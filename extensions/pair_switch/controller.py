"""An intention state machine; only Freqtrade places and reconciles orders."""

from datetime import datetime
from math import isfinite
from typing import assert_never

from freqtrade.persistence import Trade

from .models import Intent, LINK_KEY, Link, Phase, SwitchError
from .store import Store


def get_trade(trade_id: int) -> Trade | None:
  return Trade.session.get(Trade, trade_id)


def link_for(trade: Trade) -> Link | None:
  data = trade.get_custom_data(LINK_KEY)
  return Link.model_validate(data) if data is not None else None


class Controller:
  def __init__(self, store: Store):
    self.store = store

  def change(self, intent: Intent, phase: Phase, note: str) -> Intent:
    return self.store.save(intent, intent.model_copy(update={"phase": phase, "note": note}))

  def tick(self, now: datetime, available: set[str]) -> None:
    intent = self.store.active()
    if intent is None:
      return
    source = get_trade(intent.request.source_id)
    # Reconcile both open and already-closed target trades after a restart.
    if intent.phase in (Phase.ADMITTED, Phase.REVIEW):
      targets = Trade.get_trades_proxy()
      matches = [trade for trade in targets if trade.enter_tag == intent.tag]
      if len(matches) == 1:
        target = matches[0]
        if (
          source is None
          or source.is_open
          or source.has_open_orders
          or target.pair != intent.request.target
          or target.is_short != intent.short
        ):
          self.change(intent, Phase.REVIEW, "Matched tag has the wrong pair or direction.")
          return
        if target.has_open_orders:
          return
        if target.nr_of_successful_entries > 0:
          target.set_custom_data(
            LINK_KEY,
            Link(
              token=intent.request.token,
              source_id=intent.request.source_id,
              carry_profit=intent.carry_profit,
              profit_buffer=intent.request.profit_buffer,
            ).model_dump(),
          )
          self.store.save(
            intent,
            intent.model_copy(
              update={
                "phase": Phase.COMPLETE,
                "target_id": target.id,
                "note": "Target filled; native exits remain active.",
              }
            ),
          )
          return
      if intent.phase != Phase.REVIEW:
        self.change(intent, Phase.REVIEW, "No settled target fill. Authorization remains consumed; no retry.")
      return
    if now >= intent.request.expires_at:
      self.change(intent, Phase.REJECTED, "Deadline passed; no target entry will be attempted.")
      return
    if source is None:
      self.change(intent, Phase.REJECTED, "Source trade is missing.")
      return
    occupied = any(t.pair == intent.request.target for t in Trade.get_open_trades())
    if occupied or intent.request.target not in available:
      if intent.phase == Phase.REQUESTED:
        self.change(intent, Phase.REJECTED, "Target is occupied, unavailable, or lacks fresh analyzed data.")
      else:
        # Do not resume a closing request automatically after an environmental change.
        self.change(intent, Phase.REJECTED, "Target became unavailable; stop the switch without buying.")
      return
    match intent.phase:
      case Phase.REQUESTED:
        if (
          not source.is_open
          or source.has_open_orders
          or source.nr_of_successful_entries == 0
          or source.pair == intent.request.target
          or intent.request.stake > source.stake_amount
          or not isfinite(source.leverage)
          or source.leverage < 1
        ):
          self.change(intent, Phase.REJECTED, "Source is not eligible or requested stake exceeds source stake.")
          return
        prior = link_for(source)
        self.store.save(
          intent,
          intent.model_copy(
            update={
              "phase": Phase.CLOSING,
              "source_pair": source.pair,
              "source_open": source.open_date_utc,
              "short": source.is_short,
              "leverage": source.leverage,
              "source_stake": source.stake_amount,
              "carry_profit": prior.carry_profit if prior else 0.0,
              "note": "Waiting for complete source closure.",
            }
          ),
        )
      case Phase.CLOSING | Phase.READY:
        if source.pair != intent.source_pair or source.open_date_utc != intent.source_open:
          self.change(intent, Phase.REJECTED, "Source identity changed.")
          return
        if source.is_open or source.has_open_orders:
          return
        if source.close_profit_abs is None or not isfinite(source.close_profit_abs):
          self.change(intent, Phase.REJECTED, "Source final net profit is unavailable.")
          return
        if intent.phase == Phase.CLOSING:
          budget = min(intent.request.stake, max(0.0, intent.source_stake + source.close_profit_abs))
          if budget <= 0:
            self.change(intent, Phase.REJECTED, "No positive replacement budget remains.")
            return
          self.store.save(
            intent,
            intent.model_copy(
              update={
                "phase": Phase.READY,
                "budget": budget,
                "carry_profit": intent.carry_profit + source.close_profit_abs,
                "note": "Source closed; waiting for eligible target entry.",
              }
            ),
          )
      case Phase.ADMITTED | Phase.REVIEW | Phase.COMPLETE | Phase.CANCELLED | Phase.REJECTED:
        raise SwitchError("Unexpected active phase.")
      case unreachable:
        assert_never(unreachable)

  def admit(self, intent: Intent, now: datetime) -> bool:
    source = get_trade(intent.request.source_id)
    if (
      intent.phase != Phase.READY
      or now >= intent.request.expires_at
      or source is None
      or source.is_open
      or source.has_open_orders
      or source.pair != intent.source_pair
      or source.open_date_utc != intent.source_open
      or any(t.pair == intent.request.target for t in Trade.get_open_trades())
    ):
      return False
    self.change(intent, Phase.ADMITTED, "One initial entry authorized; automatic reauthorization is forbidden.")
    return True
