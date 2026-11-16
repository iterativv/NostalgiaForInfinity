"""Long V4 queue-1/6 and queue-2/7 splits through shared persistent public-bot fixtures."""

from datetime import datetime
from datetime import timedelta
from math import inf
from math import nextafter
from unittest.mock import MagicMock

import pytest
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import Trade
from freqtrade.wallets import Wallets

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8
from tests.unit import test_NFIX8_v4_grind_split as split


NOW = split.NOW
v4_case = split.v4_case
quantity_bot = split.quantity_bot
split_bot = split.split_bot
funding_case = split.funding_case
funded_grind_case = split.funded_grind_case
legacy_grind_case = split.legacy_grind_case
restore_database_sessions = split.restore_database_sessions
add_fill = split.add_fill
adjust = split.adjust
candles = split.candles
settle = split.settle


@pytest.fixture(params=[1, 2], ids=["1-to-6", "2-to-7"])
def level(request):
  return request.param


@pytest.fixture
def lower(level):
  return {1: 6, 2: 7}[level]


@pytest.fixture
def lower_stakes(level):
  return (200.0, 200.0) if level == 1 else (140.0, 160.0)


@pytest.fixture
def split_case(v4_case, level):
  strategy, trade, _ = v4_case
  for market in ("spot", "futures"):
    for name in ("stakes", "thresholds", "derisk", "profit_threshold"):
      strategy.__dict__.pop(f"system_v4_grind_{level}_{name}_{market}", None)
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", True)
  strategy.long_grind_entry_v4 = MagicMock(return_value=True)
  strategy.dp.send_msg = MagicMock()
  trade.liquidation_price = None
  return strategy, trade


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "level,use_derisk",
  [(1, False), (2, True)],
  ids=["1-to-6-derisk-disabled-isolation", "2-to-7-default-derisk-enabled"],
)
def test_engine_settles_four_allocations_with_declared_derisk_policy(
  split_bot, split_case, mocker, caplog, level, lower, use_derisk
):
  strategy, trade = split_case
  # Parent 1 is allocation isolation; parent 2 retains its default de-risk setting throughout.
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", use_derisk)
  trade.orders[-1].ft_order_tag = "seed"
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  expected = (
    [(100.0, 200.0, 1), (80.0, 200.0, 1), (75.0, 200.0, 6), (59.0, 200.0, 6)]
    if level == 1
    else [(90.0, 100.0, 2), (82.0, 120.0, 2), (76.0, 140.0, 7), (69.0, 160.0, 7)]
  )

  for index, (rate, stake, queue) in enumerate(expected):
    clock.return_value = NOW + timedelta(hours=7 * index)
    candles(split_case, rate, signal=True)
    split_bot.exchange.get_rates.return_value = (rate, rate)
    split_bot.exchange.create_order.reset_mock()
    before = trade.amount
    split_bot.check_and_call_adjust_trade_position(trade)
    assert adjustment.spy_exception is None
    assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{queue}_entry"
    assert order.ft_order_side == trade.entry_side
    assert order.amount * rate == pytest.approx(stake, abs=1e-6)
    assert strategy._grind_entry_tag == (f"g{lower}" if queue == lower else "g0")
    settle(split_bot, trade, order, when=clock.return_value)
    assert trade.amount == pytest.approx(before + order.amount, abs=1e-8)

  clock.return_value += timedelta(hours=7)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return is None
  split_bot.exchange.create_order.assert_not_called()
  assert [o.ft_order_tag for o in trade.select_filled_orders(trade.entry_side)][-4:] == [
    f"grind_{level}_entry",
    f"grind_{level}_entry",
    f"grind_{lower}_entry",
    f"grind_{lower}_entry",
  ]
  lower_amount = sum(o.safe_filled for o in trade.orders if o.ft_order_tag == f"grind_{lower}_entry")
  clock.return_value += timedelta(hours=7)
  exit_rate = 72.0 if level == 1 else 80.0
  candles(split_case, exit_rate, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (exit_rate, exit_rate)
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  order = trade.orders[-1]
  assert order.ft_order_tag.startswith(f"grind_{lower}_exit ")
  assert order.amount == pytest.approx(lower_amount, abs=1e-8)
  settle(split_bot, trade, order, when=clock.return_value)

  clock.return_value += timedelta(hours=7)
  recycle_rate = 75.0 if level == 1 else 76.0
  candles(split_case, recycle_rate, signal=True)
  split_bot.exchange.get_rates.return_value = (recycle_rate, recycle_rate)
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return == (pytest.approx(expected[2][1] / trade.leverage), f"grind_{lower}_entry")
  settle(split_bot, trade, trade.orders[-1], when=clock.return_value)
  assert all(record.levelno < 40 for record in caplog.records)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (False, 5.0)], indirect=True)
