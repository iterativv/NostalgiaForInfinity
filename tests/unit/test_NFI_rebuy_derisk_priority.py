from unittest.mock import MagicMock

import pandas as pd
import pytest

from NostalgiaForInfinityX7 import NostalgiaForInfinityX7
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8
from tests.unit import test_NFIX8_partial_exit as partial_tests


NOW = partial_tests.NOW
partial_exit_case = partial_tests.partial_exit_case
SYSTEMS = [(NostalgiaForInfinityX7, version) for version in ("legacy", "system_v3", "system_v3_1", "system_v3_2")] + [
  (NostalgiaForInfinityX8, version) for version in ("legacy", "system_v3", "system_v3_1", "system_v3_2", "system_v4")
]


@pytest.fixture(params=SYSTEMS)
def rebuy_case(partial_exit_case, request):
  original_strategy, trade = partial_exit_case
  strategy_type, version = request.param
  strategy = strategy_type.__new__(strategy_type)
  strategy.config = original_strategy.config
  strategy.dp = original_strategy.dp
  strategy.dp.send_msg = MagicMock()
  strategy.is_futures_mode = trade.leverage > 1
  strategy.position_adjustment_enable = True
  strategy.derisk_enable = True
  trade.fee_open = trade.fee_close = 0.0
  trade.funding_fees = 0.0
  trade.enter_tag = "561" if trade.is_short else "61"
  trade.set_custom_data("system_version", version)
  for order, price, tag in (
    (trade.orders[0], 100.0, "initial"),
    (trade.orders[1], 110.0 if trade.is_short else 90.0, "r"),
  ):
    order.amount = order.ft_amount = order.filled = 12.0
    order.price = order.average = order.ft_price = price
    order.cost = 12.0 * price
    order.ft_order_tag = tag
  trade.recalc_trade_from_orders()
  rate = 150.0 if trade.is_short else 60.0
  candle = {
    "close": rate,
    "EMA_26": rate * (0.9 if trade.is_short and version == "legacy" else 1.1),
    "RSI_3": 50.0,
    "RSI_3_15m": 50.0,
    "RSI_14": 70.0 if trade.is_short else 30.0,
    "ROC_2": -1.0 if trade.is_short else 1.0,
    "AROONU_14": 10.0,
    "AROONU_14_15m": 10.0,
    "AROOND_14": 10.0,
    "AROOND_14_15m": 10.0,
    "protections_long_global": True,
    "protections_short_global": True,
  }
  dataframe = pd.DataFrame([candle, candle])
  strategy.dp._set_cached_df(trade.pair, "5m", dataframe, strategy.config["candle_type_def"])
  return strategy, trade, rate, dataframe


def adjust(strategy, trade, rate, max_stake=10000.0):
  return strategy.adjust_trade_position(trade, NOW, rate, 0.0, 5.0, max_stake, rate, rate, 0.0, 0.0)


@pytest.mark.parametrize("max_stake", [0.0, 399.6, 400.0, 500.0, 1198.8, 1200.0, 1500.0, 10000.0])
@pytest.mark.parametrize("rebuy_signal", [False, True])
def test_funded_rebuy_keeps_priority_otherwise_derisk_runs(rebuy_case, max_stake, rebuy_signal):
  strategy, trade, rate, dataframe = rebuy_case
  if not rebuy_signal:
    dataframe["RSI_3"] = 100.0 if trade.is_short else 0.0

  result = adjust(strategy, trade, rate, max_stake)

  if rebuy_signal and max_stake >= 1200.0 / trade.leverage:
    assert result == (1200.0 / trade.leverage, "r")
    return

  expected_quantity = trade.amount - 5.0 * 1.55 * trade.leverage / rate
  assert result is not None
  assert result[1] == "derisk_level_3"
  assert -result[0] * trade.amount / trade.stake_amount == pytest.approx(expected_quantity)


@pytest.mark.parametrize("rows", [0, 1])
def test_candle_availability_preserves_rebuy_or_derisk(rebuy_case, rows):
  strategy, trade, rate, dataframe = rebuy_case
  strategy.dp._set_cached_df(trade.pair, "5m", dataframe.iloc[:rows], strategy.config["candle_type_def"])

  result = adjust(strategy, trade, rate)

  # Legacy needs two candles; v3/v4 already allow a funded rebuy with one.
  if rows == 1 and trade.get_custom_data("system_version") != "legacy":
    assert result == (1200.0 / trade.leverage, "r")
    return

  assert result is not None
  assert result[1] == "derisk_level_3"


@pytest.mark.parametrize("max_stake", [0.0, 10000.0])
def test_disabled_derisk_preserves_rebuy_budget(rebuy_case, max_stake):
  strategy, trade, rate, _ = rebuy_case
  strategy.derisk_enable = False

  result = adjust(strategy, trade, rate, max_stake)

  assert result == ((1200.0 / trade.leverage, "r") if max_stake else None)


def test_unmet_derisk_threshold_preserves_rebuy(rebuy_case):
  strategy, trade, _, _ = rebuy_case
  rate = 125.0 if trade.is_short else 79.0

  result = adjust(strategy, trade, rate)

  assert result == (1200.0 / trade.leverage, "r")


def test_open_order_prevents_both_actions(rebuy_case):
  strategy, trade, rate, _ = rebuy_case
  trade.orders[-1].ft_is_open = True
  trade.orders[-1].status = "open"

  result = adjust(strategy, trade, rate)

  assert result is None
