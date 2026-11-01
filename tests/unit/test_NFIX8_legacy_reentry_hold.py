"""Admission changes are exercised through the public callback, not private flags."""

from datetime import datetime, timezone

import pytest
from freqtrade.persistence import Trade

from tests.unit import legacy_reentry_fixtures as fixtures

database = fixtures.database


@pytest.mark.parametrize("enabled", [False, True])
def test_feature_behavior_captured_crv_reentry(database, enabled):
  case = fixtures.captured_crv()
  setattr(case.strategy, fixtures.FEATURE, enabled)
  result = case.run(0.399, datetime(2025, 12, 28, 12, tzinfo=timezone.utc))
  if enabled:
    assert result is None or result[0] < 0.0
  else:
    assert result == (pytest.approx(15144.01536), "gd1")


@pytest.mark.parametrize("leverage", [1.0, 3.0])
@pytest.mark.parametrize("queue", range(1, 7))
@pytest.mark.parametrize("enabled", [False, True])
def test_feature_behavior_every_grind_admission_is_held(database, leverage, queue, enabled):
  case = fixtures.make_case(leverage, target=queue, stop_queue=1 if queue != 1 else 3)
  setattr(case.strategy, fixtures.FEATURE, enabled)
  result = case.run()
  if enabled:
    assert result is None
  else:
    assert result is not None and result[0] > 0.0 and result[1] == f"gd{queue}"


@pytest.mark.parametrize("stop_queue", range(1, 7))
def test_feature_behavior_each_filled_stop_starts_hold(database, stop_queue):
  case = fixtures.make_case(stop_queue=stop_queue)
  assert case.run() is None


@pytest.mark.parametrize("signal", [False, True])
def test_feature_behavior_futures_fallback_cannot_bypass_hold(database, signal):
  case = fixtures.make_case()
  case.strategy.long_grind_entry_v3.return_value = signal
  case.strategy.derisk_use_grind_stops = False
  assert case.run(70.0) is None


@pytest.mark.parametrize("mode", ["off", "default", "zero_stop", "profit_exit"])
def test_native_admission_without_qualifying_stop(database, mode):
  case = fixtures.make_case(target=6, stop_fraction=0.0 if mode == "zero_stop" else 1.0)
  if mode == "off":
    setattr(case.strategy, fixtures.FEATURE, False)
  if mode == "default":
    delattr(case.strategy, fixtures.FEATURE)
  if mode == "profit_exit":
    case.stop.ft_order_tag = case.stop.ft_order_tag.replace("dd1", "gd1")
  result = case.run()
  assert result is not None and result[0] > 0.0 and result[1] == "gd6"


@pytest.mark.parametrize("restart", [False, True])
def test_feature_behavior_restart_keeps_hold(database, restart):
  case = fixtures.make_case()
  if restart:
    trade_id, old_id, stop_id = case.trade.id, case.old.id, case.stop.id
    Trade.commit()
    Trade.session.remove()
    trade = Trade.session.get(Trade, trade_id)
    case = fixtures.Case(
      fixtures.strategy_for(trade),
      trade,
      next(o for o in trade.orders if o.id == old_id),
      next(o for o in trade.orders if o.id == stop_id),
    )
  assert case.run() is None


@pytest.mark.parametrize("clipped", [False, True])
def test_native_queue_barrier_releases_hold(database, clipped):
  case = fixtures.make_case()
  fixtures.fill(case.trade, case.trade.exit_side, 0.99 if clipped else 1.0, f"{case.old.ft_order_tag} {case.old.id}")
  result = case.run()
  assert result is not None and result[0] > 0.0 and result[1] == "gd1"


def test_post_stop_queue_alone_does_not_keep_old_hold(database):
  case = fixtures.make_case()
  fixtures.fill(case.trade, case.trade.exit_side, 1.0, f"{case.old.ft_order_tag} {case.old.id}")
  fixtures.fill(case.trade, case.trade.entry_side, 1.0, "gd3")
  result = case.run()
  assert result is not None and result[0] > 0.0 and result[1] == "gd1"


def test_feature_behavior_later_stop_protects_newly_older_queue(database):
  case = fixtures.make_case()
  fixtures.fill(case.trade, case.trade.exit_side, 1.0, f"{case.old.ft_order_tag} {case.old.id}")
  fixtures.fill(case.trade, case.trade.entry_side, 1.0, "gd3")
  closed = fixtures.fill(case.trade, case.trade.entry_side, 1.0, "gd4")
  fixtures.fill(case.trade, case.trade.exit_side, 1.0, f"dd4 {closed.id}")
  assert case.run() is None


def test_partial_completion_remains_available(database):
  case = fixtures.make_case(stop_fraction=0.5)
  result = case.run()
  assert result is not None and result[0] < 0.0 and result[1] == case.stop.ft_order_tag
  assert -result[0] * case.trade.amount / case.trade.stake_amount == pytest.approx(0.5)


def test_feature_behavior_hold_does_not_early_return_over_profit_exit(database):
  case = fixtures.make_case()
  result = case.run(110.0)
  assert result is not None and result[0] < 0.0
  assert result[1] == f"{case.old.ft_order_tag} {case.old.id}"


def test_feature_behavior_hold_keeps_remaining_queue_stop(database):
  case = fixtures.make_case(old_amount=5.0)
  result = case.run(50.0)
  assert result is not None and result[0] < 0.0
  assert result[1] == f"dd{case.old.ft_order_tag[-1]} {case.old.id}"


def test_open_order_retains_native_block(database):
  case = fixtures.make_case()
  pending = fixtures.fill(case.trade, case.trade.entry_side, 1.0, "gd1", filled=0.0)
  pending.ft_is_open, pending.status = True, "open"
  assert case.run() is None


@pytest.mark.parametrize("tag,short", [("121", False), ("620", True), ("120 43", False)])
def test_other_modes_do_not_acquire_long120_hold(database, tag, short):
  case = fixtures.make_case(tag=tag, short=short, old_amount=0.5)
  result = case.run()
  setattr(case.strategy, fixtures.FEATURE, False)
  original = case.run()
  assert result == original
  assert original is not None and original[0] > 0.0


def test_feature_behavior_blocked_rescue_does_not_consume_one_shot(database):
  case = fixtures.make_case(target=5)
  case.strategy.long_grind_entry_v3.return_value = False
  case.strategy.derisk_use_grind_stops = False
  case.trade.liquidation_price = 69.0
  assert case.run(70.0) is None
  assert case.trade.get_custom_data("gd5_liquidation_rescue_used") is None


@pytest.mark.parametrize(
  "nested,top,enabled",
  [
    (None, None, False),
    (True, None, True),
    (False, None, False),
    (None, True, True),
    (None, False, False),
    (True, False, False),
    (False, True, True),
  ],
)
def test_normal_configuration_controls_admissions(database, tmp_path, nested, top, enabled):
  case = fixtures.make_case()
  config = {**case.strategy.config, "user_data_dir": tmp_path}
  if nested is not None:
    config["nfi_parameters"] = {fixtures.FEATURE: nested}
  if top is not None:
    config[fixtures.FEATURE] = top
  configured = fixtures.NostalgiaForInfinityX8(config)
  for name in ("dp", "is_futures_mode", "position_adjustment_enable", "derisk_enable", "long_grind_entry_v3"):
    setattr(configured, name, getattr(case.strategy, name))
  configured_case = fixtures.Case(configured, case.trade, case.old, case.stop)

  result = configured_case.run()

  if enabled:
    assert result is None
  else:
    assert result is not None and result[0] > 0.0 and result[1] == "gd1"