@pytest.mark.parametrize("offset,allowed", [(-0.0001, True), (0.0, True), (0.0001, False)])
def test_lower_uses_inclusive_weighted_entry_quote_not_last_parent_spacing(
  split_case, offset, allowed, level, lower, lower_stakes
):
  strategy, trade = split_case
  latest = add_fill(split_case, f"grind_{level}_entry", 3.0, 80.0)
  rate = 85.0 * 0.90 + offset
  assert (rate - latest.safe_price) / latest.safe_price > (-0.20 if level == 1 else -0.08)
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  candles(split_case, rate, signal=True)
  result = adjust(split_case, rate)
  assert result == ((pytest.approx(lower_stakes[0] / trade.leverage), f"grind_{lower}_entry") if allowed else None)
  if allowed:
    assert strategy._grind_entry_tag == f"g{lower}"


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_parent_gate_uses_entry_quote_even_when_exit_quote_is_lower(split_case, level, lower):
  add_fill(split_case, f"grind_{level}_entry", 3.0, 80.0)
  assert adjust(split_case, 74.0, entry_rate=76.5001) is None
  assert adjust(split_case, 74.0, entry_rate=76.5)[1] == f"grind_{lower}_entry"


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("gap,allowed", [(0.10, True), (0.11, False)])
def test_gap_loads_without_advanced_mode(split_case, tmp_path, nested, gap, allowed, level, lower, lower_stakes):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  setting = f"system_v4_grind_{lower}_primary_gap"
  config = strategy.config.copy()
  config.update(user_data_dir=tmp_path, trading_mode=trade.trading_mode, nfi_advanced_mode=False)
  config["nfi_parameters"] = {setting: gap} if nested else {}
  if not nested:
    config[setting] = gap
  strategy.target_profit_cache = MagicMock()
  strategy.__init__(config)
  assert getattr(strategy, setting) == gap
  result = adjust(split_case, 90.0)
  assert result == ((pytest.approx(lower_stakes[0]), f"grind_{lower}_entry") if allowed else None)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "state,eligible",
  [
    ("empty", False),
    ("one", False),
    ("two", True),
    ("unfilled-canceled", False),
    ("unfilled-open", False),
    ("closed-then-one", False),
    ("closed-then-two", True),
    ("overfull-3", False),
    ("overfull-4", False),
    ("overfull-5", False),
  ],
)
def test_lower_needs_exactly_two_current_filled_parents(split_case, state, eligible, level, lower, lower_stakes):
  _, trade = split_case
  if state == "empty":
    trade.orders[-1].ft_order_tag = "seed"
  elif state.startswith("unfilled"):
    order = add_fill(split_case, f"grind_{level}_entry", filled=0.0)
    if state == "unfilled-open":
      order.ft_is_open = True
      order.status = "open"
  elif state.startswith("closed"):
    add_fill(split_case, f"grind_{level}_entry")
    add_fill(split_case, f"grind_{level}_exit old-cluster", 2.0, side=trade.exit_side)
    add_fill(split_case, f"grind_{level}_entry")
    if state == "closed-then-two":
      add_fill(split_case, f"grind_{level}_entry")
  elif state == "two":
    add_fill(split_case, f"grind_{level}_entry")
  elif state.startswith("overfull"):
    for _ in range(int(state[-1]) - 1):
      add_fill(split_case, f"grind_{level}_entry")
  result = adjust(split_case, 90.0)
  if eligible:
    assert result == (pytest.approx(lower_stakes[0] / trade.leverage), f"grind_{lower}_entry")
  else:
    assert result is None or result[1] != f"grind_{lower}_entry"


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("parents", [3, 4, 5])
@pytest.mark.parametrize("reason,rate", [("exit", 110.0), ("derisk", 77.0)])
def test_old_overfull_parent_inventory_is_fully_settled(split_bot, split_case, mocker, parents, reason, rate, level):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  for _ in range(parents - 1):
    add_fill(split_case, f"grind_{level}_entry")
  ids = " ".join(str(order.id) for order in reversed(trade.orders[2:]))
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{level}_{reason} {ids}"
  assert order.amount == pytest.approx(parents, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("length", [0, 1, 2, 3, 4, 5])
def test_lower_uses_only_actual_remaining_scaled_allocations(split_case, length, level, lower):
  strategy, trade = split_case
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", False)
  original = [0.03, 0.04, 0.08, 0.11, 0.20][:length]
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_{level}_stakes_{market}", original)
  add_fill(split_case, f"grind_{level}_entry")
  minimum = 40.0 / trade.leverage
  result = adjust(split_case, 90.0, min_stake=minimum)
  if length <= 2:
    assert result is None
    return
  assert result == (pytest.approx((80.0 * 4.0 / 3.0) / trade.leverage), f"grind_{lower}_entry")
  add_fill(split_case, result[1], result[0] * trade.leverage / 90.0, 90.0)
  result = adjust(split_case, 70.0, min_stake=minimum)
  if length == 3:
    assert result is None
  else:
    assert result == (pytest.approx((110.0 * 4.0 / 3.0) / trade.leverage), f"grind_{lower}_entry")
    add_fill(split_case, result[1], result[0] * trade.leverage / 70.0, 70.0)
    result = adjust(split_case, 69.0, min_stake=minimum)
    assert result is None
  assert getattr(strategy, f"system_v4_grind_{level}_stakes_spot") == original


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("length", [0, 1])
def test_parent_cap_respects_short_custom_ladders(split_case, length, level):
  strategy, _ = split_case
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_{level}_stakes_{market}", [0.20][:length])
  assert adjust(split_case, 80.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_parent_never_admits_original_third_allocation(split_case, level, lower):
  strategy, _ = split_case
  add_fill(split_case, f"grind_{level}_entry", 1.0, 120.0)
  setattr(strategy, f"system_v4_grind_{lower}_primary_gap", 0.30)
  assert adjust(split_case, 93.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_lower_keeps_original_fourth_spacing_and_recycles(split_case, level, lower, lower_stakes):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry", 1.0, 100.0 if level == 1 else 120.0)
  first = add_fill(split_case, f"grind_{lower}_entry", 0.5, 100.0)
  # Each lower uses its original index 3, not the parent's original index 1.
  blocked, allowed = (80.5, 78.5) if level == 1 else (92.0, 90.0)
  assert adjust(split_case, blocked) is None
  result = adjust(split_case, allowed)
  assert result == (pytest.approx(lower_stakes[1] / trade.leverage), f"grind_{lower}_entry")
  second = add_fill(split_case, result[1], result[0] * trade.leverage / allowed, allowed)
  closed = add_fill(
    split_case,
    f"grind_{lower}_exit {second.id} {first.id}",
    first.safe_filled + second.safe_filled,
    100.0,
    side=trade.exit_side,
  )
  strategy.order_filled(trade.pair, trade, closed, NOW)
  assert adjust(split_case, 90.0) == (pytest.approx(lower_stakes[0] / trade.leverage), f"grind_{lower}_entry")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "gate", ["retry", "timing", "stake", "wallet", "queue", "spacing", "open_order", "signal", "unlock"]
)
def test_lower_admission_retains_native_guards(split_case, gate, level, lower):
  strategy, trade = split_case
  parent = add_fill(split_case, f"grind_{level}_entry")
  max_stake = 10000.0
  if gate == "retry":
    parent.order_filled_date = NOW - timedelta(minutes=4)
  elif gate == "timing":
    parent.order_filled_date = NOW - timedelta(minutes=10)
    add_fill(split_case, "exit_normal", 0.1, 90.0, side=trade.exit_side).order_filled_date = NOW - timedelta(minutes=9)
  elif gate == "stake":
    strategy.system_v4_max_stake = 0.1
  elif gate == "wallet":
    max_stake = 1.0
  elif gate == "queue":
    add_fill(split_case, f"grind_{lower}_entry", 0.1)
    add_fill(split_case, f"grind_{lower}_entry", 0.1)
  elif gate == "spacing":
    add_fill(split_case, f"grind_{lower}_entry", 0.1, 98.0 if level == 1 else 95.0)
  elif gate == "open_order":
    order = add_fill(split_case, f"grind_{lower}_entry", filled=0.0)
    order.ft_is_open = True
    order.status = "open"
  elif gate == "signal":
    strategy.long_grind_entry_v4.return_value = False
  else:
    strategy.system_v4_grind_only_after_derisk_enable = True
  assert adjust(split_case, 90.0, max_stake=max_stake) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_lower_does_not_borrow_four_fallback_signal(split_case, level):
  strategy, _ = split_case
  add_fill(split_case, f"grind_{level}_entry")
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  candles(split_case, 90.0, fallback=True)
  assert adjust(split_case, 90.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "enabled,use_derisk,cap,eligible",
  [(True, True, 1.0, True), (False, True, 1.0, False), (True, False, 1.0, False), (True, True, 0.5, False)],
)
def test_lower_pre_derisk_inherits_parent_controls(
  split_case, enabled, use_derisk, cap, eligible, level, lower, lower_stakes
):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  strategy.system_v4_grind_entry_before_derisk_enable = enabled
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", use_derisk)
  strategy.system_v4_grind_entry_before_derisk_max_stake = cap
  add_fill(split_case, f"grind_{level}_entry", 1.0, 120.0)
  add_fill(split_case, f"grind_{lower}_entry", 1.0, 110.0)
  result = adjust(split_case, 86.5)
  assert result == ((pytest.approx(lower_stakes[1] / trade.leverage), f"grind_{lower}_entry") if eligible else None)
  if eligible:
    assert strategy._grind_entry_tag == f"g{lower}_pre_derisk"


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("parent_exit", ["exit", "derisk"])
@pytest.mark.parametrize("reason,rate", [("exit", 85.0), ("derisk", 50.0)])
def test_orphan_lower_retains_own_profit_derisk_highwaters_and_reload(
  split_bot, split_case, mocker, caplog, parent_exit, reason, rate, level, lower
):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  second_parent = add_fill(split_case, f"grind_{level}_entry")
  first = add_fill(split_case, f"grind_{lower}_entry", 0.6, 80.0)
  second = add_fill(split_case, f"grind_{lower}_entry", 0.8, 70.0)
  candles(split_case, 82.0)
  assert adjust(split_case, 82.0) is None
  high_water = trade.get_custom_data(f"grind_{lower}_cluster_max_profit_rate")
  assert high_water > 0.0
  trade.set_custom_data(f"grind_{level}_cluster_max_profit_rate", 1.0)
  parent = add_fill(
    split_case, f"grind_{level}_{parent_exit} {second_parent.id} {trade.orders[2].id}", 2.0, side=trade.exit_side
  )
  strategy.order_filled(trade.pair, trade, parent, NOW)
  assert trade.get_custom_data(f"grind_{level}_cluster_max_profit_rate") == 0.0
  assert trade.get_custom_data(f"grind_{lower}_cluster_max_profit_rate") == high_water
  trade_id = trade.id
  Trade.session.flush()
  Trade.session.expunge_all()
  trade = Trade.session.get(Trade, trade_id)
  assert trade.get_custom_data("system_version") == "system_v4"
  candles((strategy, trade), rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  before = trade.amount
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{lower}_{reason} {second.id} {first.id}"
  assert order.amount == pytest.approx(1.4, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(before - 1.4, abs=1e-8)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)
  assert trade.get_custom_data(f"grind_{lower}_cluster_max_profit_stake") == 0.0
  assert trade.get_custom_data(f"grind_{lower}_cluster_max_profit_rate") == 0.0
  assert all(record.levelno < 40 for record in caplog.records)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 90.0), ("derisk", 60.0)])
