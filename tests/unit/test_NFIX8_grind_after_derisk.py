from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from freqtrade.persistence import Trade

from tests.unit import test_NFIX8_grind_before_derisk as before
from tests.unit import test_NFIX8_legacy_grind_funding as legacy


grind_case = before.grind_case
rescue_case = before.rescue_case
add_order = before.add_order
adjust = before.adjust
legacy_grind_case = legacy.legacy_grind_case
SETTING = "system_v4_grind_only_after_derisk_enable"


@pytest.fixture(autouse=True)
def restore_database_sessions():
  # init_db replaces the mapped classes' session attributes globally.
  models = [mapper.class_ for mapper in Trade.registry.mappers]
  sessions = [(model, model.__dict__.get("session")) for model in models]
  yield
  engine = Trade.session.get_bind()
  Trade.session.remove()
  engine.dispose()
  for model, session in sessions:
    if session is not None:
      model.session = session
    elif "session" in model.__dict__:
      delattr(model, "session")


@pytest.fixture
def normal_case(grind_case):
  strategy, trade = grind_case
  strategy.long_grind_entry_v4.return_value = True
  strategy.short_grind_entry_v4.return_value = True
  strategy._grind_entry_tag = "normal"
  return strategy, trade


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("enabled", [None, False, True], ids=["default", "disabled", "enabled"])
def test_normal_entries_require_executed_derisk_only_when_enabled(normal_case, level, enabled):
  strategy, trade = normal_case
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  if enabled is None:
    strategy.__dict__.pop(SETTING, None)
  else:
    setattr(strategy, SETTING, enabled)

  result = adjust(normal_case, 100.0)

  if enabled:
    assert result is None
  else:
    assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("derisk_level", [1, 2, 3])
def test_each_staged_fill_independently_unlocks_every_queue(normal_case, level, derisk_level):
  strategy, trade = normal_case
  setattr(strategy, SETTING, True)
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  add_order(trade, trade.exit_side, f"derisk_level_{derisk_level}", 1.0)

  result = adjust(normal_case, 100.0)

  assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"


@pytest.mark.parametrize(
  "tag,filled,status",
  [
    ("derisk_level_1", 0.0, "canceled"),
    ("derisk_level_2", 0.0, "open"),
    ("exit_normal", 1.0, "closed"),
    ("derisk_global", 1.0, "closed"),
    ("grind_1_derisk 2", 1.0, "closed"),
    ("derisk_level_4", 1.0, "closed"),
  ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_ineligible_exit_history_does_not_unlock(normal_case, tag, filled, status, enabled):
  strategy, trade = normal_case
  setattr(strategy, SETTING, enabled)
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.exit_side, tag, 1.0, filled=filled, status=status)

  result = adjust(normal_case, 100.0)

  if enabled or status == "open":
    assert result is None
  else:
    assert result is not None and result[0] > 0 and result[1] == "grind_1_entry"


@pytest.mark.parametrize("enabled", [False, True])
def test_custom_data_flags_are_not_executed_exits(normal_case, enabled):
  strategy, trade = normal_case
  setattr(strategy, SETTING, enabled)
  strategy.system_v4_grind_1_enable = True
  for level in (1, 2, 3):
    trade.set_custom_data(f"derisk_level_{level}", True)
    trade.set_custom_data(f"system_v4_derisk_level_{level}_flag", True)

  result = adjust(normal_case, 100.0)

  if enabled:
    assert result is None
  else:
    assert result is not None and result[0] > 0 and result[1] == "grind_1_entry"


@pytest.mark.parametrize("derisk_level", [1, 2, 3])
def test_old_tagged_retry_fill_survives_database_reload(normal_case, derisk_level):
  strategy, trade = normal_case
  setattr(strategy, SETTING, True)
  strategy.system_v4_grind_1_enable = True
  order = add_order(trade, trade.exit_side, f"derisk_level_{derisk_level} retry 17", 1.0)
  order.order_date = order.order_filled_date = before.NOW - timedelta(days=30)
  trade.open_date = before.NOW - timedelta(days=31)
  trade.orders[0].order_date = trade.orders[0].order_filled_date = trade.open_date
  Trade.session.flush()
  trade_id = trade.id
  Trade.session.expunge_all()
  restored = Trade.session.get(Trade, trade_id)

  result = adjust((strategy, restored), 100.0)

  assert result is not None and result[0] > 0 and result[1] == "grind_1_entry"


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("enabled", [False, True])
def test_pre_derisk_add_to_existing_queue_obeys_gate(grind_case, level, enabled):
  strategy, trade = grind_case
  setattr(strategy, SETTING, enabled)
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)

  result = adjust(grind_case, 120.0 if trade.is_short else 80.0)

  if enabled:
    assert result is None
  else:
    assert result is not None and result[0] > 0 and result[1] == f"grind_{level}_entry"


