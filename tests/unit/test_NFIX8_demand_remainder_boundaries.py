"""Exact Native minimum boundary and both lifecycle-mark requirements."""

import math

import pytest

from tests.unit import nfix8_demand_fixtures as fixtures
from tests.unit.nfix8_demand_fixtures import EXIT, KEY, make_d1


database = fixtures.database
case = fixtures.case


@pytest.mark.parametrize(
  "rate,expected",
  [
    (math.nextafter(3.875, -math.inf), EXIT),
    (3.875, EXIT),
    (math.nextafter(3.875, math.inf), None),
  ],
)
def test_existing_native_floor_is_inclusive(database, rate, expected):
  # One unit at 1x, so Native 1.55 * 2.5 is exactly binary 3.875.
  case = make_d1(leverage=1.0)
  case.gm0.amount = case.gm0.filled = 99.0
  case.gm0.cost = 99.0 * 11.0
  case.trade.recalc_trade_from_orders()
  assert case.trade.amount == 1.0
  case.demand()
  case.adjust(rate=rate, minimum=2.5)
  assert case.exit(rate=rate) == expected


def test_nonpositive_native_mark_cannot_start_intent(case):
  case.strategy.custom_fee_close_rate = 0.2
  native = case.strategy.calc_total_profit(
    case.trade, case.trade.select_filled_orders("buy"), case.trade.select_filled_orders("sell"), 11.0
  )[0]
  assert native < 0
  assert case.trade.realized_profit + case.trade.calculate_profit(11.0).profit_abs > 0
  case.demand()
  case.adjust()
  assert case.exit() is None
  assert case.trade.get_custom_data(KEY) is None
