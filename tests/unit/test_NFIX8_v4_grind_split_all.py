"""Long V4 3/8 and 5/10 contracts using the existing persistent public-bot fixtures.

The unchanged shared contract bodies below run again with this module's 3/5 fixtures.
Queue-specific admission, rescue and priority tests exercise real bot order placement,
Wallets, settlement and reload; only the existing exchange/notification boundaries are modeled.
"""

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
from tests.unit import test_NFIX8_v4_grind_split_rest_two as contracts


NOW = split.NOW
v4_case = split.v4_case
quantity_bot = split.quantity_bot
split_bot = split.split_bot
split_case = contracts.split_case
funding_case = split.funding_case
funded_grind_case = split.funded_grind_case
legacy_grind_case = split.legacy_grind_case
restore_database_sessions = split.restore_database_sessions
add_fill = split.add_fill
adjust = split.adjust
candles = split.candles
settle = split.settle

# Rebind shared behavioral contracts to the 3/5 fixtures, rather than copying their bot/accounting setup.
test_buyback_priority_and_unfunded_orphan_lower_management = (
  contracts.test_buyback_priority_and_unfunded_orphan_lower_management
)
test_gap_loads_without_advanced_mode = contracts.test_gap_loads_without_advanced_mode
test_global_derisk_ends_lower_under_native_order_protocol = (
  contracts.test_global_derisk_ends_lower_under_native_order_protocol
)
test_lower_admission_retains_native_guards = contracts.test_lower_admission_retains_native_guards
test_lower_base_fee_partial_cancel_retries_net_remainder_after_reload = (
  contracts.test_lower_base_fee_partial_cancel_retries_net_remainder_after_reload
)
test_lower_does_not_borrow_four_fallback_signal = contracts.test_lower_does_not_borrow_four_fallback_signal
test_lower_fee_aware_reduction_keeps_native_residual = contracts.test_lower_fee_aware_reduction_keeps_native_residual
test_lower_inventory_consumes_shared_exposure_without_hiding_own_derisk = (
  contracts.test_lower_inventory_consumes_shared_exposure_without_hiding_own_derisk
)
test_lower_keeps_original_fourth_spacing_and_recycles = contracts.test_lower_keeps_original_fourth_spacing_and_recycles
test_lower_needs_exactly_two_current_filled_parents = contracts.test_lower_needs_exactly_two_current_filled_parents
test_lower_partial_retry_retains_minimum_reserve_and_full_close = (
  contracts.test_lower_partial_retry_retains_minimum_reserve_and_full_close
)
test_lower_pre_derisk_inherits_parent_controls = contracts.test_lower_pre_derisk_inherits_parent_controls
test_lower_profit_exit_uses_current_value_minimum = contracts.test_lower_profit_exit_uses_current_value_minimum
test_lower_uses_only_actual_remaining_scaled_allocations = (
  contracts.test_lower_uses_only_actual_remaining_scaled_allocations
)
test_old_overfull_parent_inventory_is_fully_settled = contracts.test_old_overfull_parent_inventory_is_fully_settled
test_orphan_lower_inherits_parent_derisk_settings = contracts.test_orphan_lower_inherits_parent_derisk_settings
test_orphan_lower_inherits_parent_profit_setting_with_parent_disabled = (
  contracts.test_orphan_lower_inherits_parent_profit_setting_with_parent_disabled
)
test_orphan_lower_retains_own_profit_derisk_highwaters_and_reload = (
  contracts.test_orphan_lower_retains_own_profit_derisk_highwaters_and_reload
)
test_parent_cap_respects_short_custom_ladders = contracts.test_parent_cap_respects_short_custom_ladders
test_parent_never_admits_original_third_allocation = contracts.test_parent_never_admits_original_third_allocation
test_parent_partial_retry_settles_before_any_new_lower_admission = (
  contracts.test_parent_partial_retry_settles_before_any_new_lower_admission
)
test_post_derisk_rebuy_handoff_manages_existing_lower = contracts.test_post_derisk_rebuy_handoff_manages_existing_lower
test_real_wallet_blocks_unfunded_lower_add_but_not_own_derisk = (
  contracts.test_real_wallet_blocks_unfunded_lower_add_but_not_own_derisk
)
test_unfunded_buyback_blocks_even_affordable_new_lower = (
  contracts.test_unfunded_buyback_blocks_even_affordable_new_lower
)


