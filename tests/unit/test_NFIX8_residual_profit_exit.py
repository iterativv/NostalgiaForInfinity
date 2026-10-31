"""Deterministic software probes; these do not assert a market fill."""

import math
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest
from freqtrade.enums import RunMode
from freqtrade.persistence import Trade

from tests.unit import residual_profit_fixtures as f

database = f.database


def test_actual_unchanged_native_scalp_commits_first_target(database, tmp_path):
  case = f.make_case(tmp_path)
  f.use_actual_scalp_tracker(case)
  assert case.trade.pair not in case.strategy.target_profit_cache.data
  assert case.call() == f.REASON
  case.native.assert_called_once()
  target = f.MODULE.Cache(case.strategy.target_profit_cache.path).data[case.trade.pair]
  assert target["sell_reason"] == f.TARGET
  assert target["time_profit_reached"] == f.NOW.isoformat()
  assert target["profit"] == pytest.approx(98.95 / 1000.0)
  assert case.marker() == f.REASON


@pytest.mark.parametrize(
  "reason",
  [
    "exit_profit_long_scalp_max",
    "exit_profit_long_normal_max",
    "exit_long_scalp_o_0",
    "exit_long_normal_1_1_1",
  ],
)
def test_generic_and_named_positive_profit_targets(database, tmp_path, reason):
  case = f.make_case(tmp_path)
  case.emit(reason)
  expected = "exit_r_first_" + reason.removeprefix("exit_")
  assert case.call() == expected
  assert f.MODULE.Cache(case.strategy.target_profit_cache.path).data[case.trade.pair]["sell_reason"] == reason


@pytest.mark.parametrize(
  "reason",
  [
    "exit_long_scalp_stoploss_doom",
    "exit_long_scalp_stoploss_u_e",
    "exit_long_normal_doom",
    "exit_long_abandon",
    "exit_short_scalp_max",
    "unrelated_max",
  ],
)
def test_protective_or_nonlong_targets_do_not_trigger(database, tmp_path, reason):
  case = f.make_case(tmp_path)
  case.emit(reason)
  assert case.call() is None
  assert case.marker() is None
  case.strategy.dp.get_analyzed_dataframe.assert_not_called()


@pytest.mark.parametrize("profit", [0.0, -0.01, float("nan"), float("inf"), -float("inf")])
def test_tracking_requires_finite_positive_native_target(database, tmp_path, profit):
  case = f.make_case(tmp_path)
  if math.isfinite(profit):
    case.emit(profit=profit)
  else:
    # Native mutates memory before its JSON writer rejects this value.
    with pytest.raises(ValueError):
      case.target(profit=profit)
  assert case.call() is None
  assert case.marker() is None


@pytest.mark.parametrize("profit", [float("nan"), float("inf"), -float("inf")])
def test_native_target_write_failure_propagates_without_exit_intent(database, tmp_path, profit):
  case = f.make_case(tmp_path)
  case.emit(profit=profit)
  with pytest.raises(ValueError):
    case.call()
  case.native.assert_called_once()
  assert case.marker() is None


@pytest.mark.parametrize("reason", [f.TARGET, "exit_long_scalp_o_0"])
def test_existing_tracking_peak_update_is_not_a_new_start(database, tmp_path, reason):
  case = f.make_case(tmp_path)
  case.target(reason, f.NOW - timedelta(minutes=5), 0.01)
  case.emit(reason, profit=0.03)
  assert case.call() is None
  assert case.strategy.target_profit_cache.data[case.trade.pair]["profit"] == 0.03
  assert case.marker() is None
  case.strategy.dp.get_analyzed_dataframe.assert_not_called()


@pytest.mark.parametrize("age", [timedelta(minutes=1), timedelta(days=3)])
def test_old_timestamp_cannot_manufacture_a_current_transition(database, tmp_path, age):
  case = f.make_case(tmp_path)
  case.emit(stamp=f.NOW - age)
  assert case.call() is None
  assert case.marker() is None


