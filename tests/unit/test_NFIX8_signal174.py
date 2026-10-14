from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


@pytest.fixture
def hourly_frame():
  frame = pd.DataFrame(
    {
      "date": pd.date_range("2024-01-01", periods=240, freq="h", tz="UTC"),
      "open": 100.0,
      "high": 101.0,
      "low": 99.0,
      "close": 100.0,
      "volume": 100.0,
    }
  )
  frame.loc[219, ["high", "low"]] = [100.5, 99.5]
  frame.loc[220, ["open", "high", "low", "close"]] = [102.0, 102.2, 101.8, 102.0]
  frame.loc[221, ["open", "high", "low", "close"]] = [102.5, 104.0, 102.0, 103.0]
  return frame


@pytest.fixture
def hourly_strategy(hourly_frame):
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.long_entry_signal_params = {
    **NostalgiaForInfinityX8.long_entry_signal_params,
    "long_entry_condition_174_enable": True,
  }
  strategy.dp = SimpleNamespace(get_pair_dataframe=lambda **kwargs: hourly_frame.copy())
  return strategy


def test_hourly_breakout_emits_only_first_closed_hour(hourly_strategy):
  # Given: two consecutive breakouts, both preceded by a narrower candle.
  # When: the real informative indicator pipeline calculates the event.
  result = hourly_strategy.informative_1h_indicators({"pair": "BTC/USDT:USDT"}, "1h")
  # Then: the continuing breakout does not re-arm the event. The column is 0/1 float and is
  # read `> 0.5`, like the other pattern columns, so select on it the same way.
  assert result.index[result["s174_event"] > 0.5].tolist() == [220]


@pytest.mark.parametrize("defect", ["gap", "equal_range", "equal_high", "zero_volume", "nan", "infinity"])
def test_hourly_breakout_rejects_invalid_setup(hourly_frame, hourly_strategy, defect):
  # Given: one required setup invariant fails.
  if defect == "gap":
    hourly_frame.loc[210:, "date"] += pd.Timedelta(hours=1)
  elif defect == "equal_range":
    hourly_frame.loc[219, ["high", "low"]] = [101.0, 99.0]
  elif defect == "equal_high":
    hourly_frame.loc[220, ["open", "low", "close"]] = [101.0, 100.0, 101.0]
  elif defect == "zero_volume":
    hourly_frame.loc[210, "volume"] = 0.0
  elif defect == "nan":
    hourly_frame.loc[210, "close"] = np.nan
  elif defect == "infinity":
    hourly_frame.loc[210, "high"] = np.inf
  # When: the real indicator pipeline runs.
  result = hourly_strategy.informative_1h_indicators({"pair": "BTC/USDT:USDT"}, "1h")
  # Then: the affected breakout is not admitted.
  assert not result.loc[220, "s174_event"]


def test_hourly_breakout_does_not_read_future_candles(hourly_frame, hourly_strategy):
  # Given: the event and its history are fixed.
  before = hourly_strategy.informative_1h_indicators({"pair": "BTC/USDT:USDT"}, "1h")["s174_event"]
  hourly_frame.loc[221:, ["open", "high", "low", "close"]] = [200.0, 210.0, 190.0, 205.0]
  # When: only future candles change.
  after = hourly_strategy.informative_1h_indicators({"pair": "BTC/USDT:USDT"}, "1h")["s174_event"]
  # Then: already-closed events are unchanged.
  pd.testing.assert_series_equal(before.loc[:220], after.loc[:220])


def test_hourly_breakout_is_disabled_by_default(hourly_strategy):
  # Given: the actual default signal configuration.
  hourly_strategy.long_entry_signal_params = NostalgiaForInfinityX8.long_entry_signal_params.copy()
  # When: indicators are calculated without enabling 174.
  result = hourly_strategy.informative_1h_indicators({"pair": "BTC/USDT:USDT"}, "1h")
  # Then: the entry stays off, while the pattern column is still computed — unconditionally,
  # as 0/1 float — like the other dispatch-loop signals.
  assert NostalgiaForInfinityX8.long_entry_signal_params["long_entry_condition_174_enable"] is False
  assert result["s174_event"].dtype == "float64"
  assert set(result["s174_event"].unique()) <= {0.0, 1.0}


def test_hourly_breakout_empty_frame(hourly_frame, hourly_strategy):
  # Given: an empty informative response.
  hourly_strategy.dp = SimpleNamespace(get_pair_dataframe=lambda **kwargs: hourly_frame.iloc[:0].copy())
  # When: the real informative path executes.
  result = hourly_strategy.informative_1h_indicators({"pair": "BTC/USDT:USDT"}, "1h")
  # Then: it remains empty and provides the event column, as 0/1 float.
  assert result.empty and result["s174_event"].dtype == "float64"
