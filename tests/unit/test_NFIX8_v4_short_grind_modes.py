"""Configured V4 short grind exit and de-risk selection through native bot and settlement APIs."""

import pytest

from tests.unit import test_NFIX8_v4_grind_entry_derisk as entry
from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


level = entry.level
v4_case = entry.v4_case
quantity_bot = entry.quantity_bot
entry_derisk_bot = entry.entry_derisk_bot
no_callback_errors = entry.no_callback_errors
SHORT = [(True, 4.0)]
SHORT_LEVERAGES = [(True, 2.0), (True, 4.0)]
EXIT_MODE = "system_v4_grind_exit_mode"
DERISK_MODE = "system_v4_grind_derisk_mode"


def advanced(key, value):
  return {"nfi_advanced_mode": True, "nfi_parameters": {key: value}}


@pytest.fixture
def derisk_config(request):
  # Never inherit the long owner's oldest opt-in; each case loads its own config.
  return getattr(request, "param", {})


def set_short_rate(bot, trade, rate):
  # The short profit-exit signal mirrors the owner's long RSI_3=100 candle.
  quantity.set_rate(bot, trade, rate)
  frame, _ = bot.strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(RSI_3=0.0)
  frame["BBL_20_2.0"] = rate / 2.0
  bot.strategy.dp._set_cached_df(trade.pair, "5m", frame, bot.config["candle_type_def"])


def four_entry_queue(trade, level):
  # Chronological prices 100,64,256,128: the newest entry is neither cheapest nor dearest.
  entry_ids = [trade.orders[-1].id]
  for amount, price in ((0.5, 64.0), (0.25, 256.0), (0.125, 128.0)):
    funding.fill(trade, trade.entry_side, amount, price, f"grind_{level}_entry")
    entry_ids.append(trade.orders[-1].id)
  # Another queue's entry that loses at every tested rate; whole-trade basis stays 102.5.
  funding.fill(trade, trade.entry_side, 0.125, 64.0, f"grind_{level % 5 + 1}_entry")
  return entry_ids, trade.orders[-1].id


def assert_no_adjustment(bot, trade):
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_not_called()
  assert len(trade.orders) == before


def tag_for(level, reason, entry_ids, selected):
  return f"grind_{level}_{reason} " + " ".join(str(entry_ids[index]) for index in selected)


@pytest.mark.parametrize("v4_case", SHORT, indirect=True, ids=["futures-short"])
@pytest.mark.parametrize("derisk_config", [advanced(EXIT_MODE, "latest")], indirect=True, ids=["latest"])
def test_latest_exits_newest_entries_one_at_a_time_from_their_own_short_price(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  entry_ids, other_id = four_entry_queue(trade, level)
  originals = entry.entry_records(trade)
  entry.assert_holdings(bot, trade, "8")

  # 0.125@128 is +7.8% short profit at 118 (a long sign reads -7.8%), above every
  # queue threshold, while the queue average 113.07 is a -4.4% short loss.
  set_short_rate(bot, trade, 118.0)
  first = entry.request_exit(bot, trade, "0.125", tag_for(level, "exit", entry_ids, (3,)))
  # A pending real exit reserves this action without pretending it has bought back.
  assert_no_adjustment(bot, trade)
  entry.settle_exit(bot, trade, first, clock)
  entry.assert_coins(first.cost, "14.75")
  entry.assert_holdings(bot, trade, "7.875")

  # The retired ID does not reappear; the older 0.25@256 entry stays eligible on its own price.
  trade = entry.reload_trade(trade)
  set_short_rate(bot, trade, 118.0)
  second = entry.request_exit(bot, trade, "0.25", tag_for(level, "exit", entry_ids, (2,)))
  entry.settle_exit(bot, trade, second, clock)
  entry.assert_coins(second.cost, "29.5")
  entry.assert_holdings(bot, trade, "7.625")

  # Now 0.5@64 is newest and losing at 90. The +10% oldest 1@100 is not bought back
  # out of order, and the remaining average 88 neither exits nor de-risks.
  trade = entry.reload_trade(trade)
  set_short_rate(bot, trade, 90.0)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "7.625")
  assert entry.entry_records(trade) == originals
  assert entry.entry_records(trade)[other_id][1] == f"grind_{level % 5 + 1}_entry"


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", SHORT, indirect=True, ids=["futures-short"])
@pytest.mark.parametrize(
  "derisk_config",
  [{}, {"nfi_parameters": {EXIT_MODE: "latest"}}],
  indirect=True,
  ids=["default", "unsafe-latest"],
)
def test_default_or_unsafe_latest_keeps_short_aggregate_exit(entry_derisk_bot, v4_case, derisk_config, caplog):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  entry_ids, _ = four_entry_queue(trade, 1)
  originals = entry.entry_records(trade)
  if "nfi_parameters" in derisk_config:
    assert any(
      f"Invalid or unsafe parameter: {EXIT_MODE}." in record.getMessage() for record in caplog.get_records("setup")
    )

  # The newest entry alone is profitable at 118, but the short aggregate is not.
  set_short_rate(bot, trade, 118.0)
  assert_no_adjustment(bot, trade)
  set_short_rate(bot, trade, 100.0)
  order = entry.request_exit(bot, trade, "1.875", tag_for(1, "exit", entry_ids, (3, 2, 1, 0)))
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, "6.125")
  assert entry.entry_records(trade) == originals


