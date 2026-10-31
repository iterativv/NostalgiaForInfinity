"""Persisted intents, fee-aware marks and actual remaining inventory."""

from datetime import timedelta

import pytest

from tests.unit import nfix8_demand_fixtures as fixtures
from tests.unit.nfix8_demand_fixtures import DEMAND, DUE, EXIT, FEATURE, KEY, fill, make_d1


database = fixtures.database
case = fixtures.case


def start(case):
  assert case.demand() is False
  assert case.adjust() is None
  assert case.exit() == EXIT
  return case.trade.get_custom_data(KEY)


def test_pending_token_survives_strategy_restart(case):
  case.demand()
  restarted = case.restart()
  restarted.adjust()
  assert restarted.exit() == EXIT
  assert restarted.trade.get_custom_data(KEY)["closing"] is True


def test_restart_after_token_consumption_does_not_replay_it(case):
  case.demand()
  case.adjust()
  restarted = case.restart()
  assert restarted.exit() is None
  assert restarted.trade.get_custom_data(KEY) is None


def test_closing_survives_restart_and_disabled_admissions(case):
  initial = start(case)
  restarted = case.restart(enabled=False)
  restarted.adjust(DUE + timedelta(minutes=5))
  assert restarted.exit(DUE + timedelta(minutes=5)) == EXIT
  assert restarted.trade.get_custom_data(KEY) == initial
  assert getattr(restarted.strategy, FEATURE) is False


@pytest.mark.parametrize("result", [(10.0, "gd1"), 10.0, (-10.0, "dd1 1"), -10.0, None])
def test_closing_filters_only_positive_adjustments(case, result):
  start(case)
  filtered = case.strategy._legacy_grind_demand_adjust(case.trade, result)
  amount = result[0] if isinstance(result, tuple) else result
  assert filtered == (None if amount is not None and amount > 0 else result)


@pytest.mark.parametrize("tag,short", [("41", False), ("120 144", False), ("120", True)])
def test_other_routes_are_not_filtered(case, tag, short):
  start(case)
  case.trade.enter_tag, case.trade.is_short = tag, short
  assert case.strategy._legacy_grind_demand_adjust(case.trade, (10.0, "gd1")) == (10.0, "gd1")


@pytest.mark.parametrize("executed", [0.0, 0.04])
def test_canceled_exit_retains_real_remainder_and_closing(case, executed):
  intent = start(case)
  before = case.trade.amount
  order = fill(case.trade, "sell", before, EXIT, 11.0, filled=executed, time=DUE)
  order.status = "canceled"
  assert case.exit(DUE + timedelta(minutes=5)) == EXIT
  assert case.trade.is_open
  assert case.trade.amount == pytest.approx(before - executed)
  assert case.trade.get_custom_data(KEY) == intent
  assert case.demand(DUE + timedelta(minutes=5)) is False


def test_open_exit_order_is_managed_without_duplicate_exit_signal(case):
  intent = start(case)
  order = fill(case.trade, "sell", case.trade.amount, EXIT, 11.0, filled=0.0, time=DUE)
  order.ft_is_open, order.status = True, "open"
  assert case.exit(DUE + timedelta(minutes=5)) is None
  assert case.trade.get_custom_data(KEY) == intent
  assert case.trade.is_open


def test_slot_is_not_released_by_exit_signal(case):
  start(case)
  assert case.demand(DUE) is False
  assert case.trade.is_open and case.trade.amount > 0


def test_spot_base_fee_uses_engine_net_inventory(database):
  case = make_d1(leverage=1.0, base_fee=1.0)
  assert case.entry.safe_filled == 100.0
  assert case.entry.safe_amount_after_fee == 99.0
  assert case.trade.amount == pytest.approx(0.1)
  case.demand()
  case.adjust()
  assert case.exit() == EXIT
  assert case.trade.amount == pytest.approx(0.1)


def test_accounting_mark_can_veto_positive_native_mark(database):
  case = make_d1(fees=0.005)
  case.strategy.custom_fee_open_rate = case.strategy.custom_fee_close_rate = 0.0
  case.trade.funding_fees = -99.999
  native_mark = case.strategy.calc_total_profit(
    case.trade, case.trade.select_filled_orders("buy"), case.trade.select_filled_orders("sell"), 11.0
  )[0]
  assert native_mark > 0
  assert case.trade.realized_profit + case.trade.calculate_profit(11.0).profit_abs < 0
  case.demand()
  case.adjust()
  assert case.exit() is None
  assert case.trade.get_custom_data(KEY) is None


def test_realized_funding_is_not_counted_twice(case):
  case.entry.funding_fee = -30.0
  case.gm0.funding_fee = -50.0
  case.trade.recalc_trade_from_orders()
  case.trade.funding_fees = -90.0
  uncorrected = case.trade.realized_profit + case.trade.calculate_profit(11.0).profit_abs
  assert uncorrected < 0 < uncorrected + 80.0
  case.demand()
  case.adjust()
  assert case.exit() == EXIT
  assert case.trade.get_custom_data(KEY)["closing"] is True


def test_disabled_feature_drops_pending_token(case):
  case.demand()
  setattr(case.strategy, FEATURE, False)
  case.adjust(DEMAND)
  assert case.exit(DEMAND) is None
  assert case.trade.get_custom_data(KEY) is None