def test_prior_trade_cache_reload_is_not_a_fresh_event(database, tmp_path):
  case = f.make_case(tmp_path)
  case.target(stamp=f.NOW - timedelta(days=3))
  case.strategy.target_profit_cache = f.MODULE.Cache(case.strategy.target_profit_cache.path)
  assert case.call() is None
  assert case.marker() is None
  case.native.assert_called_once()
  case.strategy.dp.get_analyzed_dataframe.assert_not_called()


def test_new_native_commit_can_replace_prior_trade_cache(database, tmp_path):
  case = f.make_case(tmp_path)
  case.target(stamp=f.NOW - timedelta(days=3))
  case.emit()
  assert case.call() == f.REASON
  assert case.marker() == f.REASON


def test_no_committed_target_means_no_event(database, tmp_path):
  case = f.make_case(tmp_path)
  assert case.ledger()[0] > 0.0
  assert case.call() is None
  case.native.assert_called_once()
  assert case.marker() is None
  case.strategy.dp.get_analyzed_dataframe.assert_not_called()


@pytest.mark.parametrize(
  ("exit_price", "rate", "cash", "trigger"),
  [
    (80.0, 110.0, -140.93, False),
    (120.0, 90.0, 138.93, True),
  ],
)
@pytest.mark.parametrize("futures", [False, True])
def test_real_lifecycle_not_remaining_callback_profit(database, tmp_path, exit_price, rate, cash, trigger, futures):
  case = f.make_case(tmp_path, futures=futures)
  f.fill(case.trade, case.trade.exit_side, 8.0, exit_price, requested=9.0)
  f.fill(case.trade, case.trade.entry_side, 0.0, 70.0, requested=9.0, pending=True)
  orders, entries, exits = case.strategy.filled_order_snapshot(case.trade)
  assert len(orders) == 2
  assert entries[0].safe_filled == 10.0
  assert exits[0].safe_filled == 8.0
  assert case.ledger(rate)[0] == pytest.approx(cash)
  assert (case.trade.calc_profit_ratio(rate) > 0.0) is not trigger
  case.emit()
  assert case.call(rate=rate) == (f.REASON if trigger else None)
  assert case.marker() == (f.REASON if trigger else None)


@pytest.mark.parametrize(
  ("funding", "cash", "trigger"),
  [
    (0.0, -1.0, False),
    (1.0, 0.0, False),
    (1.01, 0.01, True),
    (-3.0, -4.0, False),
  ],
)
def test_real_fees_and_signed_funding_decide_lifecycle_cash(database, tmp_path, funding, cash, trigger):
  case = f.make_case(tmp_path)
  case.trade.funding_fees = funding
  assert case.ledger(100.0)[0] == pytest.approx(cash)
  case.emit()
  assert case.call(rate=100.0) == (f.REASON if trigger else None)