OLDEST_STEPS = [((0,), "derisk", "1", "7"), ((1,), "derisk", "0.5", "6.5"), ((3, 2), "exit", "0.375", "6.125")]
KEEP_LATEST_STEPS = [((2, 1, 0), "derisk", "1.75", "6.25"), ((3,), "derisk", "0.125", "6.125")]


@pytest.mark.parametrize("v4_case", SHORT, indirect=True, ids=["futures-short"])
@pytest.mark.parametrize(
  "derisk_config,steps",
  [
    (advanced(DERISK_MODE, "oldest"), OLDEST_STEPS),
    (advanced(DERISK_MODE, "keep_latest"), KEEP_LATEST_STEPS),
  ],
  indirect=["derisk_config"],
  ids=["oldest", "keep-latest"],
)
def test_selected_short_derisk_retires_only_named_ids_across_settlement_and_reload(
  entry_derisk_bot, v4_case, level, steps
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  entry_ids, other_id = four_entry_queue(trade, level)
  originals = entry.entry_records(trade)
  entry.assert_holdings(bot, trade, "8")

  # At 160 the full queue average 113.07 is a 41.5% short loss (a long sign reads
  # a gain). Unselected IDs stay in the queue: oldest de-risks the next oldest
  # from the remaining average 128, then the 213.3-average rest exits in profit;
  # keep_latest's singleton keeper de-risks from its own 25% loss.
  for selected, reason, amount, remainder in steps:
    set_short_rate(bot, trade, 160.0)
    order = entry.request_exit(bot, trade, amount, tag_for(level, reason, entry_ids, selected))
    entry.settle_exit(bot, trade, order, clock)
    entry.assert_holdings(bot, trade, remainder)
    trade = entry.reload_trade(trade)
    assert entry.entry_records(trade) == originals
  for rate in (160.0, 100.0):
    set_short_rate(bot, trade, rate)
    assert_no_adjustment(bot, trade)
    entry.assert_holdings(bot, trade, "6.125")
  assert entry.entry_records(trade)[other_id][1] == f"grind_{level % 5 + 1}_entry"


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", SHORT_LEVERAGES, indirect=True, ids=["short-2x", "short-4x"])
@pytest.mark.parametrize(
  "derisk_config,amount,selected,remainder",
  [
    (advanced(DERISK_MODE, "oldest"), "1", (0,), "11"),
    (advanced(DERISK_MODE, "keep_latest"), "2", (2, 1, 0), "10"),
  ],
  indirect=["derisk_config"],
  ids=["oldest", "keep-latest"],
)
def test_selected_modes_trigger_from_full_queue_average_not_subset_or_leverage(
  entry_derisk_bot, v4_case, amount, selected, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  entry_ids = [trade.orders[-1].id]
  for size, price in ((0.5, 48.0), (0.5, 88.0), (4.0, 150.0)):
    funding.fill(trade, trade.entry_side, size, price, "grind_1_entry")
    entry_ids.append(trade.orders[-1].id)
  originals = entry.entry_records(trade)
  entry.assert_holdings(bot, trade, "12")

  # All four average 128; the older three average 84 and the oldest is 100.
  # At 140 the full queue is only a 9.4% short loss, whereas the selected subset
  # (and a leveraged PnL) breaches 22%.
  set_short_rate(bot, trade, 140.0)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, "12")

  set_short_rate(bot, trade, 160.0)
  order = entry.request_exit(bot, trade, amount, tag_for(1, "derisk", entry_ids, selected))
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", SHORT, indirect=True, ids=["futures-short"])
@pytest.mark.parametrize(
  "derisk_config,amount,selected,remaining,after_retry,follow_up",
  [
    (advanced(DERISK_MODE, "oldest"), "1", (0,), 0.5, "7", (200.0, (1,), "derisk", "0.5", "6.5")),
    (advanced(DERISK_MODE, "keep_latest"), "1.5", (1, 0), 1.0, "6.5", (128.0, (2,), "exit", "0.5", "6")),
  ],
  indirect=["derisk_config"],
  ids=["oldest", "keep-latest"],
)
def test_cancelled_selected_derisk_retries_actual_remainder_after_trigger_loss(
  entry_derisk_bot, v4_case, amount, selected, remaining, after_retry, follow_up
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  entry_ids = [trade.orders[-1].id]
  for size, price in ((0.5, 64.0), (0.5, 256.0)):
    funding.fill(trade, trade.entry_side, size, price, "grind_1_entry")
    entry_ids.append(trade.orders[-1].id)
  originals = entry.entry_records(trade)
  tag = tag_for(1, "derisk", entry_ids, selected)
  set_short_rate(bot, trade, 160.0)
  first = entry.request_exit(bot, trade, amount, tag)
  first_id = first.id
  entry.settle_reported_fill(bot, trade, first, clock, 0.5, remaining, "canceled")
  entry.assert_holdings(bot, trade, "7.5")
  trade = entry.reload_trade(trade)
  cancelled = next(order for order in trade.orders if order.id == first_id)
  entry.assert_coins(cancelled.safe_filled, "0.5")
  entry.assert_coins(cancelled.safe_remaining, str(remaining))

  # At 128 the original average 130 no longer breaches 22%; recovery still owns
  # the callback with the latest actual same-tag remainder, not a reselection.
  set_short_rate(bot, trade, 128.0)
  retry = entry.request_exit(bot, trade, str(remaining), tag)
  entry.settle_exit(bot, trade, retry, clock)
  entry.assert_holdings(bot, trade, after_retry)
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals

  # Unselected IDs survive the partial history: oldest later de-risks 0.5@64 from
  # the remaining 160 average; keep_latest's 0.5@256 keeper exits in short profit.
  rate, next_selected, reason, next_amount, remainder = follow_up
  set_short_rate(bot, trade, rate)
  order = entry.request_exit(bot, trade, next_amount, tag_for(1, reason, entry_ids, next_selected))
  entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  trade = entry.reload_trade(trade)
  set_short_rate(bot, trade, 256.0)
  assert_no_adjustment(bot, trade)
  entry.assert_holdings(bot, trade, remainder)
  assert entry.entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", SHORT, indirect=True, ids=["futures-short"])
@pytest.mark.parametrize(
  "derisk_config,expected,selected,remainder",
  [
    (advanced(DERISK_MODE, "oldest"), "1", (0,), "0.546875"),
    (advanced(DERISK_MODE, "keep_latest"), None, None, "1.546875"),
  ],
  indirect=["derisk_config"],
  ids=["oldest-clear-of-reserve", "keep-latest-subset-blocked"],
)
def test_selected_subset_is_never_clipped_into_the_quote_reserve(
  entry_derisk_bot, v4_case, expected, selected, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  previous_exit = trade.orders[1]
  previous_exit.amount = previous_exit.ft_amount = previous_exit.filled = 9.96875
  previous_exit.cost = 996.875
  trade.recalc_trade_from_orders()
  entry_ids = [trade.orders[-1].id]
  for size in (0.5, 0.015625):
    funding.fill(trade, trade.entry_side, size, 100.0, "grind_1_entry")
    entry_ids.append(trade.orders[-1].id)
  originals = entry.entry_records(trade)
  set_short_rate(bot, trade, 128.0)
  entry.assert_holdings(bot, trade, "1.546875")

  # The 1.5 keep_latest subset would leave 0.046875 coins (6 USDT), below the
  # native 1.55*5 reserve. Clipping it would tag IDs that were not fully bought
  # back, so the subset is blocked; the 1-coin oldest leaves 70 USDT.
  if expected is None:
    assert_no_adjustment(bot, trade)
  else:
    order = entry.request_exit(bot, trade, expected, tag_for(1, "derisk", entry_ids, selected))
    entry.settle_exit(bot, trade, order, clock)
  entry.assert_holdings(bot, trade, remainder)
  trade = entry.reload_trade(trade)
  assert entry.entry_records(trade) == originals
