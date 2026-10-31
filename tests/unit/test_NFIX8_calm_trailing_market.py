from datetime import timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import CandleType
from freqtrade.enums import RunMode
from pandas.testing import assert_frame_equal

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


FLAG = "risk_calm_trail_enable"
COLUMNS = ["MKT_STRESS_1d"]
A = "A/USDT"
B = "B/USDT"
BTC = "BTC/USDT"


def candles(close=70.0, count=54):
  return pd.DataFrame(
    {
      "date": pd.date_range("2026-01-01", periods=count, freq="1D", tz="UTC"),
      "high": [100.0] * count,
      "close": [close] * count,
    }
  )


@pytest.fixture
def market():
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.config = {
    "stake_currency": "USDT",
    "runmode": RunMode.DRY_RUN,
    "timeframe": "5m",
    "candle_type_def": CandleType.SPOT,
    "exchange": {"name": "binance"},
  }
  frames = {A: candles(), B: candles(75.0), BTC: candles(100.0)}
  pairs = MagicMock()
  pairs.whitelist = [A, B]
  exchange = MagicMock()
  exchange.klines.side_effect = lambda key, copy=True: (frames[key[0]].copy() if key[1] == "1d" else pd.DataFrame())
  strategy.dp = DataProvider(strategy.config, exchange, pairs)
  return strategy, frames, pairs


def test_maturity_requires_fifty_nonmissing_candles(market):
  strategy, _, _ = market
  daily = strategy.market_health_1d()
  assert daily.loc[:48, "MKT_STRESS"].isna().all()
  assert daily.loc[49, "MKT_STRESS"] == 50.0
  assert list(daily.columns) == ["date", "MKT_STRESS"]


@pytest.mark.parametrize("close,expected", [(74.999, 50.0), (75.0, 0.0), (75.001, 0.0)])
def test_drawdown_is_strictly_below_twenty_five_percent(market, close, expected):
  strategy, frames, _ = market
  frames[A]["close"] = close
  assert strategy.market_health_1d().iloc[-1]["MKT_STRESS"] == expected


def test_high_rolls_out_after_thirty_daily_rows(market):
  strategy, frames, _ = market
  frames[A]["high"] = 80.0
  frames[A].loc[23, "high"] = 200.0
  daily = strategy.market_health_1d()
  assert daily.loc[52, "MKT_STRESS"] == 50.0
  assert daily.loc[53, "MKT_STRESS"] == 0.0


def test_old_missing_candle_delays_maturity_without_resetting_it(market):
  strategy, frames, _ = market
  frames[A] = frames[A].drop(index=5)
  daily = strategy.market_health_1d()
  assert daily.loc[49, "MKT_STRESS"] == 0.0
  assert daily.loc[50, "MKT_STRESS"] == 50.0


def test_recent_gap_does_not_forward_fill_price_or_rolling_high(market):
  strategy, frames, _ = market
  frames[A] = frames[A].drop(index=51)
  frames[B].loc[52, "close"] = float("nan")
  daily = strategy.market_health_1d()
  assert daily.loc[51, "MKT_STRESS"] == 0.0
  assert pd.isna(daily.loc[52, "MKT_STRESS"])
  assert daily.loc[53, "MKT_STRESS"] == 0.0


def test_missing_btc_yields_unknown_without_changing_constituent_eligibility(market):
  strategy, frames, _ = market
  frames[BTC] = frames[BTC].iloc[:0]
  missing = strategy.market_health_1d()
  assert missing.empty
  base = pd.DataFrame({"date": [frames[A]["date"].iloc[-1] + timedelta(days=1)]})
  assert strategy.merge_market_health(base, missing)[COLUMNS].isna().all().all()
  frames[BTC] = candles(100.0, count=1)
  assert strategy.market_health_1d().iloc[-1]["MKT_STRESS"] == 50.0


def test_future_rows_cannot_change_daily_prefix(market):
  strategy, frames, _ = market
  full = strategy.market_health_1d().iloc[:52].reset_index(drop=True)
  for pair in frames:
    frames[pair] = frames[pair].iloc[:52].copy()
  prefix = strategy.market_health_1d()
  assert_frame_equal(prefix, full)


