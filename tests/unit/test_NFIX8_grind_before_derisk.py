from datetime import timedelta

import pandas as pd
import pytest

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8
from tests.unit import test_NFIX8_liquidation_rescue
from tests.unit.test_NFIX8_liquidation_rescue import NOW
from tests.unit.test_NFIX8_liquidation_rescue import add_order


rescue_case = test_NFIX8_liquidation_rescue.rescue_case


@pytest.fixture
def grind_case(rescue_case):
  strategy, trade = rescue_case
  strategy.system_v4_grind_entry_before_derisk_enable = True
  strategy.system_v4_max_stake = 2.0
  strategy.system_v4_grind_5_liquidation_rescue_enable = False
  trade.liquidation_price = None
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


def adjust(case, rate, max_stake=10000.0):
  strategy, trade = case
  profit = trade.calc_profit_ratio(rate)
  return strategy.adjust_trade_position(trade, NOW, rate, profit, 5.0, max_stake, rate, rate, profit, profit)


def test_feature_is_enabled_by_default():
  assert NostalgiaForInfinityX8.system_v4_grind_entry_before_derisk_enable is True
  assert NostalgiaForInfinityX8.system_v4_grind_entry_before_derisk_distance == 0.02


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize(
  "long_rate,short_rate,action",
  [
    (80.01, 119.99, "none"),
    (80.0, 120.0, "entry"),
    (79.0, 121.0, "entry"),
    (78.0, 122.0, "none"),
    (77.99, 122.01, "derisk"),
  ],
)
def test_open_grind_adds_before_derisk_without_normal_signal(grind_case, level, long_rate, short_rate, action):
  # Given one open grind and no indicator/fallback entry signal.
  strategy, trade = grind_case
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)

  # When price reaches the pre-de-risk band or its boundaries.
  result = adjust(grind_case, short_rate if trade.is_short else long_rate)

  # Then this is an additional entry route, not a post-exit restriction.
  if action == "entry":
    assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"
    assert strategy._grind_entry_tag == "g_pre_derisk"
  elif action == "derisk":
    assert result is not None and result[0] < 0 and result[1].startswith(f"grind_{level}_derisk ")
  else:
    assert result is None


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("distance", [0.02, 0.03, 0.04])
def test_multiple_fills_use_weighted_queue_average(grind_case, level, distance):
  strategy, trade = grind_case
  strategy.system_v4_grind_entry_before_derisk_distance = distance
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)
  second = add_order(trade, trade.entry_side, f"grind_{level}_entry", 2.0)
  second.average = 115.0 if trade.is_short else 85.0
  second.cost = second.average * 2.0
  trade.recalc_trade_from_orders()
  average = 110.0 if trade.is_short else 90.0
  rate = average * (1.22 - distance if trade.is_short else 0.78 + distance)
  result = adjust(grind_case, rate)
  assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("state", ["empty", "other_cluster", "closed", "disabled", "no_derisk"])
def test_new_entry_requires_enabled_open_same_cluster(grind_case, level, state):
  strategy, trade = grind_case
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  if state == "other_cluster":
    add_order(trade, trade.entry_side, f"grind_{level % 5 + 1}_entry", 1.0)
  elif state != "empty":
    entry = add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)
    if state == "closed":
      add_order(trade, trade.exit_side, f"grind_{level}_derisk {entry.id}", 1.0)
    elif state == "disabled":
      strategy.system_v4_grind_entry_before_derisk_enable = False
    else:
      setattr(strategy, f"system_v4_grind_{level}_use_derisk", False)
  result = adjust(grind_case, 120.0 if trade.is_short else 80.0)
  assert result is None


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("enabled", [False, True])
def test_ordinary_entry_after_derisk_has_no_distance_restriction(grind_case, level, enabled):
  strategy, trade = grind_case
  strategy.system_v4_grind_entry_before_derisk_enable = enabled
  strategy.long_grind_entry_v4.return_value = True
  strategy.short_grind_entry_v4.return_value = True
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  entry = add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)
  add_order(trade, trade.exit_side, f"grind_{level}_derisk {entry.id}", 1.0)
  result = adjust(grind_case, 100.0)
  assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"


@pytest.mark.parametrize("gate", ["retry", "timing", "stake", "wallet", "queue", "spacing", "open_order"])
def test_new_entry_preserves_shared_admission_limits(grind_case, gate):
  strategy, trade = grind_case
  strategy.system_v4_grind_1_enable = True
  entry = add_order(trade, trade.entry_side, "grind_1_entry", 1.0)
  max_stake = 10000.0
  if gate == "retry":
    entry.order_filled_date = NOW - timedelta(minutes=4)
  elif gate == "timing":
    entry.order_filled_date = NOW - timedelta(minutes=10)
    add_order(trade, trade.exit_side, "exit_normal", 0.1).order_filled_date = NOW - timedelta(minutes=9)
    # A recent unrelated exit near current price cannot bypass the six-hour/6% guard.
    trade.orders[-1].average = 120.0 if trade.is_short else 80.0
  elif gate == "stake":
    strategy.system_v4_max_stake = 0.1
  elif gate == "wallet":
    max_stake = 1.0
  elif gate == "queue":
    strategy.system_v4_grind_1_stakes_spot = [0.2]
    strategy.system_v4_grind_1_stakes_futures = [0.2]
  elif gate == "spacing":
    strategy.system_v4_grind_1_thresholds_spot = [-0.5] * 5
    strategy.system_v4_grind_1_thresholds_futures = [-0.5] * 5
  else:
    add_order(trade, trade.entry_side, "grind_1_entry", 1.0, filled=0.0, status="open")
  assert adjust(grind_case, 120.0 if trade.is_short else 80.0, max_stake) is None


def test_filled_add_updates_average_and_does_not_repeat_at_same_price(grind_case):
  strategy, trade = grind_case
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.entry_side, "grind_1_entry", 1.0)
  rate = 120.0 if trade.is_short else 80.0
  proposal = adjust(grind_case, rate)
  assert proposal is not None and proposal[0] > 0
  order = add_order(trade, trade.entry_side, proposal[1], proposal[0] * trade.leverage / rate)
  order.average = rate
  order.cost = order.safe_filled * rate
  trade.recalc_trade_from_orders()
  assert adjust(grind_case, rate) is None
