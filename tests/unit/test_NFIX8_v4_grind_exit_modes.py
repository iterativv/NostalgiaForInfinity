"""Configured V4 long grind profit-exit selection through native bot and settlement APIs."""

import pytest

from tests.unit import test_NFIX8_v4_grind_entry_derisk as entry
from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


level = entry.level
v4_case = entry.v4_case
quantity_bot = entry.quantity_bot
entry_derisk_bot = entry.entry_derisk_bot
no_callback_errors = entry.no_callback_errors
LONG_CASES = entry.LONG_CASES
MODE = "system_v4_grind_exit_mode"
LATEST = {"nfi_advanced_mode": True, "nfi_parameters": {MODE: "latest"}}


@pytest.fixture
def derisk_config(request):
  # Keep the native de-risk selection; only the exit mode under test is configured.
  return getattr(request, "param", {})


def four_entry_queue(trade, level):
  # Chronological prices 100,256,64,128: the newest entry is not the cheapest one.
  orders = [trade.orders[-1]]
  for amount, price in ((0.5, 256.0), (0.25, 64.0), (0.125, 128.0)):
    funding.fill(trade, trade.entry_side, amount, price, f"grind_{level}_entry")
    orders.append(trade.orders[-1])
  # Another queue's entry that stays below its profit threshold at every tested rate.
  funding.fill(trade, trade.entry_side, 0.125, 256.0, f"grind_{level % 5 + 1}_entry")
  return orders, trade.orders[-1].id


def assert_no_adjustment(bot, trade):
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_not_called()
  assert len(trade.orders) == before


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "derisk_config",
  [{}, {"nfi_advanced_mode": True, "nfi_parameters": {MODE: "all"}}, {"nfi_parameters": {MODE: "latest"}}],
  indirect=True,
  ids=["default", "advanced-all", "unsafe-latest"],
)
def test_all_exits_whole_queue_only_from_queue_average(entry_derisk_bot, v4_case, level, derisk_config, caplog):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  orders, other_id = four_entry_queue(trade, level)
  oldest, second, third, newest = orders
  originals = entry.entry_records(trade)
  entry.assert_holdings(bot, trade, "8")
  if derisk_config.get("nfi_advanced_mode") is not True and "nfi_parameters" in derisk_config:
    assert any(
      f"Invalid or unsafe parameter: {MODE}." in record.getMessage() for record in caplog.get_records("setup")
    )

  # Queue average 260 / 1.875 = 138.67: +0.96% at 140, although the newest entry is +9.4%.
  quantity.set_rate(bot, trade, 140.0)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "8")

  quantity.set_rate(bot, trade, 160.0)
  order = entry.request_exit(bot, trade, "1.875", f"grind_{level}_exit {newest.id} {third.id} {second.id} {oldest.id}")
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, "6.125")
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals
  assert entry.entry_records(trade)[other_id][1] == f"grind_{level % 5 + 1}_entry"


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize("derisk_config", [LATEST], indirect=True, ids=["latest"])
def test_latest_exits_newest_entries_one_at_a_time_from_their_own_price(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  orders, other_id = four_entry_queue(trade, level)
  third_id, newest_id = orders[2].id, orders[3].id
  originals = entry.entry_records(trade)
  entry.assert_holdings(bot, trade, "8")

  # 0.125 @ 128 is +9.4% at 140 while the queue average is below its threshold.
  quantity.set_rate(bot, trade, 140.0)
  first = entry.request_exit(bot, trade, "0.125", f"grind_{level}_exit {newest_id}")
  # A pending real exit reserves this action without pretending it has sold.
  assert_no_adjustment(bot, trade)
  entry.settle_exit(bot, trade, first, clock)
  entry.assert_coins(first.cost, "17.5")
  entry.assert_holdings(bot, trade, "7.875")

  # The retired entry does not reappear; the next newest entry is checked on its own price.
  trade = entry.reload_trade(trade)
  quantity.set_rate(bot, trade, 140.0)
  next_exit = entry.request_exit(bot, trade, "0.25", f"grind_{level}_exit {third_id}")
  entry.settle_exit(bot, trade, next_exit, clock)
  entry.assert_coins(next_exit.cost, "35")
  entry.assert_holdings(bot, trade, "7.625")

  # Now 0.5 @ 256 is newest and losing. The profitable oldest 1 @ 100 is not sold out of order.
  trade = entry.reload_trade(trade)
  quantity.set_rate(bot, trade, 140.0)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "7.625")
  assert entry.entry_records(trade) == originals
  assert entry.entry_records(trade)[other_id][1] == f"grind_{level % 5 + 1}_entry"


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize("derisk_config", [LATEST], indirect=True, ids=["latest"])
def test_latest_sells_only_the_selected_entry_net_base_fee(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1]
  quantity.settle_base_fee(bot, trade, oldest, 0.0078125)
  funding.fill(trade, trade.entry_side, 0.51171875, 64.0, "grind_1_entry")
  newest = trade.orders[-1]
  quantity.settle_base_fee(bot, trade, newest, 0.00390625)
  originals = entry.entry_records(trade)
  entry.assert_coins(newest.safe_amount_after_fee, "0.5078125")

  # The newest entry is +12.5% at 72; the queue average is still about -18%.
  quantity.set_rate(bot, trade, 72.0)
  order = entry.request_exit(bot, trade, "0.5078125", f"grind_1_exit {newest.id}")
  entry.settle_exit(bot, trade, order, clock)
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals
  entry.assert_coins(trade.amount, "6.9921875")


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize(
  "invalid",
  [None, True, 1, [], "", "ALL", "oldest", "newest"],
  ids=["null", "boolean", "number", "list", "empty", "case-alias", "derisk-value", "name-alias"],
)
def test_invalid_applied_exit_mode_raises_during_real_construction(v4_case, tmp_path, invalid):
  strategy, _, _ = v4_case
  config = strategy.config | {
    "user_data_dir": tmp_path,
    "nfi_advanced_mode": True,
    "nfi_parameters": {MODE: invalid},
  }
  with pytest.raises(ValueError, match=MODE):
    type(strategy)(config)
