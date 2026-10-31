"""Actual pinned DataProvider/cache and merge boundaries; no exchange requests."""

from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import CandleType, RunMode
from freqtrade.strategy import merge_informative_pair
from pandas.testing import assert_frame_equal

from tests.unit import residual_profit_fixtures as f

database = f.database
PAIRS = ("ETH/USDT:USDT", "BTC/USDT:USDT", "SOL/USDT:USDT")
HOUR = pd.Timedelta(hours=1)
START = pd.Timestamp(f.NOW) - 1501 * HOUR


def history(rows=1700):
  dates = pd.date_range(START, periods=rows, freq="1h")
  t = np.arange(rows, dtype=float)
  market = 0.001 * np.sin(t / 11.0) + 0.0003 * np.cos(t / 5.0)
  moves = (
    market + 0.0007 * np.sin(t / 3.0),
    market - 0.0005 * np.cos(t / 7.0),
    market + 0.0004 * np.sin(t / 17.0),
  )
  frames = {
    pair: pd.DataFrame({"date": dates, "close": 100.0 * np.cumprod(1.0 + move)})
    for pair, move in zip(PAIRS, moves, strict=True)
  }
  if rows > 1500:
    frames[PAIRS[0]].loc[1500:, "close"] *= np.power(1.01, np.arange(1, rows - 1500 + 1))
  return frames


def base(start=0, stop=1700):
  dates = pd.date_range(START + start * HOUR, START + stop * HOUR, freq="5min", inclusive="left")
  return pd.DataFrame({"date": dates, "close": 110.0, "native_surface": 17.0})


def provider_strategy(frames, runmode=RunMode.BACKTEST):
  strategy = f.Strategy.__new__(f.Strategy)
  strategy.risk_residual_first_target_exit_enable = True
  strategy.config = {
    "runmode": runmode,
    "timeframe": "5m",
    "candle_type_def": CandleType.FUTURES,
    "trading_mode": "futures",
    "exchange": {"name": "binance"},
  }
  # Only the external Exchange data boundary is controlled. DataProvider's
  # current_whitelist/get_pair_dataframe/historic_ohlcv/ohlcv/cache code is real.
  store = {(pair, "1h", CandleType.FUTURES): frame.copy(deep=True) for pair, frame in frames.items()}
  exchange = SimpleNamespace(
    klines=MagicMock(side_effect=lambda key, copy=True: store[key].copy(deep=copy)),
  )
  pairlists = SimpleNamespace(whitelist=list(frames))
  strategy.dp = DataProvider(strategy.config, exchange, pairlists)
  strategy.dp._DataProvider__cached_pairs_backtesting.update(store)
  strategy.dp.get_pair_dataframe = MagicMock(wraps=strategy.dp.get_pair_dataframe)
  strategy._r_native_populate_indicators = MagicMock(side_effect=lambda frame, metadata: frame)
  return strategy, store


def feed(strategy, store, frames):
  for pair, frame in frames.items():
    key = (pair, "1h", CandleType.FUTURES)
    store[key] = frame.copy(deep=True)
    strategy.dp._DataProvider__cached_pairs_backtesting[key] = frame.copy(deep=True)


def table(rows):
  return pd.DataFrame([asdict(row) for row in rows])


def test_offline_full_cross_section_once_and_different_pair_endpoints():
  frames = history()
  before = {pair: frame.copy(deep=True) for pair, frame in frames.items()}
  strategy, _ = provider_strategy(frames)
  original = f.MODULE.RHourlyState.update
  calls = []

  def update(owner, prepared, whitelist, cutoff):
    assert set(prepared) == set(PAIRS)
    assert strategy.dp.get_pair_dataframe.call_count == len(PAIRS)
    calls.append(cutoff)
    return original(owner, prepared, whitelist, cutoff)

  with patch.object(f.MODULE.RHourlyState, "update", update):
    first = strategy.populate_indicators(base(1400, 1600), {"pair": PAIRS[0]})
    owner = strategy._r_hourly_owner
    snapshot = strategy._r_hourly_surface
    earlier = strategy.populate_indicators(base(1400, 1530), {"pair": PAIRS[1]})
    later = strategy.populate_indicators(base(1400, 1700), {"pair": PAIRS[2]})
  assert calls == [START + 1700 * HOUR]
  assert strategy._r_hourly_owner is owner
  assert strategy._r_hourly_surface is snapshot
  assert len(snapshot[PAIRS[0]]) == 1700
  assert strategy.dp.get_pair_dataframe.call_count == len(PAIRS)
  assert first["R_Z"].notna().any() and earlier["R_Z"].notna().any() and later["R_Z"].notna().any()
  assert (first["native_surface"] == 17.0).all()
  for pair in PAIRS:
    assert_frame_equal(frames[pair], before[pair], check_exact=True)
  reference = f.MODULE.RHourlyState(PAIRS).update(frames, PAIRS, START + 1700 * HOUR)
  assert_frame_equal(table(snapshot[PAIRS[1]]), table(reference[PAIRS[1]]), check_exact=True)