@pytest.mark.parametrize("enabled", [False, True])
def test_grind_four_fallback_obeys_gate(grind_case, enabled):
  strategy, trade = grind_case
  setattr(strategy, SETTING, enabled)
  strategy.system_v4_grind_4_enable = True
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, strategy.timeframe)
  frame = frame.assign(RSI_14=75.0 if trade.is_short else 25.0, close=110.0 if trade.is_short else 90.0)
  strategy.dp._set_cached_df(trade.pair, strategy.timeframe, frame, strategy.config["candle_type_def"])

  result = adjust(grind_case, 110.0 if trade.is_short else 90.0)

  if enabled:
    assert result is None
  else:
    assert result is not None and result[0] > 0 and result[1] == "grind_4_entry"


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("move", [0.06, 0.16], ids=["rescue", "original-liquidation"])
def test_grind_five_liquidation_routes_obey_gate(rescue_case, enabled, move):
  strategy, trade = rescue_case
  setattr(strategy, SETTING, enabled)
  strategy.system_v4_grind_5_enable = True
  add_order(trade, trade.exit_side, "exit_normal", 8.0)
  trade.liquidation_price = 120.0 if trade.is_short else 80.0
  rate = 100.0 * (1 + move if trade.is_short else 1 - move)

  result = adjust(rescue_case, rate)

  if enabled or not strategy.is_futures_mode:
    assert result is None
  else:
    assert result is not None and result[0] > 0 and result[1] == "grind_5_entry"


@pytest.mark.parametrize("level", [1, 2, 3])
def test_staged_exits_remain_available_before_unlock(grind_case, level):
  strategy, trade = grind_case
  setattr(strategy, SETTING, True)
  strategy.derisk_enable = True
  setattr(strategy, f"system_v4_derisk_level_{level}_enable", True)
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_derisk_level_{level}_{market}", [-0.01, -0.02])
  strategy._bad_trade_controller_derisk_hold.return_value = False

  result = adjust(grind_case, 110.0 if trade.is_short else 90.0)

  assert result is not None and result[0] < 0 and result[1] == f"derisk_level_{level}"


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("profitable", [False, True], ids=["derisk", "profit"])
def test_existing_grind_exits_remain_available(grind_case, level, profitable):
  strategy, trade = grind_case
  setattr(strategy, SETTING, True)
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  entry = add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)
  if profitable:
    for market in ("spot", "futures"):
      setattr(strategy, f"system_v4_grind_{level}_profit_threshold_{market}", 0.01)
    frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, strategy.timeframe)
    frame = frame.assign(RSI_3=0.0 if trade.is_short else 100.0, WILLR_14=-50.0, STOCHRSIk_14_14_3_3=50.0)
    frame["BBL_20_2.0"] = 50.0
    frame["BBU_20_2.0"] = 150.0
    strategy.dp._set_cached_df(trade.pair, strategy.timeframe, frame, strategy.config["candle_type_def"])
  rate = (72.0 if trade.is_short else 128.0) if profitable else (123.0 if trade.is_short else 77.0)

  result = adjust(grind_case, rate)

  kind = "exit" if profitable else "derisk"
  assert result is not None and result[0] < 0 and result[1] == f"grind_{level}_{kind} {entry.id}"


@pytest.mark.parametrize("tag", ["derisk_level_1", "grind_1_exit 2", "grind_1_derisk 2"])
def test_partial_exit_recovery_remains_available(grind_case, tag):
  strategy, trade = grind_case
  setattr(strategy, SETTING, True)
  add_order(trade, trade.entry_side, "grind_1_entry", 4.0)
  add_order(trade, trade.exit_side, tag, 4.0, filled=1.0, status="canceled")

  result = adjust(grind_case, 100.0)

  assert result == (pytest.approx(-300.0 / trade.leverage), tag)