def test_lower_base_fee_partial_cancel_retries_net_remainder_after_reload(
  split_bot, split_case, mocker, reason, rate, level, lower
):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  add_fill(split_case, f"grind_{level}_derisk 3", 1.0, side=trade.exit_side)
  entry = add_fill(split_case, f"grind_{lower}_entry", 1.0, 80.0)
  split.quantity.settle_base_fee(split_bot, trade, entry, 0.001)
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  first = trade.orders[-1]
  assert first.ft_order_tag == f"grind_{lower}_{reason} {entry.id}"
  assert first.amount == pytest.approx(0.999, abs=1e-8)
  settle(split_bot, trade, first, 0.4, "canceled")
  trade_id = trade.id
  Trade.session.expunge_all()
  trade = Trade.session.get(Trade, trade_id)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry.ft_order_tag == first.ft_order_tag
  assert retry.amount == pytest.approx(0.599, abs=1e-8)
  settle(split_bot, trade, retry)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize(
  "requested,filled,prior_exit,eligible,full_close",
  [
    (0.5, 0.453125, 4.0, True, False),
    (0.5, 0.4609375, 4.0, False, False),
    (0.5, 0.47, 4.0, False, False),
    (1.0, 0.91, 9.99, False, False),
    (7.0, 6.953125, 4.0, True, True),
  ],
  ids=["current-value-only", "exact-minimum", "below-minimum", "reserve", "full-close"],
)
def test_lower_partial_retry_retains_minimum_reserve_and_full_close(
  split_bot, split_case, mocker, requested, filled, prior_exit, eligible, full_close, level, lower
):
  strategy, trade = split_case
  setattr(strategy, f"system_v4_grind_{level}_enable", False)
  strategy.long_grind_entry_v4.return_value = False
  trade.orders[-1].ft_order_tag = f"grind_{lower}_entry"
  prior = trade.orders[1]
  prior.amount = prior.ft_amount = prior.filled = prior_exit
  prior.cost = prior_exit * 100.0
  trade.recalc_trade_from_orders()
  tag = f"grind_{lower}_exit {trade.orders[-1].id}"
  canceled = add_fill(split_case, tag, requested, 128.0, filled=filled, side=trade.exit_side)
  candles(split_case, 128.0, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (128.0, 128.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  if eligible:
    split_bot.exchange.create_order.assert_called_once()
    retry = trade.orders[-1]
    assert retry.ft_order_tag == tag
    assert retry.amount == pytest.approx(requested - filled, abs=1e-8)
    settle(split_bot, trade, retry)
    assert trade.is_open is not full_close
  else:
    split_bot.exchange.create_order.assert_not_called()
    assert trade.orders[-1] is canceled


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("amount,eligible", [(0.03, False), (0.0390625, False), (0.046875, True)])
def test_lower_profit_exit_uses_current_value_minimum(split_bot, split_case, mocker, amount, eligible, lower):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  trade.orders[-1].ft_order_tag = "seed"
  entry = add_fill(split_case, f"grind_{lower}_entry", amount)
  candles(split_case, 128.0, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (128.0, 128.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  if eligible:
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{lower}_exit {entry.id}"
    assert order.amount == pytest.approx(amount, abs=1e-8)
    assert -adjustment.spy_return[0] < 5.0
    before = trade.amount
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before - amount, abs=1e-8)
  else:
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 110.0), ("derisk", 77.0)])
def test_lower_fee_aware_reduction_keeps_native_residual(split_bot, split_case, mocker, reason, rate, lower):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  prior = trade.orders[1]
  prior.amount = prior.ft_amount = prior.filled = 9.99
  prior.cost = 999.0
  trade.orders[-1].ft_order_tag = f"grind_{lower}_entry"
  trade.recalc_trade_from_orders()
  split.quantity.settle_base_fee(split_bot, trade, trade.orders[-1], 0.001)
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  order = trade.orders[-1]
  assert order.ft_order_tag.startswith(f"grind_{lower}_{reason} ")
  assert order.amount == pytest.approx(1.009 - 5.0 * 1.55 / rate, abs=1e-8)
  assert order.amount < 0.999
  settle(split_bot, trade, order)
  assert trade.amount * rate == pytest.approx(5.0 * 1.55, abs=1e-6)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("funding_ratio", [0.0, 0.999, 1.0])
