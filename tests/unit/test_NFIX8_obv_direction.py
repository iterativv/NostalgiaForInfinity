import numpy as np
import pytest
import talib as ta

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


@pytest.mark.parametrize(
  "close,volume,expected",
  [
    ([], [], []),
    ([10], [5], [np.nan]),
    ([10, 11, 10, 10, 12], [5, 5, 5, 5, 0], [np.nan, 1, -1, 0, 0]),
    ([10, np.nan, 12, 13], [5, 5, 5, 5], [np.nan, np.nan, np.nan, 1]),
    ([10, 11, 12, 13], [5, np.inf, 5, 5], [np.nan, np.nan, 1, 1]),
  ],
)
def test_obv_direction_handles_unavailable_inputs_and_recovers(close, volume, expected):
  actual = NostalgiaForInfinityX8.obv_direction(np.array(close, dtype=float), np.array(volume, dtype=float))

  np.testing.assert_array_equal(actual, expected)


@pytest.mark.parametrize("cut", [1, 7, 19])
def test_obv_direction_is_independent_of_discarded_history_and_future_candles(cut):
  close = np.array([10, 11, 9, 9, 12, 10] * 8, dtype=float)
  volume = np.arange(1, len(close) + 1, dtype=float)
  volume[0] = 1e30
  full = NostalgiaForInfinityX8.obv_direction(close, volume)
  suffix = NostalgiaForInfinityX8.obv_direction(close[cut:], volume[cut:])

  assert np.isnan(suffix[0])
  np.testing.assert_array_equal(full[cut + 1 :], suffix[1:])
  np.testing.assert_array_equal(full[:25], NostalgiaForInfinityX8.obv_direction(close[:25], volume[:25]))


@pytest.mark.parametrize(
  "close,volume,expected_legacy",
  [
    ([10, 9, 10], [100, 100, 20], np.nan),
    ([1, 2, 3], [1e30, 1, 1], 0),
  ],
)
def test_obv_direction_survives_zero_cumulative_obv_and_lost_increments(close, volume, expected_legacy):
  close = np.array(close, dtype=float)
  volume = np.array(volume, dtype=float)
  cumulative = ta.OBV(close, volume)
  legacy = NostalgiaForInfinityX8.obv_change_pct(cumulative)[-1]

  np.testing.assert_equal(legacy, expected_legacy)
  assert NostalgiaForInfinityX8.obv_direction(close, volume)[-1] == 1


def test_obv_direction_matches_talib_movement_with_a_negative_cumulative_balance():
  close = np.array([10, 9, 8, 9, 9, 10], dtype=float)
  volume = np.array([1, 20, 30, 5, 5, 0], dtype=float)
  cumulative = ta.OBV(close, volume)
  assert cumulative[2] < 0
  percentage = NostalgiaForInfinityX8.obv_change_pct(cumulative)

  np.testing.assert_array_equal(NostalgiaForInfinityX8.obv_direction(close, volume)[1:], np.sign(percentage[1:]))