@pytest.fixture(params=[3, 5], ids=["3-to-8", "5-to-10"])
def level(request):
  return request.param


@pytest.fixture
def lower(level):
  return level + 5


@pytest.fixture
def lower_stakes(level):
  return (140.0, 160.0) if level == 3 else (70.0, 80.0)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_public_bot_settles_default_two_plus_two_then_exits_and_recycles(
  split_bot, split_case, mocker, caplog, level, lower, lower_stakes
):
  strategy, trade = split_case
  assert getattr(strategy, f"system_v4_grind_{level}_use_derisk") is True
  trade.orders[-1].ft_order_tag = "seed"
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  parent_stakes = (100.0, 120.0) if level == 3 else (50.0, 60.0)
  expected = list(
    zip((90.0, 82.0, 76.0, 69.0), parent_stakes + lower_stakes, (level, level, lower, lower), strict=True)
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
    assert trade.amount == pytest.approx(before + stake / rate, abs=1e-8)

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
  entries = [o for o in trade.orders if o.ft_order_tag == f"grind_{lower}_entry"]
  lower_amount = sum(o.safe_filled for o in entries)
  clock.return_value += timedelta(hours=7)
  candles(split_case, 80.0, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (80.0, 80.0)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{lower}_exit {entries[1].id} {entries[0].id}"
  assert order.amount == pytest.approx(lower_amount, abs=1e-8)
  settle(split_bot, trade, order, when=clock.return_value)
  assert trade.get_custom_data(f"grind_{lower}_cluster_max_profit_rate") == 0.0
  clock.return_value += timedelta(hours=7)
  candles(split_case, 76.0, signal=True)
  split_bot.exchange.get_rates.return_value = (76.0, 76.0)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return == (pytest.approx(lower_stakes[0] / trade.leverage), f"grind_{lower}_entry")
  split_bot.exchange.create_order.assert_called_once()
  settle(split_bot, trade, trade.orders[-1], when=clock.return_value)
  assert all(record.levelno < 40 for record in caplog.records)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (False, 5.0)], indirect=True)