@pytest.mark.parametrize("gate", ["retry", "timing", "stake", "wallet", "queue", "spacing", "open_order"])
def test_unlocked_entries_preserve_existing_admission_limits(normal_case, gate):
  strategy, trade = normal_case
  setattr(strategy, SETTING, True)
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.exit_side, "derisk_level_1", 1.0)
  entry = add_order(trade, trade.entry_side, "grind_1_entry", 1.0)
  max_stake = 10000.0
  if gate == "retry":
    entry.order_filled_date = before.NOW - timedelta(minutes=4)
  elif gate == "timing":
    entry.order_filled_date = before.NOW - timedelta(minutes=10)
    strategy.system_v4_grind_1_thresholds_spot = strategy.system_v4_grind_1_thresholds_futures = [0.1] * 5
  elif gate == "stake":
    strategy.system_v4_max_stake = 0.1
  elif gate == "wallet":
    max_stake = 1.0
  elif gate == "queue":
    strategy.system_v4_grind_1_stakes_spot = strategy.system_v4_grind_1_stakes_futures = [0.2]
  elif gate == "spacing":
    strategy.system_v4_grind_1_thresholds_spot = strategy.system_v4_grind_1_thresholds_futures = [-0.5] * 5
  else:
    add_order(trade, trade.entry_side, "grind_1_entry", 1.0, filled=0.0, status="open")
  rate = 100.0 if gate == "timing" else (120.0 if trade.is_short else 80.0)

  result = adjust(normal_case, rate, max_stake)

  assert result is None


@pytest.mark.parametrize("version", [None, "system_v3", "system_v3_1", "system_v3_2"])
def test_non_v4_normal_grinds_remain_available(grind_case, version):
  strategy, trade = grind_case
  setattr(strategy, SETTING, True)
  trade.set_custom_data("system_version", version)
  prefix = "grinding_v2" if version is None else "system_v3"
  for name in dir(strategy):
    if name.startswith(("grinding_v2_", "system_v3_", "system_v3_1_")) and name.endswith("_enable"):
      setattr(strategy, name, False)
  setattr(strategy, f"{prefix}_grind_1_enable", True)
  setattr(strategy, f"{prefix}_max_stake", 2.0)
  # V2 already requires a staged de-risk, including its historical "d" tag.
  add_order(trade, trade.exit_side, "d" if version is None else "exit_normal", 8.0)
  strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  strategy.short_grind_entry_v2 = MagicMock(return_value=True)
  strategy.short_grind_entry_v3 = MagicMock(return_value=True)
  strategy.long_buyback_entry_v2 = MagicMock(return_value=False)
  strategy.short_buyback_entry_v2 = MagicMock(return_value=False)
  strategy.long_buyback_entry_v3 = MagicMock(return_value=False)
  strategy.long_rebuy_entry_v3 = MagicMock(return_value=False)
  strategy.short_rebuy_entry_v3 = MagicMock(return_value=False)
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, strategy.timeframe)
  frame = frame.assign(RSI_3_1h=50.0, AROONU_14_15m=100.0, AROOND_14_15m=100.0)
  strategy.dp._set_cached_df(trade.pair, strategy.timeframe, frame, strategy.config["candle_type_def"])
  strategy._grind_entry_tag = "normal"

  result = adjust(grind_case, 100.0)

  assert result is not None and result[0] > 0 and result[1] == "grind_1_entry"


def test_rebuy_handoff_after_level_three_still_allows_grinding(normal_case):
  strategy, trade = normal_case
  setattr(strategy, SETTING, True)
  strategy.system_v4_grind_1_enable = True
  trade.enter_tag = "561" if trade.is_short else "61"
  add_order(trade, trade.exit_side, "derisk_level_3", 8.0)

  result = adjust(normal_case, 100.0)

  assert result is not None and result[0] > 0 and result[1] == "grind_1_entry"


def test_legacy_grind_route_remains_available(legacy_grind_case):
  strategy, trade, _ = legacy_grind_case
  setattr(strategy, SETTING, True)

  result = legacy.adjust(legacy_grind_case, 1000.0)

  assert result == (pytest.approx(140.0 / trade.leverage), "gd1")


@pytest.mark.parametrize("nested", [False, True], ids=["top-level", "nfi-parameters"])
@pytest.mark.parametrize("enabled", [False, True])
def test_safe_configuration_changes_public_adjustment(normal_case, tmp_path, nested, enabled):
  strategy, trade = normal_case
  strategy.system_v4_grind_1_enable = True
  config = strategy.config.copy()
  config.update(user_data_dir=tmp_path, trading_mode=trade.trading_mode, nfi_advanced_mode=False)
  if nested:
    config["nfi_parameters"] = {SETTING: enabled}
  else:
    config[SETTING] = enabled
  strategy.target_profit_cache = MagicMock()
  # Load through the real constructor while retaining the fixture's indicator boundary.
  strategy.__init__(config)

  result = adjust((strategy, trade), 100.0)

  if enabled:
    assert result is None
  else:
    assert result is not None and result[0] > 0 and result[1] == "grind_1_entry"
