"""NFI extension: intentions are signals, never direct exchange orders."""

import fcntl
import logging
from contextlib import ExitStack
from datetime import datetime
from math import isfinite

import freqtrade
from freqtrade.persistence import Order, Trade
from pandas import DataFrame

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8
from .controller import Controller, link_for
from .models import Intent, LINK_KEY, Link, Phase, SwitchError, TAG_PREFIX
from .runtime import Options, available_pairs, bot_binding
from .store import Store


log = logging.getLogger(__name__)


class PairSwitchStrategy(NostalgiaForInfinityX8):
  _switch: Controller | None = None
  _switch_fault: bool = True
  _switch_resources: ExitStack | None = None

  def bot_start(self, **kwargs) -> None:
    super().bot_start(**kwargs)
    if freqtrade.__version__ != "2026.9" or self.version() != "v18.0.130":
      raise SwitchError("This extension is validated only with FT 2026.9 and NFI v18.0.130.")
    options = Options.model_validate(self.config["pair_switch"])
    if (
      self.config["runmode"].value not in ("live", "dry_run")
      or (not self.config["dry_run"] and not options.allow_live)
      or self.config.get("force_entry_enable", False)
      or self.timeframe != "5m"
      or not self.use_exit_signal
    ):
      raise SwitchError("Require live/dry_run, explicit live opt-in, force_entry disabled, and 5m exit signals.")
    store = Store(options.database)
    # One lifetime owner; the CLI never takes this execution lease.
    resources = ExitStack()
    try:
      options.database.parent.mkdir(parents=True, exist_ok=True)
      lease = resources.enter_context(options.database.with_suffix(".owner").open("a+"))
      fcntl.flock(lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
      store.initialize(
        bot_binding(
          self.config["db_url"],
          self.config["exchange"]["name"],
          self.config["dry_run"],
        )
      )
    except (OSError, SwitchError):
      resources.close()
      raise
    self._switch_resources = resources
    self._switch = Controller(store)
    self._switch_fault = False

  def ft_bot_cleanup(self) -> None:
    try:
      super().ft_bot_cleanup()
    finally:
      if self._switch_resources is not None:
        self._switch_resources.close()
      self._switch_fault = True

  def bot_loop_start(self, current_time: datetime, **kwargs) -> None:
    super().bot_loop_start(current_time, **kwargs)
    if self._switch_fault or self._switch is None:
      return
    try:
      self._switch.tick(current_time, available_pairs(self.dp, current_time, self.config["stake_currency"]))
    except Exception:
      # Callback boundary: FT swallows callback failures. Latch entry admission closed.
      self._switch_fault = True
      log.exception("Pair-switch controller failed; new entries disabled until restart.")

  def _intent(self) -> Intent | None:
    if self._switch_fault or self._switch is None:
      raise SwitchError("Pair-switch controller is unavailable.")
    return self._switch.store.active()

  def populate_entry_trend(self, df: DataFrame, metadata: dict[str, str]) -> DataFrame:
    df = super().populate_entry_trend(df, metadata)
    try:
      intent = self._intent()
      if intent and metadata["pair"] in (intent.source_pair, intent.request.target):
        df.loc[:, ["enter_long", "enter_short"]] = 0
        if intent.phase == Phase.READY and metadata["pair"] == intent.request.target and not df.empty:
          row = df.index[-1]
          df.loc[row, "enter_short" if intent.short else "enter_long"] = 1
          df.loc[row, "enter_tag"] = intent.tag
    except Exception:
      self._switch_fault = True
      df.loc[:, ["enter_long", "enter_short"]] = 0
      log.exception("Pair-switch signal read failed; entries disabled.")
    return df

  def confirm_trade_entry(
    self,
    pair: str,
    order_type: str,
    amount: float,
    rate: float,
    time_in_force: str,
    current_time: datetime,
    entry_tag: str | None,
    side: str,
    **kwargs,
  ) -> bool:
    try:
      intent = self._intent()
      if entry_tag and entry_tag.startswith(TAG_PREFIX):
        if (
          intent is None
          or entry_tag != intent.tag
          or pair != intent.request.target
          or side != ("short" if intent.short else "long")
          or pair not in available_pairs(self.dp, current_time, self.config["stake_currency"])
          or not isfinite(amount * rate)
          or amount <= 0
          or rate <= 0
          or amount * rate / intent.leverage > intent.budget + 1e-8
        ):
          return False
        # Retain NFI's slippage/side checks, rather than its force_entry bypass.
        if not super().confirm_trade_entry(
          pair,
          order_type,
          amount,
          rate,
          time_in_force,
          current_time,
          entry_tag,
          side,
          **kwargs,
        ):
          return False
        return self._switch.admit(intent, current_time) if self._switch else False
      if intent and pair in (intent.source_pair, intent.request.target):
        return False
      return super().confirm_trade_entry(
        pair,
        order_type,
        amount,
        rate,
        time_in_force,
        current_time,
        entry_tag,
        side,
        **kwargs,
      )
    except Exception:
      # Essential: Freqtrade defaults an exception in this callback to True.
      self._switch_fault = True
      log.exception("Pair-switch admission failed closed.")
      return False

  def custom_stake_amount(
    self,
    pair: str,
    current_time: datetime,
    current_rate: float,
    proposed_stake: float,
    min_stake: float | None,
    max_stake: float,
    leverage: float,
    entry_tag: str | None,
    side: str,
    **kwargs,
  ) -> float:
    try:
      intent = self._intent()
      if entry_tag and entry_tag.startswith(TAG_PREFIX):
        if intent is None or intent.tag != entry_tag or intent.phase != Phase.READY:
          return 0.0
        stake = min(intent.budget, max_stake, proposed_stake)
        return stake if stake >= (min_stake or 0.0) else 0.0
      return super().custom_stake_amount(
        pair,
        current_time,
        current_rate,
        proposed_stake,
        min_stake,
        max_stake,
        leverage,
        entry_tag,
        side,
        **kwargs,
      )
    except Exception:
      self._switch_fault = True
      log.exception("Pair-switch sizing failed; no stake allocated.")
      return 0.0

  def leverage(
    self,
    pair: str,
    current_time: datetime,
    current_rate: float,
    proposed_leverage: float,
    max_leverage: float,
    entry_tag: str | None,
    side: str,
    **kwargs,
  ) -> float:
    try:
      intent = self._intent()
      if entry_tag and entry_tag.startswith(TAG_PREFIX):
        if intent is None or intent.tag != entry_tag or intent.leverage > max_leverage:
          raise SwitchError("Target cannot support the frozen leverage.")
        return intent.leverage
      return super().leverage(
        pair,
        current_time,
        current_rate,
        proposed_leverage,
        max_leverage,
        entry_tag,
        side,
        **kwargs,
      )
    except Exception:
      self._switch_fault = True
      log.exception("Pair-switch leverage failed; entry admission disabled.")
      return 1.0

  def custom_exit(
    self,
    pair: str,
    trade: Trade,
    current_time: datetime,
    current_rate: float,
    current_profit: float,
    **kwargs,
  ):
    try:
      intent = self._intent()
      if (
        intent
        and intent.phase == Phase.CLOSING
        and trade.id == intent.request.source_id
        and trade.pair == intent.source_pair
        and trade.open_date_utc == intent.source_open
        and not intent.exit_admitted
        and current_time < intent.request.expires_at
      ):
        return "ps_exit_" + intent.request.token
    except Exception:
      self._switch_fault = True
      log.exception("Pair-switch source exit unavailable; retaining native exits.")
    native = super().custom_exit(pair, trade, current_time, current_rate, current_profit, **kwargs)
    if native:
      return native
    try:
      link = link_for(trade)
      if (
        link
        and link.carry_profit < 0
        and trade.calculate_profit(current_rate).total_profit + link.carry_profit >= link.profit_buffer
      ):
        return "ps_recovered"
    except Exception:
      log.exception("Pair-switch recovery accounting unavailable; retaining native exits.")
    return None

  def confirm_trade_exit(
    self,
    pair: str,
    trade: Trade,
    order_type: str,
    amount: float,
    rate: float,
    time_in_force: str,
    exit_reason: str,
    current_time: datetime,
    **kwargs,
  ) -> bool:
    if exit_reason.startswith("ps_exit_"):
      try:
        intent = self._intent()
        allowed = bool(
          intent
          and intent.phase == Phase.CLOSING
          and trade.id == intent.request.source_id
          and pair == intent.source_pair
          and trade.open_date_utc == intent.source_open
          and exit_reason == "ps_exit_" + intent.request.token
          and not intent.exit_admitted
          and current_time < intent.request.expires_at
        )
        if allowed and intent is not None and self._switch is not None:
          self._switch.store.save(
            intent,
            intent.model_copy(
              update={
                "exit_admitted": True,
                "note": "One source exit authorized; wait for closure, never resend this switch exit.",
              }
            ),
          )
        return allowed
      except Exception:
        self._switch_fault = True
        log.exception("Pair-switch exit authorization failed closed.")
        return False
    return super().confirm_trade_exit(
      pair,
      trade,
      order_type,
      amount,
      rate,
      time_in_force,
      exit_reason,
      current_time,
      **kwargs,
    )

  def order_filled(self, pair: str, trade: Trade, order: Order, current_time: datetime, **kwargs) -> None:
    super().order_filled(pair, trade, order, current_time, **kwargs)
    if trade.enter_tag and trade.enter_tag.startswith(TAG_PREFIX):
      try:
        intent = self._intent()
        if intent and intent.tag == trade.enter_tag:
          trade.set_custom_data(
            LINK_KEY,
            Link(
              token=intent.request.token,
              source_id=intent.request.source_id,
              carry_profit=intent.carry_profit,
              profit_buffer=intent.request.profit_buffer,
            ).model_dump(),
          )
      except Exception:
        self._switch_fault = True
        log.exception("Pair-switch fill metadata failed; journal retained for reconciliation.")

  def adjust_trade_position(
    self,
    trade: Trade,
    current_time: datetime,
    current_rate: float,
    current_profit: float,
    min_stake: float | None,
    max_stake: float,
    current_entry_rate: float,
    current_exit_rate: float,
    current_entry_profit: float,
    current_exit_profit: float,
    **kwargs,
  ):
    try:
      intent = self._intent()
      if intent and trade.pair in (intent.source_pair, intent.request.target):
        return None
      result = super().adjust_trade_position(
        trade,
        current_time,
        current_rate,
        current_profit,
        min_stake,
        max_stake,
        current_entry_rate,
        current_exit_rate,
        current_entry_profit,
        current_exit_profit,
        **kwargs,
      )
      amount = result[0] if isinstance(result, tuple) else result
      if trade.enter_tag and trade.enter_tag.startswith(TAG_PREFIX) and amount is not None and amount > 0:
        return None
      return result
    except Exception:
      self._switch_fault = True
      log.exception("Pair-switch adjustment failed; no position adjustment submitted.")
      return None

  def adjust_entry_price(
    self,
    trade: Trade,
    order: Order | None,
    pair: str,
    current_time: datetime,
    proposed_rate: float,
    current_order_rate: float,
    entry_tag: str | None,
    side: str,
    **kwargs,
  ) -> float | None:
    # Do not replace a consumed target admission with another entry order.
    return current_order_rate