def test_real_wallet_blocks_unfunded_lower_add_but_not_own_derisk(
  split_bot, split_case, mocker, funding_ratio, level, lower, lower_stakes
):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  entry = add_fill(split_case, f"grind_{lower}_entry", 1.0, 110.0)
  proposal = lower_stakes[1] / trade.leverage
  free = proposal * funding_ratio
  wallet = trade.stake_amount - trade.realized_profit + free
  if funding_ratio == 1.0:
    # Wallet subtraction can round nominal exact funding below the proposal.
    wallet = nextafter(wallet, inf)
  split_bot.config["dry_run_wallet"] = wallet
  split_bot.wallets = Wallets(split_bot.config, split_bot.exchange)
  available = split_bot.wallets.get_available_stake_amount()
  assert available == pytest.approx(free)
  assert (available >= proposal) == (funding_ratio == 1.0)
  split_bot.exchange.get_rates.return_value = (85.0, 85.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  if funding_ratio == 1.0:
    split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
    mocker.spy(split_bot, "execute_entry")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(free)
  if funding_ratio == 1.0:
    split_bot.execute_entry.assert_called_once_with(
      trade.pair,
      proposal,
      price=85.0,
      trade=trade,
      is_short=False,
      mode="pos_adjust",
      enter_tag=f"grind_{lower}_entry",
    )
    assert split_bot.execute_entry.spy_exception is None
    assert split_bot.execute_entry.spy_return is True
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{lower}_entry"
    assert order.ft_order_side == trade.entry_side
    assert order.amount * 85.0 == pytest.approx(lower_stakes[1], abs=1e-6)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(9.0 + lower_stakes[1] / 85.0, abs=1e-8)
  else:
    split_bot.execute_entry.assert_not_called()
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{lower}_derisk {entry.id}"
    assert order.amount == pytest.approx(1.0, abs=1e-8)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(8.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 85.0), ("derisk", 50.0)])
