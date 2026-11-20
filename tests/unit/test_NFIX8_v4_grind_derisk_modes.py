"""Configured V4 long de-risk selection through native bot and settlement APIs."""

import pytest
from freqtrade.exchange import amount_to_contract_precision

from tests.unit import test_NFIX8_v4_grind_entry_derisk as entry
from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


level = entry.level
v4_case = entry.v4_case
quantity_bot = entry.quantity_bot
entry_derisk_bot = entry.entry_derisk_bot
no_callback_errors = entry.no_callback_errors
LONG_CASES = entry.LONG_CASES
MODE = "system_v4_grind_derisk_mode"


@pytest.fixture
def derisk_config(request):
  # Never inherit the existing regression owner's explicit oldest opt-in.
  # Its shared bot fixture loads this config with the real strategy constructor.
  return getattr(request, "param", {})


def four_entry_queue(trade, level):
  orders = [trade.orders[-1]]
  for amount, price in ((0.5, 256.0), (0.25, 64.0), (0.125, 128.0)):
    funding.fill(trade, trade.entry_side, amount, price, f"grind_{level}_entry")
    orders.append(trade.orders[-1])
  funding.fill(trade, trade.entry_side, 0.125, 128.0, f"grind_{level % 5 + 1}_entry")
  return orders, trade.orders[-1].id


