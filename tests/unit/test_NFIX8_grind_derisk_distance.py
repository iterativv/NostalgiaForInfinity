from datetime import timedelta

import pandas as pd
import pytest

from tests.unit.test_NFIX8_liquidation_rescue import NOW
from tests.unit.test_NFIX8_liquidation_rescue import add_order
from tests.unit import test_NFIX8_liquidation_rescue


rescue_case = test_NFIX8_liquidation_rescue.rescue_case


@pytest.fixture
def distance_case(rescue_case):
  strategy, trade = rescue_case
  strategy.system_v4_max_stake = 2.0
  strategy.system_v4_grind_5_liquidation_rescue_enable = False
  strategy.long_grind_entry_v4.return_value = True
  strategy.short_grind_entry_v4.return_value = True
  candle = {
    "close": 100.0,
    "RSI_3": 50.0,
    "RSI_3_15m": 50.0,
    "RSI_14": 50.0,
    "EMA_20": 100.0,
    "AROONU_14": 100.0,
    "AROOND_14": 100.0,
  }
  strategy.dp._set_cached_df(
    trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
  )
  return strategy, trade


def adjust(case, rate):
  strategy, trade = case
  profit = trade.calc_profit_ratio(rate)
  return strategy.adjust_trade_position(trade, NOW, rate, profit, 5.0, 10000.0, rate, rate, profit, profit)


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize(
  "rate,allowed",
  [(97.99, True), (98.0, True), (98.01, False), (100.0, False), (101.99, False), (102.0, True), (102.01, True)],
)
def test_grind_reentry_requires_two_percent_from_its_derisk(distance_case, level, rate, allowed):
  # Given a completed grind de-risk at 100 and otherwise eligible entry.
  strategy, trade = distance_case
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  entry = add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)
  add_order(trade, trade.exit_side, f"grind_{level}_derisk {entry.id}", 1.0)

  # When the public callback evaluates the proposed entry price.
  result = adjust(distance_case, rate)

  # Then the boundary is inclusive and independent of leverage/direction.
  if allowed:
    assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"
  else:
    assert result is None


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize(
  "rate,allowed",
  [(98.9799, True), (98.98, True), (98.9801, False), (103.0199, False), (103.02, True), (103.0201, True)],
)
def test_distance_boundary_uses_actual_average_fill_price(distance_case, level, rate, allowed):
  # Given a de-risk filled at 101, despite its requested limit price of 100.
  strategy, trade = distance_case
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  entry = add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)
  exit_order = add_order(trade, trade.exit_side, f"grind_{level}_derisk {entry.id}", 1.0)
  exit_order.average = 101.0
  exit_order.cost = 101.0
  trade.recalc_trade_from_orders()

  # When the callback evaluates the exact boundary or its immediate neighbors.
  result = adjust(distance_case, rate)

  # Then rounding in a divided ratio cannot reject the inclusive boundary.
  if allowed:
    assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"
  else:
    assert result is None


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("exit_tag", ["grind_{}_exit", "derisk_level_1", "derisk_global", "exit_normal"])
def test_non_grind_derisk_exits_do_not_add_distance_gate(distance_case, level, exit_tag):
  strategy, trade = distance_case
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  add_order(trade, trade.exit_side, exit_tag.format(level), 1.0)
  result = adjust(distance_case, 100.0)
  assert result is not None and result[1] == f"grind_{level}_entry"


def test_other_cluster_derisk_does_not_block_entry(distance_case):
  strategy, trade = distance_case
  strategy.system_v4_grind_2_enable = True
  add_order(trade, trade.exit_side, "grind_1_derisk 2", 1.0)
  result = adjust(distance_case, 100.0)
  assert result is not None and result[1] == "grind_2_entry"


def test_latest_cluster_exit_replaces_old_derisk(distance_case):
  strategy, trade = distance_case
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.exit_side, "grind_1_derisk 2", 1.0)
  add_order(trade, trade.exit_side, "grind_1_exit 3", 1.0)
  result = adjust(distance_case, 100.0)
  assert result is not None and result[1] == "grind_1_entry"


def test_unfilled_derisk_is_not_a_price_anchor(distance_case):
  strategy, trade = distance_case
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.exit_side, "grind_1_derisk 2", 1.0, filled=0.0, status="canceled")
  result = adjust(distance_case, 100.0)
  assert result is not None and result[1] == "grind_1_entry"


def test_partial_derisk_is_finished_before_distance_gate(distance_case):
  strategy, trade = distance_case
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.exit_side, "grind_1_derisk 2", 1.0, filled=0.5, status="canceled")
  result = adjust(distance_case, 100.0)
  assert result is not None and result[0] < 0 and result[1] == "grind_1_derisk 2"


@pytest.mark.parametrize("gate", ["signal", "retry", "wallet", "open_order"])
def test_distance_does_not_bypass_existing_entry_gates(distance_case, gate):
  strategy, trade = distance_case
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.exit_side, "grind_1_derisk 2", 1.0)
  if gate == "signal":
    strategy.long_grind_entry_v4.return_value = False
    strategy.short_grind_entry_v4.return_value = False
  elif gate == "retry":
    trade.orders[0].order_filled_date = NOW - timedelta(minutes=4)
  elif gate == "wallet":
    strategy.system_v4_max_stake = 0.1
  else:
    add_order(trade, trade.entry_side, "grind_1_entry", 1.0, filled=0.0, status="open")
  assert adjust(distance_case, 97.0 if not trade.is_short else 103.0) is None