@pytest.mark.parametrize("funded", [False, True])
def test_buyback_priority_and_unfunded_orphan_lower_management(
  split_bot, split_case, mocker, reason, rate, funded, level, lower
):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  strategy.system_v4_buyback_1_enable = True
  strategy.long_buyback_entry_v4 = MagicMock(return_value=True)
  first_parent = trade.orders[-1]
  second_parent = add_fill(split_case, f"grind_{level}_entry")
  lower_entry = add_fill(split_case, f"grind_{lower}_entry", 1.0, 80.0)
  add_fill(split_case, f"grind_{level}_exit {second_parent.id} {first_parent.id}", 2.0, side=trade.exit_side)
  add_fill(split_case, "derisk_level_4", 0.1, side=trade.exit_side)
  buyback_stake = 1000.0 / trade.leverage
  free = buyback_stake * (1.25 if funded else 0.1)
  split_bot.config["dry_run_wallet"] = trade.stake_amount - trade.realized_profit + free
  split_bot.wallets = Wallets(split_bot.config, split_bot.exchange)
  assert split_bot.wallets.get_available_stake_amount() == pytest.approx(free)
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  before = trade.amount
  if funded:
    split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
    mocker.spy(split_bot, "execute_entry")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  strategy.long_buyback_entry_v4.assert_called_once()
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(free)
  if funded:
    split_bot.execute_entry.assert_called_once_with(
      trade.pair,
      buyback_stake,
      price=rate,
      trade=trade,
      is_short=False,
      mode="pos_adjust",
      enter_tag="buyback_1_entry",
    )
    assert split_bot.execute_entry.spy_exception is None
    assert split_bot.execute_entry.spy_return is True
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == "buyback_1_entry"
    assert order.ft_order_side == trade.entry_side
    assert order.amount * rate == pytest.approx(1000.0, abs=1e-6)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before + 1000.0 / rate, abs=1e-8)
  else:
    split_bot.execute_entry.assert_not_called()
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{lower}_{reason} {lower_entry.id}"
    assert order.amount == pytest.approx(1.0, abs=1e-8)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before - 1.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_unfunded_buyback_blocks_even_affordable_new_lower(split_bot, split_case, mocker, level, lower_stakes):
  strategy, trade = split_case
  strategy.system_v4_buyback_1_enable = True
  strategy.long_buyback_entry_v4 = MagicMock(return_value=True)
  add_fill(split_case, f"grind_{level}_entry")
  add_fill(split_case, "derisk_level_4", 0.1, side=trade.exit_side)
  free = 250.0 / trade.leverage
  split_bot.config["dry_run_wallet"] = trade.stake_amount - trade.realized_profit + free
  split_bot.wallets = Wallets(split_bot.config, split_bot.exchange)
  candles(split_case, 90.0)
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  strategy.long_buyback_entry_v4.assert_called_once()
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(free)
  assert free > lower_stakes[0] / trade.leverage
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("emergency", [False, True])
def test_native_five_and_emergency_precede_lower(split_case, emergency, level):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  candles(split_case, 84.0)
  strategy.system_v4_grind_5_enable = True
  trade.liquidation_price = 80.0
  if emergency:
    strategy.derisk_enable = True
    strategy.system_v4_derisk_level_3_enable = True
    strategy.system_v4_derisk_level_3_liquidation_enable = True
  result = adjust(split_case, 84.0)
  if emergency:
    assert result == (pytest.approx(-500.0 / trade.leverage), "derisk_level_3")
  else:
    assert result == (pytest.approx(50.0 / trade.leverage), "grind_5_entry")
    assert strategy._grind_entry_tag == "g5_liq1"


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("inventory,eligible", [(1, True), (2, False)])
def test_lower_inventory_counts_toward_native_rescue_limit(split_case, inventory, eligible, level, lower):
  strategy, trade = split_case
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  strategy.system_v4_grind_5_enable = True
  strategy.system_v4_grind_5_liquidation_rescue_enable = True
  add_fill(split_case, f"grind_{level}_exit 3", 1.0, side=trade.exit_side)
  add_fill(split_case, "exit_normal", 4.0, side=trade.exit_side)
  for _ in range(inventory):
    add_fill(split_case, f"grind_{lower}_entry", 0.1)
  candles(split_case, 93.9)
  trade.liquidation_price = 90.0
  result = adjust(split_case, 93.9)
  assert result == ((pytest.approx(50.0 / trade.leverage), "grind_5_entry") if eligible else None)
  if eligible:
    assert strategy._grind_entry_tag == "g5_liq2"


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("queue,stake", [(3, 100.0), (4, 50.0), (5, 50.0), (9, 70.0)])
def test_original_queues_and_accepted_nine_precede_lower(split_case, queue, stake, level):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  if queue == 9:
    strategy.system_v4_grind_4_enable = True
    add_fill(split_case, "grind_4_entry")
    add_fill(split_case, "grind_4_entry")
  else:
    setattr(strategy, f"system_v4_grind_{queue}_enable", True)
  assert adjust(split_case, 90.0) == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 110.0), ("derisk", 77.0)])
