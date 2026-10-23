"""Guards for the 170 crash-bounce signal: the Bitcoin daily capitulation gate."""

import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import talib.abstract as ta
from freqtrade.enums import RunMode
from freqtrade.strategy import merge_informative_pair

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"
GATE = re.compile(r'\(np_view\("BTC_RSI_3_1d"\) < ([0-9.]+)\)')


def _strategy() -> NostalgiaForInfinityX8:
  return NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)


def _block() -> str:
  src = STRATEGY.read_text()
  start = src.index("# Condition #170 - Crash-bounce hunter")
  end = src.index("# Condition #171 - Pump hunter", start)
  return src[start:end]


def _daily(closes: list[float], start: str = "2024-01-01") -> pd.DataFrame:
  dates = pd.date_range(start, periods=len(closes), freq="D", tz="UTC")
  return pd.DataFrame({"date": dates, "open": closes, "high": closes, "low": closes, "close": closes, "volume": 1.0})


@pytest.fixture
def strategy_config(tmp_path):
  return {
    "exchange": {"name": "binance"},
    "runmode": RunMode.BACKTEST,
    "user_data_dir": tmp_path,
    "stake_currency": "USDT",
    "trading_mode": "futures",
  }


def test_daily_frame_is_built_only_when_the_signal_is_enabled(strategy_config, monkeypatch):
  # Given: the default build.
  default = NostalgiaForInfinityX8(strategy_config)
  # Then: it keeps the single BTC informative it has always used — the gate costs nothing until used.
  assert default.btc_info_timeframes == ["4h"]
  # When: an operator enables 170.
  monkeypatch.setattr(
    NostalgiaForInfinityX8,
    "long_entry_signal_params",
    {**NostalgiaForInfinityX8.long_entry_signal_params, "long_entry_condition_170_enable": True},
  )
  enabled = NostalgiaForInfinityX8(strategy_config)
  # Then: the daily frame is requested, because the gate reads it.
  assert enabled.btc_info_timeframes == ["4h", "1d"]


def test_switcher_routes_the_daily_frame():
  strategy = _strategy()
  frame = _daily([100.0, 101.0, 99.0, 98.0, 97.0, 96.0, 95.0])
  strategy.dp = SimpleNamespace(get_pair_dataframe=lambda **kwargs: frame.copy())
  # When: the real switcher resolves the daily timeframe.
  result = strategy.btc_info_switcher("BTC/USDT:USDT", "1d")
  # Then: it returns the published daily column, not an empty frame / exception.
  assert not result.empty
  assert "BTC_RSI_3" in result.columns


def test_daily_rsi_uses_the_fast_period():
  # Given: a monotone daily series, so a 3-period RSI must sit at its maximum.
  strategy = _strategy()
  frame = _daily([100.0 + i for i in range(30)])
  strategy.dp = SimpleNamespace(get_pair_dataframe=lambda **kwargs: frame.copy())
  result = strategy.btc_info_switcher("BTC/USDT:USDT", "1d")
  expected = ta.RSI(frame["close"].to_numpy(copy=False), timeperiod=3)
  np.testing.assert_allclose(result["BTC_RSI_3"].to_numpy(), expected, equal_nan=True)
  assert result["BTC_RSI_3"].iloc[-1] > 99.0


def test_gate_reads_the_previous_closed_daily_candle():
  # Given: two daily histories that differ only in the CURRENT day's candle.
  base = [100.0, 101.0, 100.5, 102.0, 101.0]
  calm = _daily(base + [103.0, 104.0])
  crash = _daily(base + [60.0, 55.0])
  intraday = pd.DataFrame(
    {"date": pd.date_range("2024-01-06", "2024-01-07 23:55", freq="5min", tz="UTC"), "open": 1.0, "close": 1.0}
  )
  merged = {}
  for name, daily in (("calm", calm), ("crash", crash)):
    daily = daily.copy()
    daily["BTC_RSI_3"] = ta.RSI(daily["close"].to_numpy(copy=False), timeperiod=3)
    frame = merge_informative_pair(intraday.copy(), daily, "5m", "1d", ffill=False)
    merged[name] = frame.ffill()
  # When: reading the column inside the day whose candle is the crash.
  day = merged["calm"]["date"].dt.date == pd.Timestamp("2024-01-06").date()
  before_daily_close = day & (merged["calm"]["date"].dt.strftime("%H:%M") != "23:55")
  # Then: all day long the value cannot move, because that daily candle is still open (no lookahead)
  np.testing.assert_array_equal(
    merged["calm"].loc[before_daily_close, "BTC_RSI_3_1d"].to_numpy(),
    merged["crash"].loc[before_daily_close, "BTC_RSI_3_1d"].to_numpy(),
  )
  # Then: once the daily candle is closed, the gate reads it — the crash reaches the next day...
  next_day = merged["calm"]["date"].dt.date == pd.Timestamp("2024-01-07").date()
  assert merged["calm"].loc[next_day, "BTC_RSI_3_1d"].iloc[0] != merged["crash"].loc[next_day, "BTC_RSI_3_1d"].iloc[0]
  # ...and the library lands each daily candle on the last base candle of its own day (5m grid),
  # which is the same clock the strategy runs on, not an extra day of hindsight.
  assert merged["crash"].loc[day, "BTC_RSI_3_1d"].iloc[-1] < 42.0


def test_gate_is_the_last_clause_of_the_entry_logic():
  block = _block()
  logic = block.split("# Logic")[1]
  # Then: the gate is part of the Logic (not a decorative protection chain)...
  assert GATE.search(logic)
  # ...and it only narrows the entry: it is appended after the reclaim confirmation.
  assert logic.index("(close > np_shift(high_px, 1))") < logic.index('np_view("BTC_RSI_3_1d")')
  # The protection block above the Logic stays free of raw indicator reads.
  assert "np_view(" not in block.split("# Logic")[0]


def test_threshold_stays_inside_the_measured_plateau():
  # Measured at 38 / 42 / 46 on the five deciding chunks: the three cutoffs remove the same
  # losers and differ by 0.6% of profit, so the shipped number must stay inside that band.
  match = GATE.search(_block())
  assert match, "gate missing"
  assert 38.0 <= float(match.group(1)) <= 46.0


def test_signal_is_still_disabled_by_default():
  # The gate hardens an experimental signal; turning it on is an operator decision.
  assert NostalgiaForInfinityX8.long_entry_signal_params["long_entry_condition_170_enable"] is False