def test_cache_is_cycle_snapshot_then_revalidates_source_bytes_and_whitelist(market):
  strategy, frames, pairs = market
  cycle = frames[A]["date"].iloc[-1] + timedelta(days=1)
  first = strategy.market_health_1d(cycle)
  frames[B].loc[53, "high"] = 101.0
  assert strategy.market_health_1d(cycle) is first
  updated = strategy.market_health_1d(cycle + timedelta(minutes=5))
  assert updated.iloc[-1]["MKT_STRESS"] == 100.0
  assert strategy.market_health_1d() is updated
  frames[B].loc[53, "high"] = 100.0
  assert strategy.market_health_1d().iloc[-1]["MKT_STRESS"] == 50.0
  pairs.whitelist = [B]
  assert strategy.market_health_1d(cycle).iloc[-1]["MKT_STRESS"] == 0.0


def test_actual_daily_builder_publishes_at_daily_close_and_expires(market):
  strategy, _, _ = market
  daily = strategy.market_health_1d().tail(1)
  day = daily["date"].iloc[0]
  base = pd.DataFrame(
    {
      "date": [day + timedelta(minutes=offset) for offset in (1430, 1435, 2870, 2875)],
    },
    index=[4, 6, 8, 10],
  )
  merged = strategy.merge_market_health(base, daily)
  assert merged.index.equals(base.index)
  assert merged.loc[[4, 10], COLUMNS].isna().all().all()
  assert merged.loc[[6, 8], COLUMNS].eq(50.0).all().all()
  assert list(merged.columns) == ["date", *COLUMNS]


@pytest.mark.parametrize("enabled", [False, True])
def test_informative_pairs_only_adds_btc_daily_when_enabled(market, enabled):
  strategy, _, _ = market
  setattr(strategy, FLAG, False)
  original = set(strategy.informative_pairs())
  setattr(strategy, FLAG, enabled)
  expected = original | ({(BTC, "1d")} if enabled else set())
  assert set(strategy.informative_pairs()) == expected
  assert (BTC, "5m") in original


@pytest.mark.parametrize("enabled", [False, True])
def test_populate_indicators_real_market_wiring_never_forward_fills_expired_scores(market, monkeypatch, enabled):
  strategy, frames, _ = market
  setattr(strategy, FLAG, False)
  monkeypatch.setattr(strategy, "btc_info_switcher", MagicMock(return_value=pd.DataFrame()))
  monkeypatch.setattr(strategy, "info_switcher", MagicMock(return_value=pd.DataFrame()))
  monkeypatch.setattr(strategy, "base_tf_5m_indicators", lambda metadata, frame: frame)
  day = frames[A]["date"].iloc[-1]
  base = pd.DataFrame(
    {
      "date": [day + timedelta(minutes=offset) for offset in (1435, 2870, 2875)],
      "close": [10.0, 10.0, 10.0],
    }
  )
  native_result = strategy.populate_indicators(base.copy(), {"pair": A})
  strategy.dp._exchange.klines.reset_mock()
  setattr(strategy, FLAG, enabled)
  if not enabled:
    monkeypatch.setattr(strategy, "market_health_1d", MagicMock(side_effect=AssertionError))
    monkeypatch.setattr(strategy, "merge_market_health", MagicMock(side_effect=AssertionError))
  result = strategy.populate_indicators(base, {"pair": A})
  assert "btc_roc_1_5m" in result
  if enabled:
    assert result.loc[:1, COLUMNS].eq(50.0).all().all()
    assert result.loc[2, COLUMNS].isna().all()
    assert set(result.columns) - set(native_result.columns) == set(COLUMNS)
    assert_frame_equal(result.drop(columns=COLUMNS), native_result)
  else:
    assert_frame_equal(result, native_result)
    assert not set(COLUMNS).intersection(result.columns)
    assert [call.args[0][1] for call in strategy.dp._exchange.klines.call_args_list] == ["5m"]


@pytest.mark.parametrize("style", ["default", "top_level", "nfi_parameters"])
def test_constructor_supports_safe_opt_in_with_default_off(tmp_path, monkeypatch, style):
  monkeypatch.setattr(NostalgiaForInfinityX8, "target_profit_cache", None)
  monkeypatch.setattr(NostalgiaForInfinityX8, "hold_trades_cache", None)
  config = {
    "exchange": {"name": "binance"},
    "runmode": RunMode.BACKTEST,
    "user_data_dir": tmp_path,
    "stake_currency": "USDT",
    "trading_mode": "futures",
  }
  if style == "top_level":
    config[FLAG] = True
  if style == "nfi_parameters":
    config["nfi_parameters"] = {FLAG: True}
  strategy = NostalgiaForInfinityX8(config)
  assert getattr(strategy, FLAG) is (style != "default")
