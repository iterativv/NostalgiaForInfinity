"""Callback-price lifecycle probes, without inferred intrabar fills."""

import copy
from datetime import timedelta
import pytest
from freqtrade.persistence import Trade

from tests.unit import calm_trailing_fixtures as f

database = f.database


@pytest.mark.parametrize("leverage", [1.0, 3.0])
@pytest.mark.parametrize("rate,exits", [(160.00001, False), (160.0, True), (159.99, True)])
def test_price_boundary_when_peak_observed(database, tmp_path, leverage, rate, exits):
  # Given
  case = f.make_case(tmp_path)
  case.trade.leverage = leverage
  case.trade.max_rate = 900.0
  case.emit()
  case.call()
  assert case.marker()["peak"] == 110.0
  case.native.side_effect = None
  case.call(60, 200.0)
  case.call(120, 180.0)
  # When
  result = case.call(180, rate)
  # Then
  assert result == (f.REASON if exits else None)
  assert case.marker()["peak"] == 200.0


@pytest.mark.parametrize("stress", [20.0, 20.0001, None, float("nan"), float("inf"), -float("inf"), "missing"])
def test_permanent_cancellation_when_calm_lost(database, tmp_path, stress):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.native.side_effect = None
  case.analyzed(stress if stress != "missing" else 19.0)
  if stress == "missing":
    frame, _ = case.strategy.dp.get_analyzed_dataframe.return_value
    case.strategy.dp.get_analyzed_dataframe.return_value = frame.drop(columns="MKT_STRESS_1d"), None
  # When
  result = case.call(60, 80.0)
  # Then
  assert result is None
  assert case.marker()["active"] is False
  assert case.marker()["episode"] is False


def test_no_rearm_when_calm_returns_after_cancellation(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.analyzed(20.0)
  case.native.side_effect = None
  case.call(60)
  case.analyzed()
  case.emit("exit_long_normal_1_1_1", f.NOW + timedelta(seconds=120))
  # When
  result = case.call(120, 80.0)
  # Then
  assert result is None
  assert case.marker()["active"] is False
  assert case.marker()["reason"] == f.TARGET


@pytest.mark.parametrize("rate", [0.0, -1.0, float("nan"), float("inf"), -float("inf")])
def test_cancellation_when_active_callback_rate_invalid(database, tmp_path, rate):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.native.side_effect = None
  # When
  result = case.call(60, rate, current_profit=0.0)
  # Then
  assert result is None
  assert case.marker()["active"] is False


def test_no_second_opportunity_when_first_ineligible(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.analyzed(20.0)
  case.emit()
  case.call()
  case.strategy._remove_profit_target(case.trade.pair)
  case.analyzed()
  case.emit("exit_long_normal_1_1_1", f.NOW + timedelta(seconds=60))
  # When
  case.call(60)
  # Then
  assert case.marker()["active"] is False
  assert case.marker()["reason"] == f.TARGET


def test_intent_retry_when_calm_and_rate_become_invalid(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.native.side_effect = None
  assert case.call(60, 88.0) == f.REASON
  case.analyzed(float("nan"))
  # When
  result = case.call(120, float("nan"), current_profit=0.0)
  # Then
  assert result == f.REASON
  assert case.marker()["pending"] == f.REASON


@pytest.mark.parametrize("native", ["protective", "", False, True, 0])
def test_native_priority_when_intent_pending(database, tmp_path, native):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.native.side_effect = None
  case.call(60, 88.0)
  case.native.reset_mock()
  case.native.return_value = native
  # When
  result = case.call(120, 80.0, callback_token=17)
  # Then
  assert result is native
  case.native.assert_called_once()
  assert case.native.call_args.kwargs["callback_token"] == 17


def test_resume_when_disabled_high_was_unobserved(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.native.side_effect = None
  saved = copy.deepcopy(case.marker())
  case.strategy.risk_calm_trail_enable = False
  case.call(60, 1000.0)
  assert case.marker() == saved
  case.strategy.risk_calm_trail_enable = True
  # When
  result = case.call(120, 90.0)
  # Then
  assert result is None
  assert case.marker()["peak"] == 110.0


def test_trade_reload_when_peak_persisted(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.native.side_effect = None
  case.call(60, 200.0)
  trade_id = case.trade.id
  Trade.session.commit()
  Trade.session.expunge_all()
  case.trade = Trade.session.get(Trade, trade_id)
  case.strategy.target_profit_cache = f.MODULE.Cache(case.strategy.target_profit_cache.path)
  # When
  result = case.call(120, 160.0)
  # Then
  assert result == f.REASON


def test_new_trade_when_same_pair_reused(database, tmp_path):
  # Given
  old = f.make_case(tmp_path / "old")
  old.emit()
  old.call()
  old.trade.is_open = False
  fresh = f.make_case(tmp_path / "new")
  # When
  result = fresh.call(60, 80.0)
  # Then
  assert result is None
  assert fresh.marker() is None


def test_pending_intent_when_disabled_then_reenabled(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.native.side_effect = None
  case.call(60, 88.0)
  saved = copy.deepcopy(case.marker())
  case.strategy.risk_calm_trail_enable = False
  assert case.call(120, 80.0) is None
  assert case.marker() == saved
  case.strategy.risk_calm_trail_enable = True
  case.analyzed(None)
  # When
  result = case.call(180, 110.0)
  # Then
  assert result == f.REASON