@pytest.mark.parametrize("offset,allowed", [(-0.0001, True), (0.0, True), (0.0001, False)])
def test_public_bot_uses_inclusive_weighted_parent_entry_quote(
  split_bot, split_case, mocker, offset, allowed, level, lower, lower_stakes
):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry", 3.0, 80.0)
  # The parent average is 85; the whole-trade and latest-parent averages are different.
  entry_quote = 85.0 * 0.90 + offset
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  candles(split_case, entry_quote, signal=True)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  split_bot.exchange.get_rates.return_value = (entry_quote, 74.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  before = trade.amount
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.call_args.kwargs["current_entry_rate"] == entry_quote
  if allowed:
    assert adjustment.spy_return == (pytest.approx(lower_stakes[0] / trade.leverage), f"grind_{lower}_entry")
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{lower}_entry"
    assert order.amount * entry_quote == pytest.approx(lower_stakes[0], abs=1e-6)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before + lower_stakes[0] / entry_quote, abs=1e-8)
  else:
    assert adjustment.spy_return is None
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_shipped_parent_derisk_precedes_second_lower_then_orphan_reduces(split_bot, split_case, mocker, level, lower):
  strategy, trade = split_case
  assert getattr(NostalgiaForInfinityX8, f"system_v4_grind_{level}_use_derisk") is True
  first_parent = trade.orders[-1]
  second_parent = add_fill(split_case, f"grind_{level}_entry")
  entry = add_fill(split_case, f"grind_{lower}_entry", 1.0, 90.0)
  candles(split_case, 70.0)
  split_bot.exchange.get_rates.return_value = (70.0, 70.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{level}_derisk {second_parent.id} {first_parent.id}"
  assert order.amount == pytest.approx(2.0, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(7.0, abs=1e-8)
  strategy.long_grind_entry_v4.return_value = False
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{lower}_derisk {entry.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 3.0), (False, 5.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
def test_native_rescue_fills_first_two_parent_steps_but_never_unlocks_ten_alone(split_bot, split_case, mocker, caplog):
  strategy, trade = split_case
  trade.orders[-1].ft_order_tag = "seed"
  add_fill(split_case, "exit_normal", 5.0, side=trade.exit_side)
  strategy.system_v4_grind_5_liquidation_rescue_enable = True
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  entries = []
  for index, (rate, liquidation, stake) in enumerate(((93.9, 90.0, 50.0), (87.0, 80.0, 60.0))):
    clock.return_value = NOW + timedelta(hours=7 * index)
    trade.liquidation_price = liquidation
    candles(split_case, rate)
    split_bot.exchange.get_rates.return_value = (rate, rate)
    split_bot.exchange.create_order.reset_mock()
    split_bot.check_and_call_adjust_trade_position(trade)
    assert adjustment.spy_exception is None
    assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), "grind_5_entry")
    assert strategy._grind_entry_tag == "g5_liq2"
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == "grind_5_entry"
    assert order.amount * rate == pytest.approx(stake, abs=1e-6)
    settle(split_bot, trade, order, when=clock.return_value)
    entries.append(order)

  clock.return_value += timedelta(hours=7)
  trade.liquidation_price = 75.0
  candles(split_case, 81.0)
  split_bot.exchange.get_rates.return_value = (81.0, 81.0)
  split_bot.exchange.create_order.reset_mock()
  parent_average = sum(o.safe_filled * o.safe_price for o in entries) / sum(o.safe_filled for o in entries)
  assert 81.0 <= parent_average * 0.90
  assert trade.liquidation_price < 81.0 < trade.liquidation_price * 1.20
  assert -0.15 < (81.0 - entries[-1].safe_price) / entries[-1].safe_price < -0.05
  assert trade.stake_amount + 70.0 / trade.leverage <= 500.0 / trade.leverage
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return is None
  split_bot.exchange.create_order.assert_not_called()
  assert [o.ft_order_tag for o in entries] == ["grind_5_entry", "grind_5_entry"]
  assert all(record.levelno < 40 for record in caplog.records)


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("inventory,allowed", [(1, True), (2, False)])
def test_new_lower_inventory_participates_in_all_open_native_rescue_count(
  split_bot, split_case, mocker, inventory, allowed, lower
):
  strategy, trade = split_case
  trade.orders[-1].ft_order_tag = "seed"
  add_fill(split_case, "exit_normal", 4.0, side=trade.exit_side)
  for _ in range(inventory):
    add_fill(split_case, f"grind_{lower}_entry", 0.1)
  strategy.system_v4_grind_5_enable = True
  strategy.system_v4_grind_5_liquidation_rescue_enable = True
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  trade.liquidation_price = 90.0
  candles(split_case, 93.9)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  split_bot.exchange.get_rates.return_value = (93.9, 93.9)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  if allowed:
    assert adjustment.spy_return == (pytest.approx(50.0 / trade.leverage), "grind_5_entry")
    assert strategy._grind_entry_tag == "g5_liq2"
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == "grind_5_entry"
    assert order.amount * 93.9 == pytest.approx(50.0, abs=1e-6)
    settle(split_bot, trade, order)
  else:
    assert adjustment.spy_return is None
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 3.0), (False, 5.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
@pytest.mark.parametrize(
  "remaining,minimum,allowed",
  [(4.5, 5.0, True), (4.6, 5.0, False), (4.45, 40.0, False), (4.4, 40.0, True)],
)
def test_native_rescue_budget_includes_minimum_uplift_without_extra_capital(
  split_bot, split_case, mocker, remaining, minimum, allowed
):
  strategy, trade = split_case
  trade.orders[-1].ft_order_tag = "seed"
  prior = trade.orders[1]
  prior.amount = prior.ft_amount = prior.filled = 11.0 - remaining
  prior.cost = prior.filled * 100.0
  trade.recalc_trade_from_orders()
  assert trade.stake_amount == pytest.approx(remaining * 100.0 / trade.leverage)
  strategy.system_v4_grind_5_liquidation_rescue_enable = True
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  trade.liquidation_price = 90.0
  candles(split_case, 93.9)
  split_bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  split_bot.exchange.get_rates.return_value = (93.9, 93.9)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  if allowed:
    proposal = max(50.0, minimum * 1.5) / trade.leverage
    assert adjustment.spy_return == (pytest.approx(proposal), "grind_5_entry")
    assert strategy._grind_entry_tag == "g5_liq2"
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == "grind_5_entry"
    assert order.amount * 93.9 / trade.leverage == pytest.approx(proposal, abs=1e-6)
    settle(split_bot, trade, order)
    assert trade.stake_amount <= 500.0 / trade.leverage + 1e-6
  else:
    assert adjustment.spy_return is None
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
@pytest.mark.parametrize(
  "rate,liquidation,threshold,enabled,allowed",
  [
    (95.0, 90.0, 0.05, True, False),
    (94.9, 90.0, 0.05, True, True),
    (96.0, 90.0, 0.04, True, False),
    (95.9, 90.0, 0.04, True, True),
    (93.9, 90.0, 0.05, False, False),
    (93.9, None, 0.05, True, False),
    (93.9, 0.0, 0.05, True, False),
    (93.9, -1.0, 0.05, True, False),
    (93.9, 50.0, 0.05, True, False),
    (93.9, 93.9, 0.05, True, False),
    (93.9, 100.0, 0.05, True, False),
    (96.0, 80.0, 0.03, True, False),
  ],
)
def test_native_rescue_keeps_strict_loss_and_positive_noncrossed_liquidation_guards(
  split_bot, split_case, mocker, rate, liquidation, threshold, enabled, allowed
):
  strategy, trade = split_case
  trade.orders[-1].ft_order_tag = "seed"
  add_fill(split_case, "exit_normal", 4.0, side=trade.exit_side)
  strategy.system_v4_grind_5_liquidation_rescue_enable = enabled
  strategy.system_v4_grind_5_liquidation_rescue_threshold = threshold
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  trade.liquidation_price = liquidation
  candles(split_case, rate)
  split_bot.exchange.get_rates.return_value = (rate, rate)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  if allowed:
    assert adjustment.spy_return == (pytest.approx(50.0 / trade.leverage), "grind_5_entry")
    assert strategy._grind_entry_tag == "g5_liq2"
    split_bot.exchange.create_order.assert_called_once()
    settle(split_bot, trade, trade.orders[-1])
  else:
    assert adjustment.spy_return is None
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
@pytest.mark.parametrize("route", ["fallback", "liquidation", "ordinary", "pre_derisk"])
@pytest.mark.parametrize("minimum", [5.0, 60.0])
@pytest.mark.parametrize("funded", [False, True])
def test_ten_uses_own_applicable_five_routes_actual_lower_step_and_real_wallet(
  split_bot, split_case, mocker, route, minimum, funded
):
  strategy, trade = split_case
  if route == "liquidation" and not strategy.is_futures_mode:
    # This case proves the native futures-only route does not become a spot entry.
    expected = False
  else:
    expected = funded
  add_fill(split_case, "grind_5_entry")
  if route == "fallback":
    add_fill(split_case, "derisk_level_1", 0.1, side=trade.exit_side)
  if route == "pre_derisk":
    add_fill(split_case, "grind_10_entry", 1.0, 110.0)
    strategy.system_v4_grind_entry_before_derisk_enable = True
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  rate = 84.0 if route == "liquidation" else (87.0 if route == "pre_derisk" else 90.0)
  trade.liquidation_price = 80.0 if route == "liquidation" else None
  candles(split_case, rate, signal=route == "ordinary")
  if route == "fallback":
    frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
    frame["AROONU_14"] = 0.0
    strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
  native_step = 80.0 if route == "pre_derisk" else 70.0
  proposal = max(native_step * max(1.0, minimum / 50.0), minimum * 1.5) / trade.leverage
  free = proposal * (1.0 if funded else 0.999)
  wallet = trade.stake_amount - trade.realized_profit + free
  if funded:
    wallet = nextafter(wallet, inf)
  split_bot.config["dry_run_wallet"] = wallet
  split_bot.wallets = Wallets(split_bot.config, split_bot.exchange)
  available = split_bot.wallets.get_available_stake_amount()
  assert (available >= proposal) == funded
  split_bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  split_bot.exchange.get_rates.return_value = (rate, rate)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  before = trade.amount
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(available)
  if expected:
    assert adjustment.spy_return == (pytest.approx(proposal), "grind_10_entry")
    diagnostic = {"fallback": "g10_fb1", "liquidation": "g10_liq1", "ordinary": "g10", "pre_derisk": "g10_pre_derisk"}
    assert strategy._grind_entry_tag == diagnostic[route]
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == "grind_10_entry"
    assert order.amount * rate / trade.leverage == pytest.approx(proposal, abs=1e-6)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before + proposal * trade.leverage / rate, abs=1e-8)
  else:
    assert adjustment.spy_return is None
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
@pytest.mark.parametrize("gate", ["prior_derisk", "rsi3", "rsi15", "aroonu"])
def test_ten_fallback_keeps_five_specific_prior_derisk_and_strict_indicators(split_bot, split_case, mocker, gate):
  strategy, trade = split_case
  add_fill(split_case, "grind_5_entry")
  if gate != "prior_derisk":
    add_fill(split_case, "derisk_level_1", 0.1, side=trade.exit_side)
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  candles(split_case, 90.0, fallback=True)
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame["AROONU_14"] = 50.0 if gate == "aroonu" else 0.0
  if gate == "rsi3":
    frame["RSI_3"] = 10.0
  if gate == "rsi15":
    frame["RSI_3_15m"] = 20.0
  strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
