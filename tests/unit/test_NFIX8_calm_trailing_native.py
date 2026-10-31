"""Real Native evaluator, ordering and cache-episode preservation probes."""

import copy
from unittest.mock import MagicMock, patch

import pytest

from tests.unit import calm_trailing_fixtures as f

database = f.database


def test_real_native_custom_exit_when_first_tracking_commits(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  f.actual_native(case)
  # When
  result = case.call()
  # Then
  assert result is None
  case.native.assert_called_once()
  assert case.marker()["active"] is True
  assert case.marker()["peak"] == 110.0
  assert case.strategy.target_profit_cache.data[case.trade.pair]["profit"] == pytest.approx(0.09895)


def test_original_evaluator_once_when_admitted_profit_suppressed(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit(profit=0.4)
  case.call()
  original = case.strategy._m_native_exit_profit_target
  # When
  with patch.object(case.strategy, "_m_native_exit_profit_target", wraps=original) as native:
    result = f.target_call(case, 105.0)
  # Then
  assert result == (False, None)
  native.assert_called_once()


def test_trail_persists_when_native_max_cache_cancels(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  f.actual_native(case)
  case.call()
  # When
  result = case.call(60, 88.0)
  # Then
  assert result == f.REASON
  assert case.trade.pair not in case.strategy.target_profit_cache.data
  assert case.marker()["active"] is True
  assert case.marker()["episode"] is False


def test_new_profit_episode_when_reason_changes(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit(profit=0.4)
  case.call()
  case.target("exit_long_scalp_o_0", profit=0.4)
  case.native.side_effect = None
  case.call(60)
  case.target(profit=0.4)
  original = case.strategy._m_native_exit_profit_target
  # When
  with patch.object(case.strategy, "_m_native_exit_profit_target", wraps=original) as native:
    result = f.target_call(case, 105.0)
  # Then
  assert result[0] is True
  assert case.marker()["episode"] is False
  assert case.marker()["active"] is True
  native.assert_called_once()


def test_same_reason_new_episode_when_original_cache_removed(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit(profit=0.4)
  case.call()
  assert f.target_call(case, 88.0) == (False, None)
  assert case.marker()["episode"] is False
  case.target(profit=0.4)
  # When
  result = f.target_call(case, 105.0)
  # Then
  assert result[0] is True
  assert case.marker()["active"] is True


@pytest.mark.parametrize(
  "reason", ["exit_long_scalp_stoploss_doom", "exit_long_scalp_stoploss", "exit_long_scalp_stoploss_u_e"]
)
def test_native_protective_evaluator_when_m_active(database, tmp_path, reason):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  case.target(reason, profit=-0.01)
  # When
  result = f.target_call(case, 80.0, reason)
  # Then
  assert result == (True, reason)
  assert case.marker()["episode"] is False


@pytest.mark.parametrize("guard", ["bad_trade", "signal_192"])
def test_actual_native_guard_when_price_trail_breached(database, tmp_path, guard):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  f.actual_native(case)
  if guard == "bad_trade":
    case.strategy.system_v4_bad_trade_exit_enable = True
    with patch.object(case.strategy, "_bad_trade_controller_exit_reason", return_value="native_bad") as controller:
      # When
      result = case.call(60, 80.0)
    # Then
    controller.assert_called_once()
    assert result.startswith("native_bad")
  else:
    case.trade.enter_tag = "192"
    # When
    result = case.call(60, 80.0)
    # Then
    assert result.startswith("exit_long_normal_stoploss_doom")
  assert case.marker()["pending"] is None


def test_direct_profit_exit_when_m_active(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.emit()
  case.call()
  f.actual_native(case)
  case.strategy.long_exit_main.return_value = (True, "exit_long_scalp_o_0")
  # When
  result = case.call(60, 88.0)
  # Then
  assert result.startswith("exit_long_scalp_o_0")
  assert case.marker()["pending"] is None


def test_restored_native_evaluator_when_calm_lost(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  f.actual_native(case)
  case.call()
  frame, _ = case.strategy.dp.get_analyzed_dataframe.return_value
  frame["MKT_STRESS_1d"] = 20.0
  # When
  result = case.call(60, 105.0)
  # Then
  assert result.startswith("exit_profit_long_scalp_t_")
  assert case.marker()["active"] is False


def test_other_pair_cache_when_m_admitted(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  case.strategy._set_profit_target("BTC/USDT:USDT", f.TARGET, 50000.0, 0.1, f.NOW)
  other = copy.deepcopy(case.strategy.target_profit_cache.data["BTC/USDT:USDT"])
  case.emit()
  # When
  case.call()
  # Then
  assert case.strategy.target_profit_cache.data["BTC/USDT:USDT"] == other


@pytest.mark.parametrize(
  "tag,mode",
  [
    ("1", "normal"),
    ("21", "pump"),
    ("41", "quick"),
    ("61", "rebuy"),
    ("81", "hp"),
    ("101", "rapid"),
    ("141", "tc"),
    ("161", "scalp"),
  ],
)
def test_actual_mode_tracking_when_native_first_commits(database, tmp_path, tag, mode):
  # Given
  case = f.make_case(tmp_path)
  f.actual_native(case)
  case.trade.enter_tag = tag
  case.strategy.long_exit_stoploss = MagicMock(return_value=(False, None))
  # When
  result = case.call()
  # Then
  assert result is None
  assert case.marker()["reason"] == f"exit_profit_long_{mode}_max"
  assert case.marker()["active"] is True
  case.native.assert_called_once()


def test_native_availability_when_fewer_than_two_rows(database, tmp_path):
  # Given
  case = f.make_case(tmp_path)
  f.actual_native(case)
  frame, _ = case.strategy.dp.get_analyzed_dataframe.return_value
  case.strategy.dp.get_analyzed_dataframe.return_value = frame.iloc[-1:], None
  # When
  result = case.call()
  # Then
  assert result is None
  assert case.marker() is None
  case.native.assert_called_once()
