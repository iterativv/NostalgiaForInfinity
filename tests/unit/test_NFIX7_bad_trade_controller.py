from datetime import datetime
from datetime import timedelta
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from NostalgiaForInfinityX7 import NostalgiaForInfinityX7


class MockTrade:
  def __init__(self, *, is_short=False, enter_tag="120", first_entry_rate=100.0, age_days=15):
    self.is_short = is_short
    self.enter_tag = enter_tag
    self.pair = "TEST/USDT"
    self.entry_side = "sell" if is_short else "buy"
    self.open_date_utc = datetime(2026, 1, 20, tzinfo=timezone.utc) - timedelta(days=age_days)
    self._filled_entries = [SimpleNamespace(safe_price=first_entry_rate)]

  def select_filled_orders(self, side):
    assert side == self.entry_side
    return self._filled_entries


def bad_trade_controller_strategy():
  strategy = NostalgiaForInfinityX7.__new__(NostalgiaForInfinityX7)
  strategy.bad_trade_controller_enable = True
  strategy.bad_trade_controller_structure_break_exit_enable = True
  strategy.bad_trade_controller_long_grind_stake_boost_enable = True
  strategy.bad_trade_controller_long_grind_stake_multiplier = 1.5
  strategy.bad_trade_controller_structure_break_ema_gap_pct = 35.0
  strategy.bad_trade_controller_structure_break_min_adverse_move_pct = 25.0
  strategy.bad_trade_controller_stale_exit_enable = True
  strategy.bad_trade_controller_stale_min_age_days = 14.0
  strategy.bad_trade_controller_stale_max_daily_range_pct = 7.0
  strategy.bad_trade_controller_stale_min_adverse_move_pct = 10.0
  strategy.timeframe = "5m"
  return strategy


@pytest.mark.parametrize(
  "trade,current_rate,last_candle,expected_readings",
  [
    (MockTrade(), 70.0, {"EMA_50_1d": 60.0, "EMA_200_1d": 100.0}, (-40.0, 30.0)),
    (MockTrade(is_short=True), 130.0, {"EMA_50_1d": 140.0, "EMA_200_1d": 100.0}, (-40.0, 30.0)),
  ],
)
def test_controller_ema_gap_and_adverse_move_are_signed_toward_position(
  trade, current_rate, last_candle, expected_readings
):
  readings = bad_trade_controller_strategy()._bad_trade_controller_ema_gap_and_adverse_move(
    trade, current_rate, last_candle, trade._filled_entries
  )
  assert readings == pytest.approx(expected_readings)


def test_controller_exits_use_first_entry_and_reject_nonfinite_range():
  strategy = bad_trade_controller_strategy()
  current_time = datetime(2026, 1, 20, tzinfo=timezone.utc)
  trade = MockTrade()

  structure_break_candle = {
    "EMA_50_1d": 60.0,
    "EMA_200_1d": 100.0,
    "RANGE_PCT_14_1d": 10.0,
  }
  assert (
    strategy._bad_trade_controller_exit_reason(
      trade, current_time, 70.0, structure_break_candle, trade._filled_entries
    )
    == "exit_bad_trade_broken_30pct"
  )
  strategy.bad_trade_controller_structure_break_exit_enable = False
  assert (
    strategy._bad_trade_controller_exit_reason(
      trade, current_time, 70.0, structure_break_candle, trade._filled_entries
    )
    is None
  )
  strategy.bad_trade_controller_structure_break_exit_enable = True

  stale_trade_candle = {
    "EMA_50_1d": 105.0,
    "EMA_200_1d": 100.0,
    "RANGE_PCT_14_1d": 6.0,
  }
  assert (
    strategy._bad_trade_controller_exit_reason(trade, current_time, 85.0, stale_trade_candle, trade._filled_entries)
    == "exit_bad_trade_abandon_15d"
  )

  stale_trade_candle["RANGE_PCT_14_1d"] = np.inf
  assert (
    strategy._bad_trade_controller_exit_reason(trade, current_time, 85.0, stale_trade_candle, trade._filled_entries)
    is None
  )
  assert strategy._bad_trade_controller_exit_reason(trade, current_time, 70.0, structure_break_candle, []) is None


def test_long_grind_stake_boost_preserves_tag_and_clamps_to_max_stake():
  strategy = bad_trade_controller_strategy()
  trade = MockTrade()
  analyzed_dataframe = pd.DataFrame([{"EMA_50_1d": 110.0, "EMA_200_1d": 100.0}])
  strategy.dp = SimpleNamespace(get_analyzed_dataframe=lambda pair, timeframe: (analyzed_dataframe, None))

  assert strategy._boost_bad_trade_long_grind_stake(trade, 90.0, 100.0, (80.0, "grind_1_entry")) == (
    100.0,
    "grind_1_entry",
  )
  strategy.bad_trade_controller_long_grind_stake_boost_enable = False
  assert strategy._boost_bad_trade_long_grind_stake(trade, 90.0, 100.0, (80.0, "grind_1_entry")) == (
    80.0,
    "grind_1_entry",
  )
  strategy.bad_trade_controller_long_grind_stake_boost_enable = True
  assert strategy._boost_bad_trade_long_grind_stake(trade, 90.0, 100.0, (-20.0, "derisk")) == (
    -20.0,
    "derisk",
  )
  trade.is_short = True
  assert strategy._boost_bad_trade_long_grind_stake(trade, 110.0, 100.0, (80.0, "grind")) == (
    80.0,
    "grind",
  )