@pytest.mark.parametrize("liquidation", [80.0, 90.0, 100.0])
def test_ten_original_liquidation_expression_is_not_silently_strengthened(split_bot, split_case, mocker, liquidation):
  strategy, trade = split_case
  add_fill(split_case, "grind_5_entry")
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  # The original g5_liq1 expression has no current > liquidation test; retain that exact route.
  trade.liquidation_price = liquidation
  candles(split_case, 84.0)
  split_bot.exchange.get_rates.return_value = (84.0, 84.0)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return == (pytest.approx(70.0 / trade.leverage), "grind_10_entry")
  assert strategy._grind_entry_tag == "g10_liq1"
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == "grind_10_entry"
  assert order.amount * 84.0 == pytest.approx(70.0, abs=1e-6)
  settle(split_bot, trade, order)


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("emergency", [False, True])
def test_native_emergency_three_precedes_ready_lower_and_ordinary_derisk_one_two(
  split_bot, split_case, mocker, emergency, level, lower, lower_stakes
):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  strategy.derisk_enable = True
  strategy.system_v4_derisk_level_3_enable = True
  strategy.system_v4_derisk_level_3_liquidation_enable = emergency
  strategy._bad_trade_controller_derisk_hold = MagicMock(return_value=True)
  for queue in (1, 2):
    setattr(strategy, f"system_v4_derisk_level_{queue}_enable", True)
    setattr(strategy, f"system_v4_derisk_level_{queue}_futures", [-0.01, -0.02])
  trade.liquidation_price = 80.0
  candles(split_case, 84.0, signal=True)
  split_bot.exchange.get_rates.return_value = (84.0, 84.0)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  before = trade.amount
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  if emergency:
    assert adjustment.spy_return == (pytest.approx(-500.0 / trade.leverage), "derisk_level_3")
    assert order.ft_order_tag == "derisk_level_3"
    assert order.amount == pytest.approx(5.0, abs=1e-8)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before - 5.0, abs=1e-8)
  else:
    assert adjustment.spy_return == (pytest.approx(lower_stakes[0] / trade.leverage), f"grind_{lower}_entry")
    assert order.ft_order_tag == f"grind_{lower}_entry"
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before + lower_stakes[0] / 84.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "level,queue,stake",
  [
    (3, 1, 200.0),
    (3, 2, 100.0),
    (3, 4, 50.0),
    (3, 5, 50.0),
    (5, 1, 200.0),
    (5, 2, 100.0),
    (5, 3, 100.0),
    (5, 4, 50.0),
  ],
)
def test_original_parent_decisions_precede_new_lower_orders(split_bot, split_case, mocker, level, queue, stake):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  setattr(strategy, f"system_v4_grind_{queue}_enable", True)
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{queue}_entry"
  assert order.amount * 90.0 == pytest.approx(stake, abs=1e-6)
  settle(split_bot, trade, order)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
