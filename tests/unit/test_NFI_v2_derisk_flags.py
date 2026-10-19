from datetime import timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.persistence import Trade

from NostalgiaForInfinityX7 import NostalgiaForInfinityX7
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8
from tests.unit import test_NFIX8_partial_exit as partial_tests


NOW = partial_tests.NOW
partial_exit_case = partial_tests.partial_exit_case


@pytest.fixture(
  params=[(kind, level) for kind in (NostalgiaForInfinityX7, NostalgiaForInfinityX8) for level in (1, 2, 3)]
)
def flag_case(partial_exit_case, request):
  original_strategy, trade = partial_exit_case
  kind, level = request.param
  strategy = kind.__new__(kind)
  strategy.config = original_strategy.config
  strategy.dp = original_strategy.dp
  strategy.dp.send_msg = MagicMock()
  strategy.is_futures_mode = trade.leverage > 1
  strategy.position_adjustment_enable = True
  strategy.derisk_enable = True
  trade.fee_open = trade.fee_close = 0.0
  trade.funding_fees = 0.0
  trade.enter_tag = "99999"
  trade.set_custom_data("system_version", "legacy")
  Trade.session.delete(trade.orders.pop())
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  for other in (1, 2, 3):
    setattr(strategy, f"grinding_v2_derisk_level_{other}_enable", other == level)
  candle = {
    "protections_long_global": False,
    "protections_short_global": False,
    "enter_long": False,
    "enter_short": False,
    "WILLR_14": -50.0,
  }
  for column in (
    "close",
    "open",
    "EMA_12",
    "EMA_16",
    "EMA_20",
    "EMA_26",
    "BBL_20_2.0",
    "BBU_20_2.0",
    "close_min_48",
    "close_max_48",
    "low_min_6_1h",
    "low_min_12_1h",
    "low_min_24_4h",
    "high_max_6_1h",
    "high_max_12_1h",
    "high_max_12_4h",
    "high_max_24_4h",
  ):
    candle[column] = 100.0
  for column in (
    "RSI_3",
    "RSI_3_15m",
    "RSI_3_1h",
    "RSI_3_4h",
    "RSI_3_1d",
    "RSI_14",
    "RSI_14_1h",
    "BTC_RSI_14_4h",
    "STOCHRSIk_14_14_3_3",
    "STOCHRSIk_14_14_3_3_15m",
    "STOCHRSIk_14_14_3_3_1h",
    "STOCHRSIk_14_14_3_3_4h",
  ):
    candle[column] = 50.0
  for column in (
    "ROC_2",
    "ROC_2_1h",
    "ROC_2_4h",
    "ROC_2_1d",
    "ROC_9_1h",
    "ROC_9_4h",
    "ROC_9_1d",
    "AROONU_14",
    "AROONU_14_15m",
    "AROOND_14",
    "AROOND_14_15m",
  ):
    candle[column] = 0.0
  strategy.dp._set_cached_df(trade.pair, "5m", pd.DataFrame([candle, candle]), strategy.config["candle_type_def"])
  first = trade.select_filled_orders(trade.entry_side)[0]
  basis = first.safe_filled * first.safe_price / trade.leverage
  market = "futures" if strategy.is_futures_mode else "spot"
  arm, direct = getattr(strategy, f"grinding_v2_derisk_level_{level}_{market}")
  profit = basis * (arm + direct) / 2
  return strategy, trade, level, profit


def adjust_profit(strategy, trade, profit, now=NOW):
  entries = trade.select_filled_orders(trade.entry_side)
  cost = sum(order.safe_filled * order.safe_price for order in entries)
  quantity = sum(order.safe_filled for order in entries)
  rate = (cost - profit if trade.is_short else cost + profit) / quantity
  return strategy.adjust_trade_position(trade, now, rate, 0.0, 5.0, 0.0, rate, rate, 0.0, 0.0)


def stored_flag(trade, key):
  Trade.commit()
  Trade.session.expire_all()
  return trade.get_custom_data(f"{key}_flag")


@pytest.mark.parametrize("initial", ["missing", "false", "legacy-null"])
def test_inactive_flags_arm_with_new_profit_and_time(flag_case, initial):
  strategy, trade, level, profit = flag_case
  key = f"grinding_v2_derisk_level_{level}"
  if initial != "missing":
    trade.set_custom_data(f"{key}_flag", True)
    trade.set_custom_data(f"{key}_flag", None if initial == "legacy-null" else False)
    assert stored_flag(trade, key) is False

  result = adjust_profit(strategy, trade, profit)

  assert result is None
  assert stored_flag(trade, key) is True
  assert trade.get_custom_data(f"{key}_profit") == pytest.approx(profit)
  assert trade.get_custom_data(f"{key}_time") == NOW.isoformat()


def test_improved_flag_clears_and_rearms_after_db_reload(flag_case):
  strategy, trade, level, profit = flag_case
  key = f"grinding_v2_derisk_level_{level}"
  assert adjust_profit(strategy, trade, profit) is None
  assert stored_flag(trade, key) is True
  expiry = NOW + timedelta(hours=96)
  assert adjust_profit(strategy, trade, profit + 1.0, expiry) is None
  assert stored_flag(trade, key) is True

  assert adjust_profit(strategy, trade, profit + 1.0, expiry + timedelta(microseconds=1)) is None
  assert stored_flag(trade, key) is False
  entry = trade.get_custom_data_entry(f"{key}_flag")
  assert (entry.cd_type, entry.cd_value) == ("bool", "False")
  rearm_time = expiry + timedelta(seconds=1)
  assert adjust_profit(strategy, trade, profit - 1.0, rearm_time) is None

  assert stored_flag(trade, key) is True
  assert trade.get_custom_data(f"{key}_profit") == pytest.approx(profit - 1.0)
  assert trade.get_custom_data(f"{key}_time") == rearm_time.isoformat()


def test_active_flag_keeps_timer_and_derisks_only_after_96_hours(flag_case):
  strategy, trade, level, profit = flag_case
  key = f"grinding_v2_derisk_level_{level}"
  assert adjust_profit(strategy, trade, profit) is None
  for elapsed in (timedelta(hours=48), timedelta(hours=96)):
    assert adjust_profit(strategy, trade, profit - 1.0, NOW + elapsed) is None
    assert stored_flag(trade, key) is True
    assert trade.get_custom_data(f"{key}_time") == NOW.isoformat()
    assert trade.get_custom_data(f"{key}_profit") == pytest.approx(profit)

  result = adjust_profit(strategy, trade, profit - 1.0, NOW + timedelta(hours=96, microseconds=1))

  assert result is not None
  assert result[1] == f"derisk_level_{level}"
