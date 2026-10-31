"""Admission/configuration probes using real persistent Trade records."""

from datetime import timedelta

import pandas as pd
import pytest
from freqtrade.enums import RunMode

from tests.unit import calm_trailing_fixtures as f

database = f.database


@pytest.mark.parametrize("setting", ["absent", False, True, "nested"])
def test_safe_constructor_when_overlay_supplied(tmp_path, monkeypatch, setting):
  # Given
  monkeypatch.setattr(f.Strategy, "target_profit_cache", None)
  monkeypatch.setattr(f.Strategy, "hold_trades_cache", None)
  config = {
    "exchange": {"name": "binance"},
    "runmode": RunMode.BACKTEST,
    "user_data_dir": tmp_path,
    "stake_currency": "USDT",
    "trading_mode": "futures",
    "nfi_advanced_mode": False,
  }
  config.pop("risk_calm_trail_enable", None)
  config.pop("nfi_parameters", None)
  if setting == "nested":
    config["nfi_parameters"] = {"risk_calm_trail_enable": True}
  elif setting in (True, False):
    config["risk_calm_trail_enable"] = setting
  # When
  strategy = f.Strategy(config)
  # Then
  assert f.Strategy.risk_calm_trail_enable is False
  assert strategy.risk_calm_trail_enable is (setting is True or setting == "nested")


@pytest.mark.parametrize(
  "stress", [19.9999, 20.0, 20.0001, None, float("nan"), float("inf"), -float("inf"), "missing"]
)
@pytest.mark.parametrize("enabled,short", [(True, False), (False, False), (True, True)])
def test_admission_when_calm_boundary_observed(database, tmp_path, stress, enabled, short):
  # Given
  case = f.make_case(tmp_path, enabled, short)
  case.analyzed(stress if stress != "missing" else 19.0)
  if stress == "missing":
    frame, _ = case.strategy.dp.get_analyzed_dataframe.return_value
    case.strategy.dp.get_analyzed_dataframe.return_value = frame.drop(columns="MKT_STRESS_1d"), None
  case.emit()
  # When
  result = case.call()
  # Then
  assert result is None
  marker = case.marker()
  if enabled and not short:
    assert marker["active"] is (stress == 19.9999)
    assert marker["consumed"] is True
  else:
    assert marker is None
    case.strategy.dp.get_analyzed_dataframe.assert_not_called()
  case.native.assert_called_once()


@pytest.mark.parametrize("mode", ["normal", "pump", "quick", "rebuy", "hp", "rapid", "grind", "btc", "tc", "scalp"])
@pytest.mark.parametrize("named", [False, True])
def test_first_generic_or_named_tracking_when_committed(database, tmp_path, mode, named):
  # Given
  case = f.make_case(tmp_path)
  reason = f"exit_long_{mode}_1_1_1" if named else f"exit_profit_long_{mode}_max"
  case.emit(reason)
  # When
  case.call()
  # Then
  assert case.marker()["active"] is True
  assert case.marker()["reason"] == reason
  assert case.marker()["peak"] == 110.0
  assert case.strategy.target_profit_cache.data[case.trade.pair]["sell_reason"] == reason


@pytest.mark.parametrize(
  "reason",
  [
    "exit_long_scalp_stoploss_doom",
    "exit_long_normal_stoploss",
    "exit_long_scalp_stoploss_u_e",
    "exit_long_normal_doom",
    "exit_long_abandon",
    "exit_short_scalp_max",
    "unrelated_max",
  ],
)
def test_excluded_target_when_committed(database, tmp_path, reason):
  # Given
  case = f.make_case(tmp_path)
  case.emit(reason)
  # When
  case.call()
  # Then
  assert case.marker() is None


@pytest.mark.parametrize("profit", [0.0, -0.01])
def test_nonpositive_target_when_committed(database, tmp_path, profit):
  # Given
  case = f.make_case(tmp_path)
  case.emit(profit=profit)
  # When
  case.call()
  # Then
  assert case.marker() is None


@pytest.mark.parametrize("age", [timedelta(minutes=1), timedelta(days=3)])
def test_stale_commit_when_timestamp_precedes_callback(database, tmp_path, age):
  # Given
  case = f.make_case(tmp_path)
  case.emit(stamp=f.NOW - age)
  # When
  case.call()
  # Then
  assert case.marker() is None


def test_existing_current_trade_target_when_first_enabled(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.target(stamp=f.NOW - timedelta(minutes=5))
  case.emit(profit=0.03)
  # When
  case.call()
  # Then
  assert case.marker()["consumed"] is True
  assert case.marker()["active"] is False


def test_prior_trade_cache_when_replaced_by_current_commit(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.target(stamp=f.NOW - timedelta(days=3))
  case.emit()
  # When
  case.call()
  # Then
  assert case.marker()["active"] is True


@pytest.mark.parametrize("rows", [0, 1])
def test_insufficient_rows_when_first_opportunity_observed(database, tmp_path, rows):
  # Given
  case = f.make_case(tmp_path)
  case.strategy.dp.get_analyzed_dataframe.return_value = pd.DataFrame([{"MKT_STRESS_1d": 19.0}] * rows), None
  case.emit()
  # When
  case.call()
  # Then
  assert case.marker()["active"] is False
  assert case.marker()["consumed"] is True


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_consumed_opportunity_when_admission_rate_invalid(database, tmp_path, rate):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  # When
  case.call(rate=rate, current_profit=0.0)
  # Then
  assert case.marker()["consumed"] is True
  assert case.marker()["active"] is False


@pytest.mark.parametrize("profit", [float("nan"), float("inf"), -float("inf")])
def test_native_cache_failure_when_nonfinite_target_written(database, tmp_path, profit):
  # Given
  case = f.make_case(tmp_path)
  case.emit(profit=profit)
  # When
  with pytest.raises(ValueError):
    case.call()
  # Then
  case.native.assert_called_once()
  assert case.marker() is None
