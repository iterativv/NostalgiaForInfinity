from datetime import timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.persistence import Trade

from NostalgiaForInfinityX8 import Cache
from tests.unit import market_relief_fixtures as fixtures
from tests.unit.market_relief_fixtures import KEY
from tests.unit.market_relief_fixtures import NOW
from tests.unit.market_relief_fixtures import REASON
from tests.unit.market_relief_fixtures import TARGET
from tests.unit.market_relief_fixtures import cash
from tests.unit.market_relief_fixtures import emit
from tests.unit.market_relief_fixtures import evaluate
from tests.unit.market_relief_fixtures import fill
from tests.unit.market_relief_fixtures import reading


case = fixtures.case


def test_actual_native_scalp_tracker_commits_fresh_target(case):
  strategy, trade = case
  for name in ("signals", "main", "williams_r", "dec"):
    setattr(strategy, f"long_exit_{name}", MagicMock(return_value=(False, None)))

  def native(pair, position, stamp, rate, current_profit, **kwargs):
    _, entries, exits = strategy.filled_order_snapshot(position)
    profits = strategy.calc_total_profit(position, entries, exits, rate)
    candle = pd.Series({"close": rate})
    sell, reason = strategy.long_exit_scalp(
      pair,
      rate,
      *profits,
      0.0,
      0.0,
      entries,
      exits,
      candle,
      candle,
      position,
      stamp,
      ["120"],
    )
    return reason if sell else None

  strategy._g2_native_custom_exit.side_effect = native
  assert evaluate(strategy, trade) == REASON
  target = Cache(strategy.target_profit_cache.path).data[trade.pair]
  assert target["sell_reason"] == TARGET
  assert target["time_profit_reached"] == NOW.isoformat()
  assert target["profit"] == pytest.approx(98.95 / 1000.0)
  assert trade.get_custom_data(KEY) == REASON


@pytest.mark.parametrize(
  "stress,relief,trigger",
  [
    (45.0, 80.0, False),
    (45.000001, 80.0, True),
    (46.0, 79.999999, False),
    (46.0, 80.0, True),
    (float("nan"), 100.0, False),
    (46.0, float("inf"), False),
    (None, 80.0, False),
  ],
)
def test_daily_guard_boundaries(case, stress, relief, trigger):
  strategy, trade = case
  reading(strategy, trade, stress, relief)
  emit(strategy, trade)
  assert evaluate(strategy, trade) == (REASON if trigger else None)
  assert trade.get_custom_data(KEY) == (REASON if trigger else None)


@pytest.mark.parametrize(
  "prior,current,trigger",
  [
    (None, NOW - timedelta(minutes=5), False),
    (NOW - timedelta(days=3), NOW - timedelta(days=3), False),
    (NOW - timedelta(days=3), NOW, True),
    (NOW - timedelta(minutes=5), NOW, False),
  ],
)
def test_only_fresh_tracking_transition_arms(case, prior, current, trigger):
  strategy, trade = case
  if prior is not None:
    strategy._set_profit_target(trade.pair, TARGET, 105.0, 0.01, prior)
    strategy.target_profit_cache = Cache(strategy.target_profit_cache.path)
  emit(strategy, trade, current)
  assert evaluate(strategy, trade) == (REASON if trigger else None)
  assert strategy.target_profit_cache.data[trade.pair]["profit"] == 0.02


@pytest.mark.parametrize(
  "price,rate,expected,trigger",
  [
    (80.0, 110.0, -140.93, False),
    (120.0, 90.0, 138.93, True),
  ],
)
def test_actual_partial_fills_and_realized_cash_override_remaining_profit(case, price, rate, expected, trigger):
  strategy, trade = case
  fill(trade, trade.exit_side, 8.0, price, 9.0)
  fill(trade, trade.entry_side, 0.0, 70.0, 9.0, pending=True)
  orders, entries, exits = strategy.filled_order_snapshot(trade)
  assert len(orders) == 2
  assert (entries[0].safe_filled, exits[0].safe_filled) == (10.0, 8.0)
  assert cash(strategy, trade, rate) == pytest.approx(expected)
  assert (trade.calc_profit_ratio(rate) > 0.0) is not trigger
  emit(strategy, trade)
  assert evaluate(strategy, trade, rate) == (REASON if trigger else None)


@pytest.mark.parametrize(
  "funding,expected,trigger",
  [
    (0.0, -1.0, False),
    (1.0, 0.0, False),
    (1.01, 0.01, True),
    (-3.0, -4.0, False),
  ],
)
def test_fees_and_signed_funding_require_strictly_positive_cash(case, funding, expected, trigger):
  strategy, trade = case
  trade.funding_fees = funding
  assert cash(strategy, trade, 100.0) == pytest.approx(expected)
  emit(strategy, trade)
  assert evaluate(strategy, trade, 100.0) == (REASON if trigger else None)


@pytest.mark.parametrize("result", ["exit_long_native", "", False, True, 0])
def test_every_non_none_native_result_preempts_pending_intent(case, monkeypatch, result):
  strategy, trade = case
  trade.set_custom_data(KEY, REASON)
  strategy._g2_native_custom_exit.return_value = result
  monkeypatch.setattr(trade, "get_custom_data", MagicMock(side_effect=AssertionError))
  assert evaluate(strategy, trade, token=17) is result
  strategy._g2_native_custom_exit.assert_called_once_with(
    trade.pair,
    trade,
    NOW,
    110.0,
    trade.calc_profit_ratio(110.0),
    token=17,
  )


@pytest.mark.parametrize("enabled,short", [(False, False), (False, True), (True, True)])
def test_off_and_short_do_not_touch_added_data_or_state(case, monkeypatch, enabled, short):
  strategy, trade = case
  strategy.risk_market_relief_exit_enable = enabled
  trade.is_short = short
  del strategy.target_profit_cache
  del strategy.dp
  for name in ("get_custom_data", "set_custom_data"):
    monkeypatch.setattr(trade, name, MagicMock(side_effect=AssertionError))
  assert evaluate(strategy, trade) is None
  strategy._g2_native_custom_exit.assert_called_once()


def test_pending_intent_survives_sqlite_reload_and_expired_market(case):
  strategy, trade = case
  emit(strategy, trade)
  assert evaluate(strategy, trade) == REASON
  trade_id = trade.id
  Trade.session.commit()
  Trade.session.expunge_all()
  reloaded = Trade.session.get(Trade, trade_id)
  assert reloaded is not None and reloaded is not trade
  strategy._g2_native_custom_exit.side_effect = None
  strategy.target_profit_cache = Cache(strategy.target_profit_cache.path)
  reading(strategy, reloaded, float("nan"), float("nan"))
  assert evaluate(strategy, reloaded, 90.0, NOW + timedelta(minutes=5)) == REASON
  assert reloaded.get_custom_data(KEY) == REASON


@pytest.mark.parametrize("reason", ["exit_long_stoploss_doom", "exit_long_abandon", "exit_short_scalp_max"])
def test_non_profit_targets_do_not_arm(case, reason):
  strategy, trade = case
  emit(strategy, trade, reason=reason)
  assert evaluate(strategy, trade) is None
  assert trade.get_custom_data(KEY) is None


def test_native_target_write_error_and_memory_mutation_are_preserved(case):
  strategy, trade = case
  emit(strategy, trade, profit=float("nan"))
  with pytest.raises(ValueError):
    evaluate(strategy, trade)
  assert pd.isna(strategy.target_profit_cache.data[trade.pair]["profit"])
  assert trade.get_custom_data(KEY) is None