def test_provider_prefix_future_perturbation_and_no_source_mutation():
  frames = history()
  prefix = {pair: frame.iloc[:1550].copy() for pair, frame in frames.items()}
  altered = {pair: frame.copy(deep=True) for pair, frame in frames.items()}
  for frame in altered.values():
    frame.loc[1550:, "close"] = 1e50
  left, _ = provider_strategy(prefix)
  right, _ = provider_strategy(altered)
  candles = base(1400, 1550)
  expected = left.populate_indicators(candles.copy(), {"pair": PAIRS[0]})
  actual = right.populate_indicators(candles.copy(), {"pair": PAIRS[0]})
  assert_frame_equal(actual, expected, check_exact=True)
  assert_frame_equal(candles, base(1400, 1550), check_exact=True)


def test_real_framework_0055_close_availability_and_missing_hour_expiry():
  frames = history(1)
  strategy, _ = provider_strategy(frames)
  available = START + HOUR
  row = f.MODULE.HourlyReading(
    START,
    available,
    3,
    0.01,
    0.02,
    1.0,
    0.01,
    0.001,
    10.0,
    0.0,
    True,
  )
  # Isolate the merge boundary, not detector arithmetic.
  strategy._r_hourly_surface = {pair: (row,) for pair in PAIRS}
  strategy._r_whitelist = tuple(sorted(PAIRS))
  strategy._r_cutoff = START + 3 * HOUR
  candles = base(0, 3)
  merged = strategy._r_merge_hourly(candles, {"pair": PAIRS[0]})
  first = merged.loc[merged["R_UP_ALARM"], "date"].iloc[0]
  assert first == START + pd.Timedelta(minutes=55)
  framework = merge_informative_pair(
    candles.copy(),
    pd.DataFrame([asdict(row)]),
    "5m",
    "1h",
    ffill=True,
  )
  within = (candles["date"] >= START + pd.Timedelta(minutes=55)) & (
    candles["date"] < START + pd.Timedelta(hours=1, minutes=55)
  )
  assert merged.loc[within, "R_UP_ALARM"].tolist() == framework.loc[within, "R_UP_ALARM_1h"].tolist()
  assert not merged.loc[candles["date"] < START + pd.Timedelta(minutes=55), "R_UP_ALARM"].any()
  expired = merged["date"] >= START + pd.Timedelta(hours=1, minutes=55)
  assert not merged.loc[expired, "R_UP_ALARM"].any()
  assert merged.loc[expired, "R_AVAILABLE_AT"].isna().all()


def test_live_rolling_owner_matches_full_prefix_without_replaying():
  frames = history()
  expected = f.MODULE.RHourlyState(PAIRS).update(frames, PAIRS, START + 1700 * HOUR)
  source = {pair: frame.iloc[:1490] for pair, frame in frames.items()}
  strategy, store = provider_strategy(source, RunMode.DRY_RUN)
  strategy.populate_indicators(base(1480, 1490), {"pair": PAIRS[0]})
  owner = strategy._r_hourly_owner
  assert not owner._retain_history
  for stop in (1500, 1550, 1600, 1700):
    feed(strategy, store, {pair: frame.iloc[max(0, stop - 110) : stop] for pair, frame in frames.items()})
    result = strategy.populate_indicators(base(stop - 10, stop), {"pair": PAIRS[0]})
    assert strategy._r_hourly_owner is owner
    assert owner._last == START + (stop - 1) * HOUR
    assert np.isfinite(result["R_Z"].iloc[-1])
    assert result["R_Z"].iloc[-1] == expected[PAIRS[0]][stop - 1].R_Z
    assert bool(result["R_UP_ALARM"].iloc[-1]) == expected[PAIRS[0]][stop - 1].R_UP_ALARM
    calls = strategy.dp.get_pair_dataframe.call_count
    repeated = strategy.populate_indicators(base(stop - 10, stop), {"pair": PAIRS[0]})
    assert_frame_equal(repeated, result, check_exact=True)
    assert strategy.dp.get_pair_dataframe.call_count == calls
  assert len(owner._raw) == 721
  assert len(strategy._r_hourly_surface[PAIRS[0]]) <= 111
  assert all(not rows for rows in owner._rows.values())


def test_individual_and_whole_market_missing_hours_do_not_bridge():
  frames = history()
  frames[PAIRS[0]] = frames[PAIRS[0]].drop(index=1498)
  for pair in PAIRS:
    frames[pair] = frames[pair].drop(index=1500)
  strategy, _ = provider_strategy(frames)
  strategy.populate_indicators(base(1490, 1510), {"pair": PAIRS[0]})
  rows = strategy._r_hourly_surface[PAIRS[0]]
  assert rows[1498].R_MARKET_COUNT == 2
  assert np.isnan(rows[1498].R_RETURN) and np.isnan(rows[1499].R_RETURN)
  assert rows[1500].R_MARKET_COUNT == rows[1501].R_MARKET_COUNT == 0
  assert all(not row.R_UP_ALARM and np.isnan(row.R_Z) for row in rows[1498:1510])