def test_public_bot_preserves_complete_nine_six_seven_then_eight_ten_entry_order(split_bot, split_case, mocker):
  strategy, trade = split_case
  trade.orders[-1].ft_order_tag = "seed"
  # Priority isolation only: the larger test cap admits all five parents concurrently.
  strategy.system_v4_max_stake = 3.0
  for parent in range(1, 6):
    setattr(strategy, f"system_v4_grind_{parent}_enable", True)
    add_fill(split_case, f"grind_{parent}_entry")
    add_fill(split_case, f"grind_{parent}_entry")
  candles(split_case, 90.0, signal=True)
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  clock.return_value = NOW
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  for queue, stake in ((9, 70.0), (6, 200.0), (7, 140.0), (8, 140.0), (10, 70.0)):
    split_bot.exchange.create_order.reset_mock()
    before = trade.amount
    split_bot.check_and_call_adjust_trade_position(trade)
    assert adjustment.spy_exception is None
    assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{queue}_entry"
    assert order.amount * 90.0 == pytest.approx(stake, abs=1e-6)
    settle(split_bot, trade, order, when=clock.return_value)
    assert trade.amount == pytest.approx(before + stake / 90.0, abs=1e-8)
    clock.return_value += timedelta(hours=7)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return is None
  split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level,earlier", [(3, 9), (3, 6), (3, 7), (5, 9), (5, 6), (5, 7), (5, 8)])