@pytest.mark.parametrize("funding", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_real_lifecycle_cash_does_not_issue_intent(database, tmp_path, funding):
  case = f.make_case(tmp_path)
  case.trade.funding_fees = funding
  case.emit()
  assert case.call() is None
  assert case.marker() is None


@pytest.mark.parametrize("result", ["exit_long_native", "", False, True, 0])
@pytest.mark.parametrize("pending", [False, True])
def test_every_non_none_native_decision_wins_exactly_once(database, tmp_path, result, pending):
  case = f.make_case(tmp_path)
  if pending:
    case.trade.set_custom_data(key=f.KEY, value=f.REASON)
  case.emit()
  original = case.native.side_effect

  def boundary(*args, **kwargs):
    original(*args, **kwargs)
    return result

  case.native.side_effect = boundary
  with patch.object(case.trade, "get_custom_data", side_effect=AssertionError("Native preempts marker")):
    assert case.call(token=17) is result
  case.native.assert_called_once_with(
    case.trade.pair,
    case.trade,
    f.NOW,
    110.0,
    case.trade.calc_profit_ratio(110.0),
    token=17,
  )
  case.strategy.dp.get_analyzed_dataframe.assert_not_called()
  assert case.marker() == (f.REASON if pending else None)


@pytest.mark.parametrize(("enabled", "short"), [(None, False), (False, False), (False, True), (True, True)])
@pytest.mark.parametrize("result", [None, "", False, True, "exit_long_native"])
def test_off_or_short_adds_no_cache_marker_or_reading_access(database, tmp_path, enabled, short, result):
  case = f.make_case(tmp_path, enabled is True, short)
  if enabled is None:
    del case.strategy.risk_residual_first_target_exit_enable
  case.native.return_value = result
  del case.strategy.target_profit_cache
  del case.strategy.dp
  with (
    patch.object(case.trade, "get_custom_data", side_effect=AssertionError("R marker access")),
    patch.object(
      case.trade,
      "set_custom_data",
      side_effect=AssertionError("R marker write"),
    ),
  ):
    assert case.call(token=17) is result
  case.native.assert_called_once_with(
    case.trade.pair,
    case.trade,
    f.NOW,
    110.0,
    case.trade.calc_profit_ratio(110.0),
    token=17,
  )


def test_pending_intent_survives_commit_reload_retry_disable_and_reenable(database, tmp_path):
  case = f.make_case(tmp_path)
  case.emit()
  assert case.call() == f.REASON
  trade_id = case.trade.id
  Trade.session.commit()
  Trade.session.expunge_all()
  reloaded = Trade.session.get(Trade, trade_id)
  assert reloaded is not None and reloaded is not case.trade
  case.trade = reloaded
  assert case.marker() == f.REASON
  case.native.side_effect = None
  case.native.reset_mock()
  case.strategy.target_profit_cache = f.MODULE.Cache(case.strategy.target_profit_cache.path)
  case.analyzed(False)
  case.strategy.dp.get_analyzed_dataframe.reset_mock()
  assert case.call(60, rate=90.0) == f.REASON
  assert case.trade.is_open
  case.strategy.risk_residual_first_target_exit_enable = False
  assert case.call(120, rate=90.0) is None
  assert case.marker() == f.REASON
  case.strategy.risk_residual_first_target_exit_enable = True
  assert case.call(180, rate=90.0) == f.REASON
  assert case.native.call_count == 3
  case.strategy.dp.get_analyzed_dataframe.assert_not_called()


def test_rejected_alarm_does_not_turn_later_peak_update_into_first_start(database, tmp_path):
  case = f.make_case(tmp_path)
  case.analyzed(False)
  case.emit()
  assert case.call() is None
  case.analyzed()
  case.emit(stamp=f.NOW + timedelta(minutes=5), profit=0.03)
  assert case.call(300) is None
  assert case.marker() is None
  assert case.native.call_count == 2


@pytest.mark.parametrize("setting", ["absent", False, True, "nested"])
def test_real_constructor_safe_override_without_advanced_mode(tmp_path: Path, monkeypatch, setting):
  monkeypatch.setattr(f.Strategy, "target_profit_cache", None)
  monkeypatch.setattr(f.Strategy, "hold_trades_cache", None)
  config = {"exchange": {"name": "binance"}, "stake_currency": "USDT", "trading_mode": "futures"}
  config.update({"runmode": RunMode.BACKTEST, "user_data_dir": tmp_path, "nfi_advanced_mode": False})
  config.pop("risk_residual_first_target_exit_enable", None)
  config.pop("nfi_parameters", None)
  if setting == "nested":
    config["nfi_parameters"] = {"risk_residual_first_target_exit_enable": True}
  elif isinstance(setting, bool):
    config["risk_residual_first_target_exit_enable"] = setting
  strategy = f.Strategy(config)
  assert f.Strategy.risk_residual_first_target_exit_enable is False
  assert strategy.risk_residual_first_target_exit_enable is (setting is True or setting == "nested")


@pytest.mark.parametrize(
  ("age", "seconds", "trigger"),
  [
    (0, -1, False),
    (0, 0, True),
    (0, 3599, True),
    (0, 3600, False),
    (3600, 0, False),
    (7200, 0, False),
    (-3600, 0, False),
  ],
)
def test_alarm_available_interval_not_persistent_arming(database, tmp_path, age, seconds, trigger):
  case = f.make_case(tmp_path)
  case.analyzed(available=f.NOW - timedelta(seconds=age))
  case.emit(stamp=f.NOW + timedelta(seconds=seconds))
  assert case.call(seconds) == (f.REASON if trigger else None)
  assert case.marker() == (f.REASON if trigger else None)
  case.native.assert_called_once()


@pytest.mark.parametrize("field", ["R_AVAILABLE_AT", "R_UP_ALARM", "date"])
@pytest.mark.parametrize("bad", ["missing", None, pd.NaT])
def test_missing_hourly_reading_never_arms_trade(database, tmp_path, field, bad):
  case = f.make_case(tmp_path)
  frame, _ = case.strategy.dp.get_analyzed_dataframe(case.trade.pair, "5m")
  frame = frame.copy()
  if bad == "missing":
    frame = frame.drop(columns=field)
  else:
    frame[field] = bad
  case.cache(frame)
  case.emit()
  assert case.call() is None
  assert case.marker() is None


def test_unclosed_analyzed_base_row_cannot_expose_next_hour(database, tmp_path):
  case = f.make_case(tmp_path)
  case.analyzed(date=f.NOW)
  case.emit()
  assert case.call() is None
  assert case.marker() is None


def test_future_appended_analyzed_rows_do_not_hide_last_completed_row(database, tmp_path):
  case = f.make_case(tmp_path)
  case.cache(
    pd.DataFrame(
      {
        "date": [f.NOW - timedelta(minutes=5), f.NOW],
        "R_AVAILABLE_AT": [f.NOW, f.NOW + timedelta(hours=1)],
        "R_UP_ALARM": [True, False],
      }
    )
  )
  case.emit()
  assert case.call() == f.REASON


def test_alarm_without_tracking_leaves_no_marker_and_cannot_be_used_later(database, tmp_path):
  case = f.make_case(tmp_path)
  assert case.call() is None
  assert case.marker() is None
  case.emit(stamp=f.NOW + timedelta(hours=1))
  assert case.call(3600) is None
  assert case.marker() is None


def test_canceled_exit_order_retries_original_intent_without_new_alarm(database, tmp_path):
  case = f.make_case(tmp_path)
  case.emit()
  assert case.call() == f.REASON
  canceled = f.fill(case.trade, case.trade.exit_side, 0.0, 110.0, requested=10.0)
  assert canceled.status == "canceled" and canceled.safe_filled == 0.0
  case.native.side_effect = None
  case.analyzed(False, available=f.NOW - timedelta(days=1))
  assert case.call(7200, rate=90.0) == f.REASON
  assert case.marker() == f.REASON
  assert case.trade.is_open


@pytest.mark.parametrize("reason", [f.TARGET, "exit_long_scalp_o_0"])
def test_removed_rejected_cache_can_start_a_fresh_eligible_episode(database, tmp_path, reason):
  case = f.make_case(tmp_path)
  case.analyzed(False)
  case.emit()
  assert case.call() is None
  assert case.marker() is None
  case.strategy._remove_profit_target(case.trade.pair)
  later = f.NOW + timedelta(minutes=5)
  case.analyzed(True, available=later, date=f.NOW)
  case.emit(reason=reason, stamp=later)
  expected = "exit_r_first_" + reason.removeprefix("exit_")
  assert case.call(300) == expected
  assert case.marker() == expected
  assert case.native.call_count == 2
