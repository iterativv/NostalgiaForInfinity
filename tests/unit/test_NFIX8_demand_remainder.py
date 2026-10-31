"""Demand qualification and Native priority through public callbacks."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import RunMode

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8
from tests.unit import nfix8_demand_fixtures as fixtures
from tests.unit.nfix8_demand_fixtures import DEMAND, DUE, EXIT, FEATURE, KEY, fill, make_d1


database = fixtures.database
case = fixtures.case


@pytest.fixture
def strategy_config(tmp_path):
  return {
    "exchange": {"name": "binance"},
    "runmode": RunMode.BACKTEST,
    "user_data_dir": tmp_path,
    "stake_currency": "USDT",
    "trading_mode": "futures",
    "nfi_advanced_mode": False,
  }


def test_constructor_defaults_to_enabled(strategy_config):
  strategy = NostalgiaForInfinityX8(strategy_config)
  assert getattr(strategy, FEATURE) is True


@pytest.mark.parametrize("config_style", ["nested", "top_level"])
@pytest.mark.parametrize("enabled", [False, True])
def test_constructor_accepts_safe_override_without_advanced_mode(strategy_config, config_style, enabled):
  if config_style == "nested":
    strategy_config["nfi_parameters"] = {FEATURE: enabled}
  else:
    strategy_config[FEATURE] = enabled
  strategy = NostalgiaForInfinityX8(strategy_config)
  assert getattr(strategy, FEATURE) is enabled


@pytest.mark.parametrize("top_level", [False, True])
def test_constructor_top_level_precedence_and_instance_isolation(strategy_config, top_level):
  strategy_config["nfi_parameters"] = {FEATURE: not top_level}
  strategy_config[FEATURE] = top_level
  configured = NostalgiaForInfinityX8(strategy_config)
  clean_config = {key: value for key, value in strategy_config.items() if key not in ("nfi_parameters", FEATURE)}
  clean = NostalgiaForInfinityX8(clean_config)
  assert getattr(configured, FEATURE) is top_level
  assert getattr(clean, FEATURE) is True


def test_default_enabled_without_instance_override(case):
  assert FEATURE not in case.strategy.__dict__
  assert getattr(case.strategy, FEATURE) is True
  assert case.demand() is False
  assert case.adjust() is None
  assert case.exit() == EXIT


def test_same_candle_demand_waits_for_next_callback(case):
  assert case.demand() is False
  assert case.adjust(DEMAND) is None
  assert case.exit(DEMAND) is None
  assert case.trade.get_custom_data(KEY)["due_candle"] == int(DUE.timestamp())


def test_next_candle_starts_one_full_exit_intent(case):
  assert case.demand() is False
  assert case.adjust() is None
  assert case.exit() == EXIT
  assert case.trade.get_custom_data(KEY)["closing"] is True
  assert case.trade.is_open and case.trade.amount > 0
  assert len(case.trade.orders) == 2


def test_later_exit_in_same_due_candle_uses_actual_intent_time(case):
  case.demand()
  assert case.adjust(DUE + timedelta(seconds=1)) is None
  exit_time = DUE + timedelta(seconds=6)
  assert case.exit(exit_time) == EXIT
  assert case.trade.get_custom_data(KEY)["intent_time"] == exit_time.isoformat()


@pytest.mark.parametrize("exit_time", [DUE, DUE + timedelta(minutes=5)])
def test_earlier_or_next_candle_exit_consumes_snapshot_without_replay(case, exit_time):
  case.demand()
  case.adjust(DUE + timedelta(seconds=1))
  assert case.exit(exit_time) is None
  assert case.strategy._legacy_grind_demand_snapshot is None
  assert case.trade.get_custom_data(KEY) is None
  assert case.exit(DUE + timedelta(seconds=6)) is None


def test_explicit_false_preserves_native_callbacks(database):
  case = make_d1(enabled=False)
  assert case.demand() is False
  assert case.adjust() is None
  assert case.exit() is None
  assert case.trade.get_custom_data(KEY) is None


def test_late_callback_expires_demand(case):
  case.demand()
  case.adjust(DUE + timedelta(minutes=5))
  assert case.exit(DUE + timedelta(minutes=5)) is None
  assert case.trade.get_custom_data(KEY) is None


def test_first_actual_demand_preserves_order(case):
  case.demand(pair="INJ/USDT:USDT")
  case.demand(pair="ADA/USDT:USDT")
  assert case.trade.get_custom_data(KEY)["demand_pair"] == "INJ/USDT:USDT"


@pytest.mark.parametrize("mode", ["disabled", "initial", "mixed_tag", "short", "other_exit", "canceled_gm0"])
def test_ineligible_owner_never_records_demand(database, mode):
  case = make_d1(enabled=False if mode == "disabled" else None, initial_only=mode == "initial")
  if mode == "mixed_tag":
    case.trade.enter_tag = "120 144"
  if mode == "short":
    case.trade.is_short = True
  if mode == "other_exit":
    case.gm0.ft_order_tag = "gmd0"
  if mode == "canceled_gm0":
    case.gm0.status = "canceled"
  case.demand()
  assert case.trade.get_custom_data(KEY) is None


@pytest.mark.parametrize("pair", ["NOT_ALLOWED/USDT:USDT", "ETH/USDT:USDT"])
def test_non_demand_rejection_does_not_record_token(case, pair):
  case.demand(pair=pair)
  assert case.trade.get_custom_data(KEY) is None


def test_available_slot_does_not_record_demand(case):
  case.strategy.grind_mode_max_slots = 2
  assert case.demand() is True
  assert case.trade.get_custom_data(KEY) is None


@pytest.mark.parametrize("change", ["new_fill", "open_order", "new_zero_order"])
def test_changed_orders_invalidate_due_token(case, change):
  case.demand()
  order = fill(case.trade, "buy", 0.1, "gd1", 9.0, filled=0.1 if change == "new_fill" else 0.0)
  if change == "open_order":
    order.ft_is_open = True
    order.status = "open"
  case.adjust()
  assert case.exit() is None
  assert case.trade.get_custom_data(KEY) is None


def test_native_add_precedes_demand_exit(case):
  case.demand()
  case.strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  case.strategy.long_grind_entry_v4 = MagicMock(return_value=True)
  # Native: initial 100 * 10 / grind multiplier 0.20 * first stake 0.24 / 3x.
  assert case.adjust(rate=9.0) == (400.0, "gd1")
  assert case.exit(rate=9.0) is None
  assert case.trade.get_custom_data(KEY) is None


def test_original_full_exit_precedes_new_intent(case):
  case.gm0.price = case.gm0.average = 14.0
  case.gm0.cost = case.gm0.safe_filled * 14.0
  case.trade.recalc_trade_from_orders()
  case.demand()
  case.adjust(rate=14.0)
  # Native lifecycle profit / initial cost exceeds its 0.25 full-exit threshold.
  assert case.exit(rate=14.0) == "exit_long_grind_g ( 120)"
  assert case.trade.get_custom_data(KEY) is None


@pytest.mark.parametrize("exit_delay", [0, 5])
@pytest.mark.parametrize("change", ["price", "funding", "inventory", "order_tag", "fee"])
def test_changed_callback_state_rejects_snapshot(case, change, exit_delay):
  case.demand()
  adjusted_at = DUE + timedelta(seconds=1)
  case.adjust(adjusted_at)
  rate = 11.0
  if change == "price":
    rate = 11.01
  if change == "funding":
    case.trade.funding_fees += 0.01
  if change == "inventory":
    case.trade.amount += 0.01
  if change == "order_tag":
    case.gm0.ft_order_tag = "gmd0"
  if change == "fee":
    case.trade.fee_close += 0.0001
  assert case.exit(adjusted_at + timedelta(seconds=exit_delay), rate=rate) is None
  assert case.strategy._legacy_grind_demand_snapshot is None
  assert case.trade.get_custom_data(KEY) is None
  assert case.exit(adjusted_at + timedelta(seconds=6), rate=rate) is None


def test_snapshot_is_consumed_even_when_native_exit_wins(case):
  case.gm0.price = case.gm0.average = 14.0
  case.gm0.cost = case.gm0.safe_filled * 14.0
  case.trade.recalc_trade_from_orders()
  case.demand()
  case.adjust(rate=14.0)
  assert case.exit(rate=14.0) == "exit_long_grind_g ( 120)"
  assert case.strategy._legacy_grind_demand_snapshot is None
  # The realized gm0 gain still exceeds 25% even when the remainder marks at 11.
  assert case.exit(rate=11.0) == "exit_long_grind_g ( 120)"
  assert case.trade.get_custom_data(KEY) is None


@pytest.mark.parametrize("exit_second", [2, 3, 6])
def test_snapshot_preserves_original_retry_time_boundary(case, exit_second):
  boundary = DUE + timedelta(seconds=3)
  entry_time = boundary - timedelta(minutes=10)
  case.entry.order_date = case.entry.order_filled_date = entry_time
  case.gm0.order_date = case.gm0.order_filled_date = entry_time + timedelta(minutes=1)
  case.trade.open_date = entry_time
  case.strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  case.strategy.long_grind_entry_v4 = MagicMock(return_value=True)
  assert case.demand() is False
  assert case.adjust(DUE + timedelta(seconds=1), rate=9.0) is None
  assert case.strategy._legacy_grind_demand_snapshot is not None
  exit_time = DUE + timedelta(seconds=exit_second)

  result = case.exit(exit_time, rate=9.0)

  if exit_time <= boundary:
    assert result == EXIT
  else:
    assert result is None
    assert case.trade.get_custom_data(KEY) is None
    assert case.adjust(exit_time, rate=9.0) == (400.0, "gd1")