@pytest.mark.parametrize("reason,entry_rate", [("exit", 80.0), ("derisk", 110.0)])
def test_complete_earlier_lower_reduction_precedes_new_lower_admission(
  split_bot, split_case, mocker, level, earlier, reason, entry_rate
):
  strategy, trade = split_case
  add_fill(split_case, f"grind_{level}_entry")
  entry = add_fill(split_case, f"grind_{earlier}_entry", 1.0, entry_rate)
  candles(split_case, 85.0, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (85.0, 85.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{earlier}_{reason} {entry.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(8.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [5])
@pytest.mark.parametrize("reason,rate", [("exit", 85.0), ("derisk", 50.0)])
def test_interleaved_orphan_eight_and_ten_reload_and_settle_own_inventory_in_order(
  split_bot, split_case, mocker, reason, rate
):
  strategy, trade = split_case
  strategy.system_v4_grind_3_enable = strategy.system_v4_grind_5_enable = False
  strategy.long_grind_entry_v4.return_value = False
  trade.orders[-1].ft_order_tag = "seed"
  first_eight = add_fill(split_case, "grind_8_entry", 0.6, 80.0)
  first_ten = add_fill(split_case, "grind_10_entry", 0.8, 70.0)
  second_eight = add_fill(split_case, "grind_8_entry", 0.4, 70.0)
  second_ten = add_fill(split_case, "grind_10_entry", 0.2, 60.0)
  trade.set_custom_data("grind_10_cluster_max_profit_rate", 0.25)
  trade_id = trade.id
  Trade.session.flush()
  Trade.session.expunge_all()
  trade = Trade.session.get(Trade, trade_id)
  candles((strategy, trade), rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  for queue, first, second in ((8, first_eight, second_eight), (10, first_ten, second_ten)):
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
    if queue == 8:
      assert trade.amount == pytest.approx(8.0, abs=1e-8)
      assert trade.get_custom_data("grind_10_cluster_max_profit_rate") >= 0.25
  assert trade.amount == pytest.approx(7.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (True, 3.0)], indirect=True)
@pytest.mark.parametrize("version", [None, "system_v3", "system_v3_1", "system_v3_2", "system_v4"])
@pytest.mark.parametrize("reason", ["exit", "derisk"])
def test_new_lower_fill_resets_only_own_two_highwaters_for_stored_long_v4(split_case, version, reason, lower):
  strategy, trade = split_case
  trade.set_custom_data("system_version", version)
  for queue in (6, 7, 8, 9, 10):
    trade.set_custom_data(f"grind_{queue}_cluster_max_profit_stake", 12.0)
    trade.set_custom_data(f"grind_{queue}_cluster_max_profit_rate", 0.12)
  order = add_fill(split_case, f"grind_{lower}_{reason} 3", 0.1, side=trade.exit_side)
  strategy.order_filled(trade.pair, trade, order, NOW)
  for queue in (6, 7, 8, 9, 10):
    reset = queue == lower and version == "system_v4" and not trade.is_short
    assert trade.get_custom_data(f"grind_{queue}_cluster_max_profit_stake") == (0.0 if reset else 12.0)
    assert trade.get_custom_data(f"grind_{queue}_cluster_max_profit_rate") == (0.0 if reset else 0.12)


@pytest.mark.parametrize("v4_case", [(True, 3.0)], indirect=True)
def test_public_short_keeps_all_original_three_or_five_steps_and_no_lower_orders(
  split_bot, split_case, mocker, level, lower
):
  strategy, trade = split_case
  strategy.system_v4_max_stake = 3.0
  setattr(strategy, f"system_v4_grind_{lower}_primary_gap", 0.99)
  stakes = (120.0, 140.0, 160.0, 180.0) if level == 3 else (60.0, 70.0, 80.0, 90.0)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  for index, (rate, stake) in enumerate(zip((114.0, 128.0, 144.0, 162.0), stakes, strict=True)):
    clock.return_value = NOW + timedelta(hours=7 * index)
    split_bot.exchange.get_rates.return_value = (rate, rate)
    split_bot.exchange.create_order.reset_mock()
    before = trade.amount
    split_bot.check_and_call_adjust_trade_position(trade)
    assert adjustment.spy_exception is None
    assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), f"grind_{level}_entry")
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{level}_entry"
    assert order.ft_order_side == trade.entry_side
    assert order.amount * rate == pytest.approx(stake, abs=1e-6)
    settle(split_bot, trade, order, when=clock.return_value)
    assert trade.amount == pytest.approx(before + stake / rate, abs=1e-8)
  assert all(o.ft_order_tag != f"grind_{lower}_entry" for o in trade.orders)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize(
  "funding_case,level",
  [
    ((version, parent, "grind"), parent)
    for version in (None, "system_v3", "system_v3_1", "system_v3_2")
    for parent in (3, 5)
  ],
  indirect=["funding_case"],
)
def test_earlier_systems_keep_original_third_three_and_five_allocations(funded_grind_case, level, lower):
  strategy, trade, rate = funded_grind_case
  strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  prefix = "grinding_v2" if trade.get_custom_data("system_version") is None else "system_v3"
  setattr(strategy, f"{prefix}_max_stake", 2.0)
  setattr(strategy, f"system_v4_grind_{lower}_primary_gap", 0.99)
  add_fill((strategy, trade), f"grind_{level}_entry")
  assert split.funding.adjust((strategy, trade, rate), 10000.0) == (pytest.approx(150.0), f"grind_{level}_entry")


def test_legacy_grind_mode_remains_distinct_from_eight_and_ten(legacy_grind_case):
  strategy, trade, _ = legacy_grind_case
  strategy.system_v4_grind_8_primary_gap = 0.99
  strategy.system_v4_grind_10_primary_gap = 0.99
  assert split.legacy.adjust(legacy_grind_case, 1000.0) == (pytest.approx(140.0 / trade.leverage), "gd1")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("length", [0, 1, 2, 3, 4, 5])
def test_public_bot_empty_short_and_scaled_custom_ladders_use_only_original_remaining_steps(
  split_bot, split_case, mocker, length, level, lower
):
  strategy, trade = split_case
  original = [0.03, 0.04, 0.08, 0.11, 0.20][:length]
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_{level}_stakes_{market}", original)
  add_fill(split_case, f"grind_{level}_entry")
  minimum = 40.0 / trade.leverage
  split_bot.exchange.get_min_pair_stake_amount.return_value = minimum
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  clock.return_value = NOW
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  for index, (rate, step) in enumerate(((90.0, 80.0), (81.0, 110.0))):
    candles(split_case, rate)
    split_bot.exchange.get_rates.return_value = (rate, rate)
    split_bot.exchange.create_order.reset_mock()
    before = trade.amount
    split_bot.check_and_call_adjust_trade_position(trade)
    assert adjustment.spy_exception is None
    if length <= index + 2:
      assert adjustment.spy_return is None
      split_bot.exchange.create_order.assert_not_called()
    else:
      proposal = step * 4.0 / 3.0 / trade.leverage
      assert adjustment.spy_return == (pytest.approx(proposal), f"grind_{lower}_entry")
      split_bot.exchange.create_order.assert_called_once()
      order = trade.orders[-1]
      assert order.ft_order_tag == f"grind_{lower}_entry"
      assert order.amount * rate / trade.leverage == pytest.approx(proposal, abs=1e-6)
      settle(split_bot, trade, order, when=clock.return_value)
      assert trade.amount == pytest.approx(before + proposal * trade.leverage / rate, abs=1e-8)
    clock.return_value += timedelta(hours=7)
  candles(split_case, 80.0)
  split_bot.exchange.get_rates.return_value = (80.0, 80.0)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return is None
  split_bot.exchange.create_order.assert_not_called()
  assert getattr(strategy, f"system_v4_grind_{level}_stakes_spot") == original


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "state,expected_queue",
  [
    ("empty", "parent"),
    ("one", "parent"),
    ("two", "lower"),
    ("unfilled-canceled", "parent"),
    ("unfilled-open", None),
    ("closed-then-one", "parent"),
    ("closed-then-two", "lower"),
    ("overfull-3", None),
    ("overfull-4", None),
    ("overfull-5", None),
  ],
)
def test_public_bot_admits_lower_only_with_exactly_two_current_filled_parents(
  split_bot, split_case, mocker, state, expected_queue, level, lower, lower_stakes
):
  strategy, trade = split_case
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
  candles(split_case, 90.0)
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  before = trade.amount
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  if expected_queue is None:
    assert adjustment.spy_return is None
    split_bot.exchange.create_order.assert_not_called()
  else:
    queue = lower if expected_queue == "lower" else level
    parent_steps = (100.0, 120.0) if level == 3 else (50.0, 60.0)
    stake = lower_stakes[0] if expected_queue == "lower" else parent_steps[0 if state == "empty" else 1]
    assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{queue}_entry"
    assert order.amount * 90.0 == pytest.approx(stake, abs=1e-6)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before + stake / 90.0, abs=1e-8)
