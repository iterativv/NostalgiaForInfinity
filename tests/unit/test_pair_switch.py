"""Deterministic pair-switch regressions against real Freqtrade 2026.9 models.

Run with the installed Freqtrade interpreter:
python -m unittest discover -s tests/unit -p test_pair_switch.py -v
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Barrier
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from ccxt import DECIMAL_PLACES
from freqtrade.enums import TradingMode
from freqtrade.persistence import Order, Trade, init_db
from freqtrade.persistence.custom_data import _CustomData
from freqtrade.strategy.strategy_wrapper import strategy_safe_wrapper
from pandas import DataFrame, Timestamp

from extensions.pair_switch.controller import Controller, link_for
from extensions.pair_switch.models import LINK_KEY, Link, Phase, Request, SwitchError
from extensions.pair_switch.store import Store
from extensions.pair_switch.strategy import PairSwitchStrategy
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 14, 12, tzinfo=timezone.utc)
SOURCE = "AAA/USDT"
TARGET = "BBB/USDT"
THIRD = "CCC/USDT"


class PairSwitchFixture(unittest.TestCase):
  def setUp(self):
    self.temp = TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    init_db("sqlite://")
    self.engine = Trade.session.get_bind()
    self.addCleanup(self.cleanup_db, Trade.session, _CustomData.session, self.engine)
    self.store = Store(Path(self.temp.name) / "queue.sqlite")
    self.store.initialize("test-bot")
    self.controller = Controller(self.store)
    self.order_number = 0
    self.source = self.make_trade(SOURCE)

  @staticmethod
  def cleanup_db(trade_session, custom_session, engine):
    custom_session.remove()
    trade_session.remove()
    engine.dispose()

  def add_order(self, trade, side, rate, amount, *, pending=False, funding=0.0):
    self.order_number += 1
    order = Order(
      ft_order_side=side,
      ft_pair=trade.pair,
      ft_is_open=pending,
      ft_amount=amount,
      ft_price=rate,
      order_id=str(self.order_number),
      status="open" if pending else "closed",
      symbol=trade.pair,
      order_type="limit",
      side=side,
      price=rate,
      average=rate,
      amount=amount,
      filled=0.0 if pending else amount,
      remaining=amount if pending else 0.0,
      cost=rate * amount,
      order_date=NOW,
      order_filled_date=None if pending else NOW,
      order_update_date=NOW,
      funding_fee=funding,
    )
    trade.orders.append(order)
    Trade.commit()
    if not pending:
      trade.update_trade(order)
    return order

  def make_trade(self, pair, *, tag=None, fee=0.0, short=False):
    trade = Trade(
      pair=pair,
      exchange="test",
      is_open=True,
      is_short=short,
      open_date=NOW - timedelta(days=1),
      open_rate=100.0,
      stake_amount=100.0,
      amount=1.0,
      amount_requested=1.0,
      fee_open=fee,
      fee_close=fee,
      leverage=1.0,
      trading_mode=TradingMode.FUTURES,
      enter_tag=tag,
      amount_precision=8,
      price_precision=8,
      precision_mode=DECIMAL_PLACES,
      precision_mode_price=DECIMAL_PLACES,
      contract_size=1.0,
    )
    Trade.session.add(trade)
    Trade.commit()
    self.add_order(trade, trade.entry_side, 100.0, 1.0)
    return trade

  def request(self, **updates):
    values = dict(
      token="a" * 32,
      source_id=self.source.id,
      target=TARGET,
      stake=100.0,
      profit_buffer=2.0,
      expires_at=NOW + timedelta(hours=1),
    )
    values.update(updates)
    return Request(**values)

  def closing(self, **updates):
    self.store.submit(self.request(**updates))
    self.controller.tick(NOW, {TARGET, THIRD})
    intent = self.store.active()
    self.assertEqual(intent.phase, Phase.CLOSING)
    return intent

  def ready(self, rate=80.0, **updates):
    self.closing(**updates)
    self.add_order(self.source, self.source.exit_side, rate, self.source.amount)
    self.assertFalse(self.source.is_open)
    self.controller.tick(NOW, {TARGET, THIRD})
    intent = self.store.active()
    self.assertEqual(intent.phase, Phase.READY)
    return intent


class QueueTests(PairSwitchFixture):
  def test_source_fill_ready_one_shot_target_fill_and_restart_metadata(self):
    ready = self.ready()
    self.assertEqual(ready.budget, 80.0)
    self.assertEqual(ready.carry_profit, -20.0)
    self.assertTrue(self.controller.admit(ready, NOW))
    self.assertFalse(self.controller.admit(self.store.active(), NOW))
    with self.assertRaisesRegex(SwitchError, "changed concurrently"):
      self.controller.admit(ready, NOW)
    target = self.make_trade(TARGET, tag=ready.tag)
    target_id = target.id
    Trade.session.remove()
    Controller(Store(self.store.path)).tick(NOW, {TARGET})
    finished = self.store.all()[0]
    self.assertEqual(finished.phase, Phase.COMPLETE)
    self.assertEqual(finished.target_id, target_id)
    self.assertIsNone(self.store.active())
    Trade.session.remove()
    restored = Trade.session.get(Trade, target_id)
    self.assertEqual(
      link_for(restored),
      Link(
        token=ready.request.token,
        source_id=ready.request.source_id,
        carry_profit=-20.0,
        profit_buffer=2.0,
      ),
    )

  def test_duplicate_token_is_idempotent_but_conflicting_data_refused(self):
    request = self.request()
    first = self.store.submit(request)
    self.assertEqual(self.store.submit(request), first)
    with self.assertRaisesRegex(SwitchError, "different request data"):
      self.store.submit(self.request(stake=90.0))
    self.assertEqual(self.store.all(), [first])

  def test_active_request_conflict_and_source_reuse_after_cancel(self):
    self.store.submit(self.request())
    with self.assertRaisesRegex(SwitchError, "Another request is active"):
      self.store.submit(self.request(token="b" * 32, source_id=999))
    self.store.cancel("a" * 32)
    with self.assertRaisesRegex(SwitchError, "source trade was already requested"):
      self.store.submit(self.request(token="c" * 32))

  def test_occupied_target_is_rejected_before_source_exit(self):
    self.make_trade(TARGET)
    self.store.submit(self.request())
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)
    self.assertTrue(self.source.is_open)

  def test_source_pair_cannot_be_target(self):
    self.store.submit(self.request(target=SOURCE))
    self.controller.tick(NOW, {SOURCE})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_pending_source_order_rejected_before_exit(self):
    self.add_order(self.source, self.source.exit_side, 80.0, 1.0, pending=True)
    self.store.submit(self.request())
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_partial_source_exit_and_pending_remainder_never_admitted(self):
    self.closing()
    self.add_order(self.source, self.source.exit_side, 80.0, 0.4)
    pending = self.add_order(self.source, self.source.exit_side, 75.0, 0.6, pending=True)
    self.controller.tick(NOW, {TARGET})
    self.assertTrue(self.source.is_open)
    self.assertEqual(self.store.active().phase, Phase.CLOSING)
    self.assertFalse(self.controller.admit(self.store.active(), NOW))
    pending.ft_is_open = False
    pending.status = "closed"
    pending.filled = 0.6
    pending.remaining = 0.0
    pending.order_filled_date = NOW
    self.source.update_trade(pending)
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.active().phase, Phase.READY)
    self.assertAlmostEqual(self.store.active().carry_profit, -23.0)
    self.assertAlmostEqual(self.store.active().budget, 77.0)

  def test_closed_source_with_pending_order_waits(self):
    self.closing()
    self.add_order(self.source, self.source.exit_side, 80.0, 1.0)
    self.add_order(self.source, self.source.exit_side, 80.0, 0.1, pending=True)
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.active().phase, Phase.CLOSING)

  def test_requested_stake_exceeding_source_is_rejected(self):
    self.store.submit(self.request(stake=100.01))
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_no_positive_budget_after_fees_is_rejected(self):
    self.source.fee_open = self.source.fee_close = 0.01
    self.closing()
    self.add_order(self.source, self.source.exit_side, 0.1, 1.0)
    self.assertLess(self.source.close_profit_abs, -100.0)
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_expiry_at_exact_deadline_rejects_request(self):
    self.store.submit(self.request(expires_at=NOW))
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_ready_admission_refuses_exact_deadline(self):
    ready = self.ready()
    self.assertFalse(self.controller.admit(ready, ready.request.expires_at))
    self.controller.tick(ready.request.expires_at, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_missing_source_is_rejected(self):
    self.store.submit(self.request(source_id=999))
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_changed_source_identity_refuses_closing_and_admission(self):
    ready = self.ready()
    self.source.open_date += timedelta(seconds=1)
    Trade.commit()
    self.assertFalse(self.controller.admit(ready, NOW))
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_target_becomes_occupied_after_ready(self):
    ready = self.ready()
    self.make_trade(TARGET)
    self.assertFalse(self.controller.admit(ready, NOW))
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)

  def test_target_unavailable_during_closing_is_not_resumed(self):
    self.closing()
    self.controller.tick(NOW, set())
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)
    self.assertTrue(self.source.is_open)

  def test_concurrent_admission_compare_and_swap_allows_exactly_one(self):
    ready = self.ready()
    barrier = Barrier(2)

    def attempt():
      controller = Controller(Store(self.store.path))
      change = controller.change

      def synchronized_change(*args):
        barrier.wait(timeout=5)
        return change(*args)

      controller.change = synchronized_change
      try:
        return controller.admit(ready, NOW)
      except SwitchError as error:
        return str(error)
      finally:
        Trade.session.remove()

    with ThreadPoolExecutor(max_workers=2) as pool:
      results = list(pool.map(lambda _: attempt(), range(2)))
    self.assertEqual(results.count(True), 1)
    self.assertEqual(results.count("The request changed concurrently; admission was refused."), 1)
    self.assertEqual(self.store.active().phase, Phase.ADMITTED)

  def test_admitted_without_trade_is_never_rearmed_even_after_expiry(self):
    ready = self.ready()
    self.controller.admit(ready, NOW)
    for now in (NOW, ready.request.expires_at, NOW + timedelta(days=1)):
      Controller(Store(self.store.path)).tick(now, {TARGET})
      self.assertEqual(self.store.active().phase, Phase.REVIEW)
      self.assertFalse(self.controller.admit(self.store.active(), now))
    with self.assertRaisesRegex(SwitchError, "never rearm"):
      self.store.cancel(ready.request.token)

  def test_open_and_closed_target_restart_recovery(self):
    for closed in (False, True):
      with self.subTest(closed=closed):
        self.setUp()
        ready = self.ready()
        self.controller.admit(ready, NOW)
        target = self.make_trade(TARGET, tag=ready.tag)
        if closed:
          self.add_order(target, target.exit_side, 110.0, target.amount)
        target_id = target.id
        Trade.session.remove()
        Controller(Store(self.store.path)).tick(NOW + timedelta(days=1), {TARGET})
        self.assertEqual(self.store.all()[0].phase, Phase.COMPLETE)
        recovered = Trade.session.get(Trade, target_id)
        self.assertEqual(recovered.is_open, not closed)
        self.assertEqual(link_for(recovered).carry_profit, -20.0)

  def test_pending_target_fill_waits_for_settlement(self):
    ready = self.ready()
    self.controller.admit(ready, NOW)
    target = self.make_trade(TARGET, tag=ready.tag)
    pending = self.add_order(target, target.entry_side, 100.0, 0.1, pending=True)
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.active().phase, Phase.ADMITTED)
    pending.ft_is_open = False
    pending.status = "canceled"
    Trade.commit()
    self.controller.tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].phase, Phase.COMPLETE)

  def test_wrong_target_pair_or_direction_and_duplicate_tags_require_review(self):
    for problem in ("pair", "direction", "duplicate"):
      with self.subTest(problem=problem):
        self.setUp()
        ready = self.ready()
        self.controller.admit(ready, NOW)
        target = self.make_trade(THIRD if problem == "pair" else TARGET, tag=ready.tag, short=problem == "direction")
        if problem == "duplicate":
          self.make_trade(THIRD, tag=ready.tag)
        self.controller.tick(NOW, {TARGET})
        self.assertEqual(self.store.active().phase, Phase.REVIEW)
        self.assertIsNone(link_for(target))

  def test_multi_hop_carries_real_net_fees_funding_and_partial_exits_once(self):
    self.source.fee_open = self.source.fee_close = 0.001
    self.closing()
    self.add_order(self.source, self.source.exit_side, 90.0, 0.4, funding=1.0)
    self.add_order(self.source, self.source.exit_side, 80.0, 0.6, funding=-0.5)
    self.assertAlmostEqual(self.source.close_profit_abs, -15.684)
    self.controller.tick(NOW, {TARGET, THIRD})
    first = self.store.active()
    self.assertAlmostEqual(first.carry_profit, -15.684)
    self.controller.admit(first, NOW)
    target = self.make_trade(TARGET, tag=first.tag, fee=0.001)
    self.controller.tick(NOW, {TARGET, THIRD})
    self.store.submit(self.request(token="b" * 32, source_id=target.id, target=THIRD))
    self.controller.tick(NOW, {THIRD})
    self.assertAlmostEqual(self.store.active().carry_profit, -15.684)
    self.add_order(target, target.exit_side, 110.0, 1.0, funding=0.25)
    self.assertAlmostEqual(target.close_profit_abs, 10.04)
    self.controller.tick(NOW, {THIRD})
    second = self.store.active()
    self.assertAlmostEqual(second.carry_profit, -5.644)
    self.assertEqual(second.budget, 100.0)
    self.controller.tick(NOW, {THIRD})
    self.assertEqual(self.store.active(), second)


class StrategyTests(PairSwitchFixture):
  def setUp(self):
    super().setUp()
    self.strategy = object.__new__(PairSwitchStrategy)
    self.strategy._switch = self.controller
    self.strategy._switch_fault = False
    self.strategy.config = {"stake_currency": "USDT"}
    frame = DataFrame([{"date": Timestamp(NOW), "close": 100.0, "volume": 1.0}])
    self.strategy.dp = SimpleNamespace(
      current_whitelist=lambda: [TARGET, THIRD],
      market=lambda pair: {"active": True},
      get_analyzed_dataframe=lambda pair, timeframe: (frame, NOW),
    )

  def confirm(self, intent, *, amount=0.8, rate=100.0, pair=TARGET, side="long", tag=None):
    return self.strategy.confirm_trade_entry(
      pair,
      "limit",
      amount,
      rate,
      "gtc",
      NOW,
      tag or intent.tag,
      side,
    )

  def adjustment(self, trade):
    return self.strategy.adjust_trade_position(
      trade,
      NOW,
      100.0,
      0.0,
      1.0,
      1000.0,
      100.0,
      100.0,
      0.0,
      0.0,
    )

  def test_db_failure_confirm_fails_closed_through_freqtrade_true_default(self):
    self.store.path.unlink()
    callback = strategy_safe_wrapper(self.strategy.confirm_trade_entry, default_retval=True)
    with self.assertLogs("extensions.pair_switch.strategy", level="ERROR"):
      admitted = callback(THIRD, "limit", 1.0, 100.0, "gtc", NOW, None, "long")
    self.assertFalse(admitted)
    self.assertTrue(self.strategy._switch_fault)

  def test_native_exit_preserved_below_carried_debt_and_exit_confirmation(self):
    self.source.set_custom_data(
      LINK_KEY,
      Link(
        token="a" * 32,
        source_id=99,
        carry_profit=-100.0,
        profit_buffer=2.0,
      ).model_dump(),
    )
    with patch.object(NostalgiaForInfinityX8, "custom_exit", return_value="native_stop") as native:
      self.assertEqual(self.strategy.custom_exit(SOURCE, self.source, NOW, 80.0, -0.2), "native_stop")
      native.assert_called_once()
    with patch.object(NostalgiaForInfinityX8, "confirm_trade_exit", return_value=True) as confirm:
      self.assertTrue(
        self.strategy.confirm_trade_exit(
          SOURCE,
          self.source,
          "limit",
          1.0,
          80.0,
          "gtc",
          "native_stop",
          NOW,
        )
      )
      confirm.assert_called_once()

  def test_recovery_exit_uses_real_net_profit_and_buffer(self):
    self.source.set_custom_data(
      LINK_KEY,
      Link(
        token="a" * 32,
        source_id=99,
        carry_profit=-20.0,
        profit_buffer=2.0,
      ).model_dump(),
    )
    with patch.object(NostalgiaForInfinityX8, "custom_exit", return_value=None):
      self.assertIsNone(self.strategy.custom_exit(SOURCE, self.source, NOW, 121.99, 0.2199))
      self.assertEqual(self.strategy.custom_exit(SOURCE, self.source, NOW, 122.0, 0.22), "ps_recovered")

  def test_final_entry_notional_budget_and_invalid_values_are_refused(self):
    ready = self.ready()
    with patch.object(NostalgiaForInfinityX8, "confirm_trade_entry", return_value=True) as native:
      for amount, rate in (
        (0.8001, 100.0),
        (0.0, 100.0),
        (-1.0, 100.0),
        (1.0, 0.0),
        (float("nan"), 100.0),
        (1.0, float("inf")),
      ):
        with self.subTest(amount=amount, rate=rate):
          self.assertFalse(self.confirm(ready, amount=amount, rate=rate))
          self.assertEqual(self.store.active().phase, Phase.READY)
      native.assert_not_called()
      self.assertTrue(self.confirm(ready))
      native.assert_called_once()
      self.assertFalse(self.confirm(ready))

  def test_entry_identity_native_veto_and_fresh_market_are_required(self):
    ready = self.ready()
    with patch.object(NostalgiaForInfinityX8, "confirm_trade_entry", return_value=False):
      self.assertFalse(self.confirm(ready))
      self.assertEqual(self.store.active().phase, Phase.READY)
    with patch.object(NostalgiaForInfinityX8, "confirm_trade_entry", return_value=True) as native:
      for pair, side, tag in (
        (THIRD, "long", ready.tag),
        (TARGET, "short", ready.tag),
        (TARGET, "long", "ps_" + "b" * 32),
      ):
        self.assertFalse(self.confirm(ready, pair=pair, side=side, tag=tag))
      self.strategy.dp.current_whitelist = lambda: []
      self.assertFalse(self.confirm(ready))
      native.assert_not_called()

  def test_custom_stake_obeys_budget_proposal_maximum_and_minimum(self):
    ready = self.ready()
    for proposed, minimum, maximum, expected in (
      (100.0, 1.0, 1000.0, 80.0),
      (50.0, 1.0, 1000.0, 50.0),
      (100.0, None, 40.0, 40.0),
      (100.0, 81.0, 1000.0, 0.0),
    ):
      with self.subTest(proposed=proposed, minimum=minimum, maximum=maximum):
        self.assertEqual(
          self.strategy.custom_stake_amount(
            TARGET,
            NOW,
            100.0,
            proposed,
            minimum,
            maximum,
            1.0,
            ready.tag,
            "long",
          ),
          expected,
        )
    self.controller.admit(ready, NOW)
    self.assertEqual(
      self.strategy.custom_stake_amount(
        TARGET,
        NOW,
        100.0,
        100.0,
        1.0,
        1000.0,
        1.0,
        ready.tag,
        "long",
      ),
      0.0,
    )

  def test_source_exit_identity_and_deadline(self):
    intent = self.closing()
    reason = "ps_exit_" + intent.request.token
    with patch.object(NostalgiaForInfinityX8, "custom_exit", return_value="native"):
      self.assertEqual(self.strategy.custom_exit(SOURCE, self.source, NOW, 80.0, -0.2), reason)
      self.assertEqual(
        self.strategy.custom_exit(
          SOURCE,
          self.source,
          intent.request.expires_at,
          80.0,
          -0.2,
        ),
        "native",
      )
    self.strategy._remove_profit_target = lambda pair: None
    self.assertTrue(
      self.strategy.confirm_trade_exit(
        SOURCE,
        self.source,
        "limit",
        1.0,
        80.0,
        "gtc",
        reason,
        NOW,
      )
    )
    self.assertFalse(
      self.strategy.confirm_trade_exit(
        SOURCE,
        self.source,
        "limit",
        1.0,
        80.0,
        "gtc",
        reason,
        intent.request.expires_at,
      )
    )

  def test_order_filled_metadata_persists_and_restart_completes(self):
    ready = self.ready()
    self.controller.admit(ready, NOW)
    target = self.make_trade(TARGET, tag=ready.tag)
    with patch.object(NostalgiaForInfinityX8, "order_filled", return_value=None) as native:
      self.strategy.order_filled(TARGET, target, target.orders[0], NOW)
      native.assert_called_once()
    self.assertEqual(link_for(target).carry_profit, -20.0)
    target_id = target.id
    Trade.session.remove()
    Controller(Store(self.store.path)).tick(NOW, {TARGET})
    self.assertEqual(self.store.all()[0].target_id, target_id)
    self.assertEqual(self.store.all()[0].phase, Phase.COMPLETE)

  def test_position_adjustment_bound_for_source_target_and_linked_target(self):
    intent = self.closing()
    target = self.make_trade(TARGET, tag=intent.tag)
    with patch.object(NostalgiaForInfinityX8, "adjust_trade_position", return_value=10.0) as native:
      self.assertIsNone(self.adjustment(self.source))
      self.assertIsNone(self.adjustment(target))
      native.assert_not_called()
      self.store.cancel(intent.request.token)
      self.assertIsNone(self.adjustment(target))
    with patch.object(NostalgiaForInfinityX8, "adjust_trade_position", return_value=(10.0, "add")):
      self.assertIsNone(self.adjustment(target))
    with patch.object(NostalgiaForInfinityX8, "adjust_trade_position", return_value=(-5.0, "reduce")):
      self.assertEqual(self.adjustment(target), (-5.0, "reduce"))

  def test_target_replacement_price_remains_current_order_rate(self):
    ready = self.ready()
    target = self.make_trade(TARGET, tag=ready.tag)
    self.assertEqual(
      self.strategy.adjust_entry_price(
        target,
        target.orders[0],
        TARGET,
        NOW,
        110.0,
        99.0,
        ready.tag,
        "long",
      ),
      99.0,
    )

  def test_ready_signal_only_latest_target_row_and_source_suppressed(self):
    ready = self.ready()
    frame = DataFrame({"enter_long": [1, 1], "enter_short": [1, 1], "enter_tag": ["nfi", "nfi"]})
    with patch.object(NostalgiaForInfinityX8, "populate_entry_trend", side_effect=lambda df, meta: df):
      target = self.strategy.populate_entry_trend(frame.copy(), {"pair": TARGET})
      source = self.strategy.populate_entry_trend(frame.copy(), {"pair": SOURCE})
    self.assertEqual(target["enter_long"].tolist(), [0, 1])
    self.assertEqual(target["enter_short"].tolist(), [0, 0])
    self.assertEqual(target.iloc[-1]["enter_tag"], ready.tag)
    self.assertEqual(source["enter_long"].tolist(), [0, 0])
    self.assertEqual(source["enter_short"].tolist(), [0, 0])


if __name__ == "__main__":
  unittest.main()