def test_accepted_nine_management_precedes_lower_management(split_case, reason, rate, level, lower):
  strategy, trade = split_case
  setattr(strategy, f"system_v4_grind_{level}_enable", False)
  strategy.long_grind_entry_v4.return_value = False
  trade.orders[-1].ft_order_tag = "seed"
  earlier = add_fill(split_case, "grind_9_entry")
  add_fill(split_case, f"grind_{lower}_entry")
  candles(split_case, rate, profit_exit=reason == "exit")
  result = adjust(split_case, rate)
  assert result[1] == f"grind_9_{reason} {earlier.id}"


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_global_derisk_ends_lower_under_native_order_protocol(split_case, level, lower):
  strategy, trade = split_case
  setattr(strategy, f"system_v4_grind_{level}_enable", False)
  strategy.long_grind_entry_v4.return_value = False
  add_fill(split_case, f"grind_{lower}_entry", 0.5, 80.0)
  add_fill(split_case, "derisk_global", 0.5, 90.0, side=trade.exit_side)
  candles(split_case, 110.0, profit_exit=True)
  assert adjust(split_case, 110.0) is None


@pytest.mark.parametrize("v4_case", [(True, 3.0)], indirect=True)
def test_short_keeps_all_original_parent_allocations(split_case, level, lower):
  strategy, trade = split_case
  strategy.system_v4_max_stake = 3.0
  setattr(strategy, f"system_v4_grind_{lower}_primary_gap", 0.99)
  allocations = (
    [(120.0, 200.0), (146.0, 200.0), (178.0, 200.0), (219.0, 200.0)]
    if level == 1
    else [(114.0, 120.0), (128.0, 140.0), (144.0, 160.0), (162.0, 180.0)]
  )
  for rate, stake in allocations:
    result = adjust(split_case, rate)
    assert result == (pytest.approx(stake / trade.leverage), f"grind_{level}_entry")
    add_fill(split_case, result[1], result[0] * trade.leverage / rate, rate)
  result = adjust(split_case, allocations[-1][0])
  assert result is not None and result[1].startswith(f"grind_{level}_derisk ")


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize(
  "funding_case,level",
  [
    ((version, parent, "grind"), parent)
    for version in (None, "system_v3", "system_v3_1", "system_v3_2")
    for parent in (1, 2)
  ],
  indirect=["funding_case"],
)
def test_earlier_systems_keep_original_third_parent_allocation(funded_grind_case, level, lower):
  strategy, trade, rate = funded_grind_case
  strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  prefix = "grinding_v2" if trade.get_custom_data("system_version") is None else "system_v3"
  setattr(strategy, f"{prefix}_max_stake", 2.0)
  setattr(strategy, f"system_v4_grind_{lower}_primary_gap", 0.99)
  add_fill((strategy, trade), f"grind_{level}_entry")
  assert split.funding.adjust((strategy, trade, rate), 10000.0) == (pytest.approx(150.0), f"grind_{level}_entry")


def test_legacy_gd_route_stays_distinct_from_new_lower_queues(legacy_grind_case):
  strategy, trade, _ = legacy_grind_case
  strategy.system_v4_grind_6_primary_gap = 0.99
  strategy.system_v4_grind_7_primary_gap = 0.99
  assert split.legacy.adjust(legacy_grind_case, 1000.0) == (pytest.approx(140.0 / trade.leverage), "gd1")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [1])