def test_all_provider_frames_prepare_before_any_commit():
  frames = history(10)
  strategy, _ = provider_strategy(frames)
  actual = strategy.dp.get_pair_dataframe
  seen = []

  def interrupted(pair, timeframe):
    seen.append(pair)
    if len(seen) == 2:
      raise RuntimeError("provider frame unavailable")
    return actual(pair, timeframe)

  with patch.object(strategy.dp, "get_pair_dataframe", side_effect=interrupted):
    with pytest.raises(RuntimeError, match="provider frame unavailable"):
      strategy.populate_indicators(base(0, 10), {"pair": PAIRS[0]})
  assert not hasattr(strategy, "_r_hourly_owner")
  assert not hasattr(strategy, "_r_cutoff")
  result = strategy.populate_indicators(base(0, 10), {"pair": PAIRS[0]})
  assert result["R_Z"].isna().all()


@pytest.mark.parametrize("changed", ["add", "remove", "duplicate"])
def test_frozen_whitelist_rejects_change_before_provider_fetch(changed):
  strategy, _ = provider_strategy(history(10))
  strategy.populate_indicators(base(0, 10), {"pair": PAIRS[0]})
  owner = strategy._r_hourly_owner
  cutoff = owner._cutoff
  calls = strategy.dp.get_pair_dataframe.call_count
  whitelist = strategy.dp._pairlists.whitelist
  if changed == "add":
    whitelist.append("X/USDT:USDT")
  elif changed == "remove":
    whitelist.pop()
  else:
    whitelist.append(whitelist[0])
  with pytest.raises(ValueError):
    strategy.populate_indicators(base(0, 11), {"pair": PAIRS[0]})
  assert owner._cutoff == cutoff
  assert strategy.dp.get_pair_dataframe.call_count == calls


def test_new_short_buffer_owner_remains_unknown_not_fabricated_continuity():
  frames = history()
  frames = {pair: frame.iloc[-48:] for pair, frame in frames.items()}
  strategy, _ = provider_strategy(frames, RunMode.DRY_RUN)
  merged = strategy.populate_indicators(base(1690, 1700), {"pair": PAIRS[0]})
  assert merged["R_Z"].isna().all()
  assert not merged["R_UP_ALARM"].any()
  assert strategy.startup_candle_count == 800


@pytest.mark.parametrize("explicit", [False, True])
def test_default_off_indicator_surface_constructs_nothing_and_fetches_nothing(explicit):
  strategy, _ = provider_strategy(history(10))
  if explicit:
    strategy.risk_residual_first_target_exit_enable = False
  else:
    del strategy.risk_residual_first_target_exit_enable
  candles = base(0, 10)
  with (
    patch.object(f.MODULE, "RHourlyState", side_effect=AssertionError("OFF owner")),
    patch.object(
      strategy.dp,
      "get_pair_dataframe",
      side_effect=AssertionError("OFF raw access"),
    ),
    patch.object(strategy.dp, "current_whitelist", side_effect=AssertionError("OFF universe access")),
  ):
    result = strategy.populate_indicators(candles, {"pair": PAIRS[0]})
  assert result is candles
  strategy._r_native_populate_indicators.assert_called_once_with(candles, {"pair": PAIRS[0]})
  assert not hasattr(strategy, "_r_hourly_owner")
  assert not any(name.startswith("R_") for name in result)


def test_actual_provider_alarm_to_native_tracking_and_sqlite_intent(database, tmp_path):
  frames = history()
  strategy, _ = provider_strategy(frames)
  case = f.make_case(tmp_path)
  case.strategy.dp = strategy.dp
  case.strategy.config = strategy.config
  case.strategy._r_native_populate_indicators = strategy._r_native_populate_indicators
  merged = case.strategy.populate_indicators(base(1400, 1700), {"pair": PAIRS[0]})
  alarm = merged.loc[
    merged["R_UP_ALARM"]
    & (merged["date"] >= pd.Timestamp(f.NOW) - pd.Timedelta(hours=24))
    & (merged["date"] < pd.Timestamp(f.NOW))
  ].iloc[0]
  now = (alarm["date"] + pd.Timedelta(minutes=5)).to_pydatetime()
  case.cache(merged.loc[merged["date"] <= alarm["date"]])
  f.use_actual_scalp_tracker(case)
  assert (
    case.strategy.custom_exit(
      case.trade.pair,
      case.trade,
      now,
      110.0,
      case.trade.calc_profit_ratio(110.0),
    )
    == f.REASON
  )
  case.native.assert_called_once()
  assert case.marker() == f.REASON
  target = f.MODULE.Cache(case.strategy.target_profit_cache.path).data[case.trade.pair]
  assert target["time_profit_reached"] == now.isoformat()
  assert case.ledger()[0] == pytest.approx(98.95)