def assert_no_adjustment(bot, trade):
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_not_called()
  assert len(trade.orders) == before


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
def test_default_all_matches_native_four_entry_quantity_and_ids(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  orders, other_id = four_entry_queue(trade, level)
  oldest, second, third, newest = orders
  originals = entry.entry_records(trade)
  assert oldest.order_id != str(oldest.id)
  entry.assert_holdings(bot, trade, "8")

  # Native aggregate: 1 + 0.5 + 0.25 + 0.125, newest-first database IDs.
  # The published oldest-only parent must fail on quantity before tag text.
  quantity.set_rate(bot, trade, 64.0)
  order = entry.request_exit(
    bot, trade, "1.875", f"grind_{level}_derisk {newest.id} {third.id} {second.id} {oldest.id}"
  )
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "8")
  if trade.leverage == 1.0:
    entry.assert_coins(bot.wallets.get_free("ETH"), "6.125")
    entry.assert_coins(bot.wallets.get_used("ETH"), "1.875")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_coins(order.cost, "120")
  entry.assert_holdings(bot, trade, "6.125")
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals
  assert entry.entry_records(trade)[other_id][1] == f"grind_{level % 5 + 1}_entry"
  for rate in (64.0, 128.0):
    quantity.set_rate(bot, trade, rate)
    assert_no_adjustment(bot, trade)
    entry.assert_holdings(bot, trade, "6.125")


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
def test_default_all_matches_native_after_historical_aggregate_exit(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  historical_oldest = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 1.0, 100.0, "grind_1_entry")
  historical_newest = trade.orders[-1].id
  # A normal fully-filled Native ALL tag closes that historical cohort.
  funding.fill(trade, trade.exit_side, 2.0, 128.0, f"grind_1_derisk {historical_newest} {historical_oldest}")
  funding.fill(trade, trade.entry_side, 1.0, 100.0, "grind_1_entry")
  oldest = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 256.0, "grind_1_entry")
  middle = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 64.0, "grind_1_entry")
  newest = trade.orders[-1].id
  originals = entry.entry_records(trade)
  entry.assert_holdings(bot, trade, "8")

  quantity.set_rate(bot, trade, 64.0)
  order = entry.request_exit(bot, trade, "2", f"grind_1_derisk {newest} {middle} {oldest}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_coins(order.cost, "128")
  entry.assert_holdings(bot, trade, "6")
  trade = entry.reload_trade(trade)
  assert_no_adjustment(bot, trade)
  assert entry.entry_records(trade) == originals
  entry.assert_holdings(bot, trade, "6")


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "derisk_config,selected,amount,remainder",
  [
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "all"}}, (3, 2, 1, 0), "1.875", "6.125"),
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "oldest"}}, (0,), "1", "7"),
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}, (2, 1, 0), "1.75", "6.25"),
  ],
  indirect=["derisk_config"],
  ids=["advanced-all", "advanced-oldest", "advanced-keep-latest"],
)
def test_advanced_selection_uses_queue_positions_not_price_sort(
  entry_derisk_bot, v4_case, level, selected, amount, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  orders, _ = four_entry_queue(trade, level)
  newest_id = orders[3].id
  originals = entry.entry_records(trade)
  # Chronological prices 100,256,64,128: list-last is not max-price,
  # and list-first is not min-price. The keeper is the 0.125@128 entry.
  tag = f"grind_{level}_derisk " + " ".join(str(orders[index].id) for index in selected)
  quantity.set_rate(bot, trade, 64.0)
  order = entry.request_exit(bot, trade, amount, tag)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "8")
  if trade.leverage == 1.0:
    entry.assert_coins(bot.wallets.get_free("ETH"), remainder)
    entry.assert_coins(bot.wallets.get_used("ETH"), amount)
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals

  if selected == (2, 1, 0):
    # Four open IDs became one keeper, not a rewritten or partially sold entry.
    # The next same-price callback applies the explicit singleton exception;
    # there is no fresh-cross requirement or permanent immunity for that ID.
    keeper = entry.request_exit(bot, trade, "0.125", f"grind_{level}_derisk {newest_id}")
    entry.settle_exit(bot, trade, keeper, clock)
    entry.assert_holdings(bot, trade, "6.125")
    trade = entry.reload_trade(trade)
    assert_no_adjustment(bot, trade)
    assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "derisk_config", [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}], indirect=True
)
def test_keep_latest_singleton_exits_its_one_native_entry(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1].id
  originals = entry.entry_records(trade)
  quantity.set_rate(bot, trade, 64.0)
  order = entry.request_exit(bot, trade, "1", f"grind_{level}_derisk {oldest}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, "6")
  trade = entry.reload_trade(trade)
  for rate in (64.0, 128.0):
    quantity.set_rate(bot, trade, rate)
    assert_no_adjustment(bot, trade)
    entry.assert_holdings(bot, trade, "6")
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "derisk_config,amount,selected,remainder",
  [
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "all"}}, "6", (3, 2, 1, 0), "6"),
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "oldest"}}, "1", (0,), "11"),
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}, "2", (2, 1, 0), "10"),
  ],
  indirect=["derisk_config"],
  ids=["all", "oldest", "keep-latest"],
)
def test_every_mode_triggers_from_all_four_entries_not_sold_subset_or_leverage(
  entry_derisk_bot, v4_case, amount, selected, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  orders = [trade.orders[-1]]
  for size, price in ((0.5, 512.0), (0.5, 128.0), (4.0, 48.0)):
    funding.fill(trade, trade.entry_side, size, price, "grind_1_entry")
    orders.append(trade.orders[-1])
  originals = entry.entry_records(trade)
  entry.assert_holdings(bot, trade, "12")

  # All four average102; the older three average210. At96 the whole
  # queue is only -5.88%, whereas the sold subset (and 4x PnL) breaches -22%.
  quantity.set_rate(bot, trade, 96.0)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "12")
  assert entry.entry_records(trade) == originals

  quantity.set_rate(bot, trade, 64.0)
  tag = "grind_1_derisk " + " ".join(str(orders[index].id) for index in selected)
  order = entry.request_exit(bot, trade, amount, tag)
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "derisk_config",
  [
    {"nfi_advanced_mode": False, "nfi_parameters": {MODE: "oldest"}},
    {"nfi_parameters": {MODE: "keep_latest"}},
    {"nfi_advanced_mode": False, "nfi_parameters": {MODE: "unsupported"}},
    {"nfi_advanced_mode": False, "nfi_parameters": {MODE: None}},
    {"nfi_advanced_mode": False, "nfi_parameters": {MODE: []}},
    {"nfi_advanced_mode": True, MODE: "oldest"},
  ],
  indirect=True,
  ids=["unsafe-oldest", "unsafe-keep-latest", "unsafe-invalid", "unsafe-null", "unsafe-list", "legacy-top-level"],
)
def test_ignored_mode_configuration_retains_native_all(entry_derisk_bot, v4_case, derisk_config, caplog):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 1.0, 100.0, "grind_1_entry")
  newest = trade.orders[-1].id
  originals = entry.entry_records(trade)
  quantity.set_rate(bot, trade, 64.0)
  order = entry.request_exit(bot, trade, "2", f"grind_1_derisk {newest} {oldest}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, "6")
  assert entry.entry_records(trade) == originals
  if "nfi_parameters" in derisk_config:
    assert any(
      f"Invalid or unsafe parameter: {MODE}." in record.getMessage() for record in caplog.get_records("setup")
    )


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize(
  "derisk_config",
  [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}, MODE: "oldest"}],
  indirect=True,
)
def test_legacy_top_level_does_not_replace_applied_nested_mode(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 100.0, "grind_1_entry")
  middle = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 100.0, "grind_1_entry")
  originals = entry.entry_records(trade)
  quantity.set_rate(bot, trade, 64.0)
  order = entry.request_exit(bot, trade, "1.5", f"grind_1_derisk {middle} {oldest}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, "6.5")
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize(
  "invalid",
  [None, True, 1, [], {}, "", "ALL", "keep_newest"],
  ids=["null", "boolean", "number", "list", "mapping", "empty", "case-alias", "name-alias"],
)
def test_invalid_applied_mode_raises_during_real_construction(v4_case, tmp_path, invalid):
  strategy, _, _ = v4_case
  config = strategy.config | {
    "user_data_dir": tmp_path,
    "nfi_advanced_mode": True,
    "nfi_parameters": {MODE: invalid},
  }
  with pytest.raises(ValueError, match=MODE):
    type(strategy)(config)


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "derisk_config",
  [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}],
  indirect=True,
)
def test_keep_latest_does_not_restrict_normal_group_profit_or_reload_highwater(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  strategy, trade, _ = v4_case
  orders, _ = four_entry_queue(trade, 1)
  oldest, second, third, newest = orders
  originals = entry.entry_records(trade)
  strategy.system_v4_grind_1_use_derisk = False
  quantity.set_rate(bot, trade, 64.0)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "8")
  quantity.set_rate(bot, trade, 256.0)
  order = entry.request_exit(bot, trade, "1.875", f"grind_1_exit {newest.id} {third.id} {second.id} {oldest.id}")
  highwater = trade.get_custom_data("grind_1_cluster_max_profit_rate")
  assert highwater > 0.0
  order_id = order.id
  trade = entry.reload_trade(trade)
  assert trade.get_custom_data("grind_1_cluster_max_profit_rate") == highwater
  order = next(order for order in trade.orders if order.id == order_id)
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_coins(order.cost, "480")
  entry.assert_holdings(bot, trade, "6.125")
  assert trade.get_custom_data("grind_1_cluster_max_profit_rate") == 0.0
  trade = entry.reload_trade(trade)
  assert trade.get_custom_data("grind_1_cluster_max_profit_rate") == 0.0
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "derisk_config,amount,selected,remaining,remainder",
  [
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "all"}}, "2", (2, 1, 0), 1.5, "6"),
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}, "1.5", (1, 0), 1.0, "6.5"),
  ],
  indirect=["derisk_config"],
  ids=["all", "keep-latest"],
)
def test_multi_id_derisk_recovers_actual_cancelled_remainder_before_reconstruction(
  entry_derisk_bot, v4_case, amount, selected, remaining, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  orders = [trade.orders[-1]]
  for size, price in ((0.5, 256.0), (0.5, 64.0)):
    funding.fill(trade, trade.entry_side, size, price, "grind_1_entry")
    orders.append(trade.orders[-1])
  originals = entry.entry_records(trade)
  tag = "grind_1_derisk " + " ".join(str(orders[index].id) for index in selected)
  quantity.set_rate(bot, trade, 64.0)
  first = entry.request_exit(bot, trade, amount, tag)
  first_id = first.id
  keeper_id = orders[2].id
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "8")
  entry.settle_reported_fill(bot, trade, first, clock, 0.5, remaining, "canceled")
  entry.assert_holdings(bot, trade, "7.5")
  trade = entry.reload_trade(trade)
  cancelled = next(order for order in trade.orders if order.id == first_id)
  entry.assert_coins(cancelled.safe_filled, "0.5")
  entry.assert_coins(cancelled.safe_remaining, str(remaining))

  # Raw original average130 does not de-risk at128; the latest actual
  # same-tag safe_remaining still owns recovery, with no per-ID allocation.
  quantity.set_rate(bot, trade, 128.0)
  retry = entry.request_exit(bot, trade, str(remaining), tag)
  entry.settle_exit(bot, trade, retry, clock)
  entry.assert_holdings(bot, trade, remainder)
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals
  if selected == (1, 0):
    keeper = entry.request_exit(bot, trade, "0.5", f"grind_1_exit {keeper_id}")
    entry.settle_exit(bot, trade, keeper, clock)
    entry.assert_holdings(bot, trade, "6")
    trade = entry.reload_trade(trade)
  for rate in (64.0, 128.0):
    quantity.set_rate(bot, trade, rate)
    assert_no_adjustment(bot, trade)
    entry.assert_holdings(bot, trade, "6")
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize(
  "derisk_config,amount,selected,remainder",
  [
    ({}, "2", (2, 1, 0), "6"),
    ({"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}, "1.4921875", (1, 0), "6.5078125"),
  ],
  indirect=["derisk_config"],
  ids=["native-all-fees", "keep-latest-selected-fees"],
)
def test_aggregate_owns_only_selected_entries_net_base_fees(entry_derisk_bot, v4_case, amount, selected, remainder):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1]
  quantity.settle_base_fee(bot, trade, oldest, 0.0078125)
  funding.fill(trade, trade.entry_side, 0.5, 100.0, "grind_1_entry")
  middle = trade.orders[-1]
  funding.fill(trade, trade.entry_side, 0.51171875, 100.0, "grind_1_entry")
  newest = trade.orders[-1]
  quantity.settle_base_fee(bot, trade, newest, 0.00390625)
  orders = oldest, middle, newest
  originals = entry.entry_records(trade)
  entry.assert_coins(oldest.safe_amount_after_fee, "0.9921875")
  entry.assert_coins(newest.safe_amount_after_fee, "0.5078125")
  entry.assert_holdings(bot, trade, "8")
  quantity.set_rate(bot, trade, 64.0)
  tag = "grind_1_derisk " + " ".join(str(orders[index].id) for index in selected)
  order = entry.request_exit(bot, trade, amount, tag)
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize(
  "derisk_config", [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}], indirect=True
)
@pytest.mark.parametrize(
  "v4_case,precision,precision_mode,contract_size,amount,remainder",
  [
    ((False, 1.0), 2, 2, 1.0, "0.37", "6.63"),
    ((False, 4.0), 1.0, 4, 0.25, "0.25", "6.75"),
  ],
  indirect=["v4_case"],
  ids=["spot-decimal-truncation", "futures-whole-quarter-coin-contract"],
)
def test_selected_group_uses_reloaded_native_exchange_precision(
  entry_derisk_bot, v4_case, precision, precision_mode, contract_size, amount, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1]
  oldest.amount = oldest.ft_amount = oldest.filled = 0.25
  oldest.cost = 25.0
  trade.recalc_trade_from_orders()
  funding.fill(trade, trade.entry_side, 0.125, 100.0, "grind_1_entry")
  middle = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.625, 100.0, "grind_1_entry")
  oldest_id = oldest.id
  originals = entry.entry_records(trade)
  trade.amount_precision = precision
  trade.precision_mode = precision_mode
  trade.contract_size = contract_size
  trade = entry.reload_trade(trade)
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, size: amount_to_contract_precision(
    size, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  quantity.set_rate(bot, trade, 64.0)
  entry.assert_holdings(bot, trade, "7")
  order = entry.request_exit(bot, trade, amount, f"grind_1_derisk {middle} {oldest_id}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize(
  "derisk_config", [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}], indirect=True
)
@pytest.mark.parametrize(
  "each,other_rate,expected,remainder",
  [(0.03125, 240.0, None, "8"), (0.0390625, 192.0, None, "8"), (0.046875, 144.0, "0.09375", "8.03125")],
  ids=["below-group-minimum", "exact-group-minimum", "above-group-minimum"],
)
def test_keep_latest_minimum_never_borrows_keeper_and_can_fall_through(
  entry_derisk_bot, v4_case, each, other_rate, expected, remainder
):
  bot, clock = entry_derisk_bot
  strategy, trade, _ = v4_case
  oldest = trade.orders[-1]
  oldest.amount = oldest.ft_amount = oldest.filled = each
  oldest.price = oldest.average = oldest.ft_price = 512.0
  oldest.cost = each * 512.0
  trade.recalc_trade_from_orders()
  funding.fill(trade, trade.entry_side, each, 512.0, "grind_1_entry")
  middle = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 2.0 - 2.0 * each, 128.0, "grind_1_entry")
  # These historical admissions keep the whole-trade basis exactly112.
  funding.fill(trade, trade.entry_side, 0.125, other_rate, "grind_2_entry")
  other = trade.orders[-1].id
  strategy.system_v4_grind_2_use_derisk = True
  originals = entry.entry_records(trade)
  quantity.set_rate(bot, trade, 64.0)
  entry.assert_holdings(bot, trade, "8.125")
  # Selected older entries are worth4/5/6 USDT. A large excluded newest
  # entry must not help the strict >5 test, enlarge the sale, or hide queue2.
  if expected is None:
    order = entry.request_exit(bot, trade, "0.125", f"grind_2_derisk {other}")
  else:
    order = entry.request_exit(bot, trade, expected, f"grind_1_derisk {middle} {oldest.id}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize(
  "derisk_config", [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}], indirect=True
)
def test_keep_latest_preserves_native_quote_reserve_without_inventory_repair(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  previous_exit = trade.orders[1]
  previous_exit.amount = previous_exit.ft_amount = previous_exit.filled = 9.9375
  previous_exit.cost = 993.75
  trade.recalc_trade_from_orders()
  oldest = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 100.0, "grind_1_entry")
  middle = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.03125, 100.0, "grind_1_entry")
  originals = entry.entry_records(trade)
  quantity.set_rate(bot, trade, 64.0)
  entry.assert_holdings(bot, trade, "1.59375")
  # Native 1.55*5 quote reserve is0.12109375 ETH at64. It clips the
  # selected1.5, never adds the keeper or rounds the physical remainder away.
  order = entry.request_exit(bot, trade, "1.47265625", f"grind_1_derisk {middle} {oldest}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, "0.12109375")
  trade = entry.reload_trade(trade)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "0.12109375")
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [2])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize(
  "derisk_config", [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}], indirect=True
)
def test_keep_latest_preserves_funded_entry_priority_with_real_settlement(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  strategy, trade, _ = v4_case
  funding.fill(trade, trade.entry_side, 1.0, 100.0, "grind_2_entry")
  originals = entry.entry_records(trade)
  strategy.long_grind_entry_v4.return_value = True
  bot.exchange.get_max_pair_stake_amount.return_value = 100000.0
  bot.exchange.get_fee.return_value = 0.0
  quantity.set_rate(bot, trade, 64.0)
  # Native rung2 is0.14 of the original1000-USDT entry. Run execute_entry,
  # price validation, Wallets and settlement instead of inspecting a stub.
  del bot.execute_entry
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  assert len(trade.orders) == before + 1
  order = trade.orders[-1]
  assert order.ft_order_side == trade.entry_side
  assert order.ft_order_tag == "grind_2_entry"
  assert order.ft_is_open
  entry.assert_coins(order.amount, "2.1875")
  entry.assert_coins(order.stake_amount, "140")
  entry.assert_holdings(bot, trade, "8")
  entry.settle_reported_fill(bot, trade, order, clock, 2.1875)
  entry.assert_holdings(bot, trade, "10.1875")
  trade = entry.reload_trade(trade)
  assert {key: entry.entry_records(trade)[key] for key in originals} == originals
  assert trade.nr_of_successful_entries == 4


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 4.0)], indirect=True, ids=["futures-long"])
@pytest.mark.parametrize(
  "derisk_config", [{"nfi_advanced_mode": True, "nfi_parameters": {MODE: "keep_latest"}}], indirect=True
)
def test_keep_latest_leaves_forced_derisk_priority_unchanged(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  strategy, trade, _ = v4_case
  funding.fill(trade, trade.entry_side, 1.0, 256.0, "grind_1_entry")
  originals = entry.entry_records(trade)
  strategy.derisk_enable = True
  strategy.system_v4_derisk_level_3_enable = True
  strategy.system_v4_derisk_level_3_liquidation_enable = True
  trade.liquidation_price = 96.0
  quantity.set_rate(bot, trade, 98.0)
  # The queue average178 also breaches -22%; shared liquidation de-risk
  # still wins, using its existing tag and five original-entry coins.
  order = entry.request_exit(bot, trade, "5", "derisk_level_3")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, "3")
  assert entry.entry_records(trade) == originals