def test_default_enabled_parent_derisk_wins_before_second_six_then_orphan_reduces(split_bot, split_case, mocker):
  strategy, trade = split_case
  assert NostalgiaForInfinityX8.system_v4_grind_1_use_derisk is True
  first_parent = trade.orders[-1]
  second_parent = add_fill(split_case, "grind_1_entry")
  lower = add_fill(split_case, "grind_6_entry", 1.0, 90.0)
  candles(split_case, 70.0)
  split_bot.exchange.get_rates.return_value = (70.0, 70.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  parent_exit = trade.orders[-1]
  assert parent_exit.ft_order_tag == f"grind_1_derisk {second_parent.id} {first_parent.id}"
  assert parent_exit.amount == pytest.approx(2.0, abs=1e-8)
  settle(split_bot, trade, parent_exit)
  assert trade.amount == pytest.approx(7.0, abs=1e-8)
  strategy.long_grind_entry_v4.return_value = False
  split_bot.exchange.create_order.reset_mock()

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  lower_exit = trade.orders[-1]
  assert lower_exit.ft_order_tag == f"grind_6_derisk {lower.id}"
  assert lower_exit.amount == pytest.approx(1.0, abs=1e-8)
  settle(split_bot, trade, lower_exit)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_parent_partial_retry_settles_before_any_new_lower_admission(split_bot, split_case, mocker, level):
  strategy, trade = split_case
  parent = add_fill(split_case, f"grind_{level}_entry")
  canceled = add_fill(split_case, f"grind_{level}_exit {parent.id} 3", 2.0, 90.0, filled=0.4, side=trade.exit_side)
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry.ft_order_tag == canceled.ft_order_tag
  assert retry.amount == pytest.approx(1.6, abs=1e-8)
  settle(split_bot, trade, retry)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("threshold,eligible", [(0.025, True), (0.035, False), (0.04, False)])
def test_orphan_lower_inherits_parent_profit_setting_with_parent_disabled(
  split_bot, split_case, mocker, threshold, eligible, level, lower
):
  strategy, trade = split_case
  setattr(strategy, f"system_v4_grind_{level}_enable", False)
  strategy.long_grind_entry_v4.return_value = False
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_{level}_profit_threshold_{market}", threshold)
  trade.orders[-1].ft_order_tag = "seed"
  entry = add_fill(split_case, f"grind_{lower}_entry")
  candles(split_case, 103.0, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (103.0, 103.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  if eligible:
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{lower}_exit {entry.id}"
    assert order.amount == pytest.approx(1.0, abs=1e-8)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(7.0, abs=1e-8)
  else:
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "threshold,enabled,eligible", [(-0.22, True, True), (-0.25, True, False), (-0.22, False, False)]
)
def test_orphan_lower_inherits_parent_derisk_settings(
  split_bot, split_case, mocker, threshold, enabled, eligible, level, lower
):
  strategy, trade = split_case
  setattr(strategy, f"system_v4_grind_{level}_enable", False)
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", enabled)
  strategy.long_grind_entry_v4.return_value = False
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_{level}_derisk_{market}", threshold)
  trade.orders[-1].ft_order_tag = "seed"
  entry = add_fill(split_case, f"grind_{lower}_entry")
  split_bot.exchange.get_rates.return_value = (77.0, 77.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  if eligible:
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{lower}_derisk {entry.id}"
    assert order.amount == pytest.approx(1.0, abs=1e-8)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(7.0, abs=1e-8)
  else:
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (True, 3.0)], indirect=True)
@pytest.mark.parametrize("version", [None, "system_v3", "system_v3_1", "system_v3_2", "system_v4"])
@pytest.mark.parametrize("reason", ["exit", "derisk"])
def test_lower_filled_reset_is_only_for_its_own_stored_long_v4_cluster(split_case, version, reason, lower):
  strategy, trade = split_case
  trade.set_custom_data("system_version", version)
  trade.set_custom_data(f"grind_{lower}_cluster_max_profit_stake", 12.0)
  trade.set_custom_data(f"grind_{lower}_cluster_max_profit_rate", 0.12)
  other_lower = 7 if lower == 6 else 6
  trade.set_custom_data(f"grind_{other_lower}_cluster_max_profit_rate", 0.25)
  trade.set_custom_data("grind_9_cluster_max_profit_rate", 0.25)
  order = add_fill(split_case, f"grind_{lower}_{reason} 3", 0.1, side=trade.exit_side)
  strategy.order_filled(trade.pair, trade, order, NOW)
  target = version == "system_v4" and not trade.is_short
  assert trade.get_custom_data(f"grind_{lower}_cluster_max_profit_stake") == (0.0 if target else 12.0)
  assert trade.get_custom_data(f"grind_{lower}_cluster_max_profit_rate") == (0.0 if target else 0.12)
  assert trade.get_custom_data(f"grind_{other_lower}_cluster_max_profit_rate") == 0.25
  assert trade.get_custom_data("grind_9_cluster_max_profit_rate") == 0.25


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("reason,entry_rate", [("exit", 80.0), ("derisk", 110.0)])
def test_accepted_nine_reduction_settles_before_eligible_new_lower(
  split_bot, split_case, mocker, reason, entry_rate, level
):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  earlier = add_fill(split_case, "grind_9_entry", 1.0, entry_rate)
  candles(split_case, 85.0, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (85.0, 85.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_9_{reason} {earlier.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(8.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_lower_inventory_consumes_shared_exposure_without_hiding_own_derisk(
  split_bot, split_case, mocker, level, lower
):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  entry = add_fill(split_case, f"grind_{lower}_entry", 1.0, 110.0)
  strategy.system_v4_max_stake = 0.75
  # The parent/base position alone is below the cap; the existing lower inventory takes it above.
  assert (trade.amount - 1.0) * 85.0 < 750.0 < trade.amount * 85.0
  split_bot.exchange.get_rates.return_value = (85.0, 85.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{lower}_derisk {entry.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(8.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_post_derisk_rebuy_handoff_manages_existing_lower(split_bot, split_case, mocker, lower):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  trade.enter_tag = trade.orders[0].ft_order_tag = "61"
  trade.orders[1].ft_order_tag = "derisk_level_3"
  entry = trade.orders[-1]
  entry.ft_order_tag = f"grind_{lower}_entry"
  split_bot.exchange.get_rates.return_value = (77.0, 77.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{lower}_derisk {entry.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_other_native_parent_admission_precedes_lower(split_case, level):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  other, stake = (2, 100.0) if level == 1 else (1, 200.0)
  setattr(strategy, f"system_v4_grind_{other}_enable", True)
  assert adjust(split_case, 90.0) == (pytest.approx(stake / trade.leverage), f"grind_{other}_entry")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [2])
def test_six_admits_before_seven_then_seven_uses_its_own_allocation(split_bot, split_case, mocker):
  strategy, trade = split_case
  add_fill(split_case, "grind_2_entry")
  strategy.system_v4_grind_1_enable = True
  strategy.system_v4_max_stake = 2.0
  add_fill(split_case, "grind_1_entry")
  add_fill(split_case, "grind_1_entry")
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  entry_call = mocker.spy(split_bot, "execute_entry")
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  clock.return_value = NOW

  for queue, stake in ((6, 200.0), (7, 140.0)):
    split_bot.exchange.create_order.reset_mock()
    before = trade.amount
    split_bot.check_and_call_adjust_trade_position(trade)
    assert adjustment.spy_exception is None
    assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")
    assert entry_call.spy_exception is None
    assert entry_call.spy_return is True
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{queue}_entry"
    assert order.ft_order_side == trade.entry_side
    assert order.amount * 90.0 == pytest.approx(stake, abs=1e-6)
    settle(split_bot, trade, order, when=clock.return_value)
    assert trade.amount == pytest.approx(before + stake / 90.0, abs=1e-8)
    clock.return_value += timedelta(hours=7)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [2])
@pytest.mark.parametrize("reason,rate", [("exit", 85.0), ("derisk", 50.0)])
def test_interleaved_orphan_six_and_seven_settle_independently_in_priority_order(
  split_bot, split_case, mocker, reason, rate
):
  strategy, trade = split_case
  strategy.system_v4_grind_1_enable = strategy.system_v4_grind_2_enable = False
  strategy.long_grind_entry_v4.return_value = False
  trade.orders[-1].ft_order_tag = "seed"
  first_six = add_fill(split_case, "grind_6_entry", 0.6, 80.0)
  first_seven = add_fill(split_case, "grind_7_entry", 0.8, 70.0)
  second_six = add_fill(split_case, "grind_6_entry", 0.4, 70.0)
  second_seven = add_fill(split_case, "grind_7_entry", 0.2, 60.0)
  trade.set_custom_data("grind_7_cluster_max_profit_rate", 0.25)
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  for queue, first, second in ((6, first_six, second_six), (7, first_seven, second_seven)):
    split_bot.exchange.create_order.reset_mock()
    split_bot.check_and_call_adjust_trade_position(trade)
    assert adjustment.spy_exception is None
    split_bot.execute_entry.assert_not_called()
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{queue}_{reason} {second.id} {first.id}"
    assert order.amount == pytest.approx(1.0, abs=1e-8)
    settle(split_bot, trade, order)
    assert trade.get_custom_data(f"grind_{queue}_cluster_max_profit_rate") == 0.0
    if queue == 6:
      assert trade.amount == pytest.approx(8.0, abs=1e-8)
      assert trade.get_custom_data("grind_7_cluster_max_profit_rate") >= 0.25
  assert trade.amount == pytest.approx(7.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [3])
def test_parent_three_now_uses_two_parent_and_two_lower_allocations(split_case):
  strategy, trade = split_case
  # Allocation isolation: the shipped parent de-risk priority is covered by the all-splits public-bot tests.
  strategy.system_v4_grind_3_use_derisk = False
  for rate, stake, queue in ((91.0, 120.0, 3), (83.0, 140.0, 8), (75.0, 160.0, 8)):
    result = adjust(split_case, rate)
    assert result == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")
    add_fill(split_case, result[1], stake / rate, rate)
  assert adjust(split_case, 67.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [2])
@pytest.mark.parametrize("reason,entry_rate", [("exit", 80.0), ("derisk", 110.0)])
def test_complete_six_reduction_precedes_otherwise_eligible_seven_entry(
  split_bot, split_case, mocker, reason, entry_rate
):
  strategy, trade = split_case
  add_fill(split_case, "grind_2_entry")
  earlier = add_fill(split_case, "grind_6_entry", 1.0, entry_rate)
  candles(split_case, 85.0, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (85.0, 85.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_6_{reason} {earlier.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(8.0, abs=1e-8)