def test_adjustment_router_boosts_grind_but_not_rebuy():
  strategy = bad_trade_controller_strategy()
  strategy.position_adjustment_enable = True
  strategy.long_rebuy_mode_tags = {"61"}
  strategy.long_rebuy_grind_mode_tags = {"61", "120"}
  strategy.long_grind_mode_tags = {"120"}
  strategy.long_btc_mode_tags = set()
  strategy.long_adjust_mode_tags = set()
  strategy.long_known_mode_tags = {"61", "120"}
  strategy.is_backtest_mode = lambda: True
  strategy.get_system_version_flags = lambda trade: (False, False, False)
  strategy.long_rebuy_adjust_trade_position = MagicMock(return_value=(20.0, "rebuy"))
  strategy.long_grind_adjust_trade_position = MagicMock(return_value=(20.0, "grind"))
  strategy._boost_bad_trade_long_grind_stake = MagicMock(return_value=(30.0, "grind"))
  adjustment_kwargs = {
    "current_time": datetime(2026, 1, 20, tzinfo=timezone.utc),
    "current_rate": 90.0,
    "current_profit": -0.1,
    "min_stake": 1.0,
    "max_stake": 100.0,
    "current_entry_rate": 90.0,
    "current_exit_rate": 90.0,
    "current_entry_profit": -0.1,
    "current_exit_profit": -0.1,
  }

  assert strategy.adjust_trade_position(MockTrade(enter_tag="120"), **adjustment_kwargs) == (
    30.0,
    "grind",
  )
  strategy._boost_bad_trade_long_grind_stake.assert_called_once()
  strategy._boost_bad_trade_long_grind_stake.reset_mock()

  assert strategy.adjust_trade_position(MockTrade(enter_tag="61"), **adjustment_kwargs) == (
    20.0,
    "rebuy",
  )
  strategy._boost_bad_trade_long_grind_stake.assert_not_called()


def test_custom_exit_controller_preempts_existing_router():
  strategy = bad_trade_controller_strategy()
  for name in (
    "long_normal_mode_tags",
    "long_pump_mode_tags",
    "long_quick_mode_tags",
    "long_rebuy_mode_tags",
    "long_rebuy_grind_mode_tags",
    "long_high_profit_mode_tags",
    "long_rapid_mode_tags",
    "long_rapid_rebuy_grind_scalp_mode_tags",
    "long_grind_mode_tags",
    "long_btc_mode_tags",
    "long_top_coins_mode_tags",
    "long_scalp_mode_tags",
    "long_scalp_rebuy_grind_mode_tags",
    "long_known_mode_tags",
    "short_normal_mode_tags",
    "short_pump_mode_tags",
    "short_quick_mode_tags",
    "short_rebuy_mode_tags",
    "short_high_profit_mode_tags",
    "short_rapid_mode_tags",
    "short_scalp_mode_tags",
    "short_scalp_rebuy_grind_mode_tags",
    "short_exit_known_mode_tags",
  ):
    setattr(strategy, name, set())
  strategy.long_exit_normal = MagicMock(return_value=(False, None))
  strategy.long_exit_pump = MagicMock(return_value=(False, None))
  strategy.long_exit_quick = MagicMock(return_value=(False, None))
  strategy.short_exit_normal = MagicMock(return_value=(False, None))
  analyzed_dataframe = pd.DataFrame(
    [
      {"EMA_50_1d": 60.0, "EMA_200_1d": 100.0, "RANGE_PCT_14_1d": 10.0},
      {"EMA_50_1d": 60.0, "EMA_200_1d": 100.0, "RANGE_PCT_14_1d": 10.0},
    ]
  )
  strategy.dp = SimpleNamespace(get_analyzed_dataframe=lambda pair, timeframe: (analyzed_dataframe, None))
  trade = MockTrade()
  strategy.filled_order_snapshot = MagicMock(return_value=(trade._filled_entries, trade._filled_entries, []))
  strategy.calc_total_profit = MagicMock(return_value=(-10.0, -0.1, -0.1, -0.1))
  strategy.cache_backtest_profit_snapshot = MagicMock()

  reason = strategy.custom_exit(
    trade.pair,
    trade,
    datetime(2026, 1, 20, tzinfo=timezone.utc),
    70.0,
    -0.1,
  )

  assert reason == "exit_bad_trade_broken_30pct ( 120)"
  strategy.long_exit_normal.assert_not_called()


def test_controller_indicators_are_absent_when_disabled_and_present_when_enabled():
  rows = 240
  close = np.linspace(100.0, 140.0, rows)
  informative_1d = pd.DataFrame(
    {
      "open": close - 1.0,
      "high": close + 2.0,
      "low": close - 2.0,
      "close": close,
      "volume": np.full(rows, 1000.0),
    }
  )
  strategy = bad_trade_controller_strategy()
  strategy.dp = SimpleNamespace(get_pair_dataframe=lambda pair, timeframe: informative_1d.copy())

  strategy.bad_trade_controller_enable = False
  disabled = strategy.informative_1d_indicators({"pair": "TEST/USDT"}, "1d")
  assert not {"EMA_50", "EMA_200", "RANGE_PCT_14"} & set(disabled.columns)

  strategy.bad_trade_controller_enable = True
  enabled = strategy.informative_1d_indicators({"pair": "TEST/USDT"}, "1d")
  assert {"EMA_50", "EMA_200", "RANGE_PCT_14"} <= set(enabled.columns)
  assert np.isfinite(enabled["RANGE_PCT_14"].iloc[-1])
