"""Original V4 long queues de-risk one native entry without rewriting their fills."""

import logging
from datetime import datetime, timedelta
from decimal import Decimal
from itertools import count
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import ExitCheckTuple, ExitType, MarginMode, TradingMode
from freqtrade.exchange import amount_to_contract_precision
from freqtrade.persistence import Trade
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


level = funding.level
v4_case = funding.v4_case
quantity_bot = quantity.quantity_bot
LONG_CASES = [(False, 1.0), (False, 4.0)]


@pytest.fixture(autouse=True)
def no_callback_errors(caplog):
  yield
  errors = [
    record.getMessage()
    for phase in ("setup", "call", "teardown")
    for record in caplog.get_records(phase)
    if record.levelno >= logging.ERROR
  ]
  assert not errors, "\n".join(errors)


@pytest.fixture
def entry_derisk_bot(quantity_bot, v4_case, level, mocker):
  strategy, trade, _ = v4_case
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  # Only admission decisions and exchange/RPC I/O are modeled; adjustment,
  # confirmation, persistence, fees and wallet accounting remain native.
  for name in ("short_grind_entry_v4", "long_grind_entry_v3", "long_buyback_entry_v3", "long_rebuy_entry_v3"):
    setattr(strategy, name, MagicMock(return_value=False))
  for queue in range(1, 6):
    setattr(strategy, f"system_v4_grind_{queue}_use_derisk", queue == level)
    for market in ("spot", "futures"):
      # The funding owner deliberately lowers these settings. Restore the
      # actual queue-average policy instead of inheriting its -10% trigger.
      for field in ("stakes", "thresholds", "derisk", "profit_threshold"):
        name = f"system_v4_grind_{queue}_{field}_{market}"
        setattr(strategy, name, getattr(type(strategy), name))
  trade.funding_fees = trade.funding_fee_running = 0.0
  trade.liquidation_price = None
  quantity_bot.margin_mode = MarginMode.ISOLATED if strategy.is_futures_mode else MarginMode.NONE
  quantity_bot.exchange.get_min_pair_stake_amount.return_value = 5.0 / trade.leverage
  quantity_bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  precision = trade.amount_precision, trade.precision_mode, trade.contract_size
  quantity_bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, *precision
  )
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  clock.return_value = funding.NOW
  create_order = quantity_bot.exchange.create_order.side_effect
  template = create_order(side=trade.exit_side, rate=trade.open_rate, amount=1.0)
  serial = count(1)

  def create(**kwargs):
    # Reuse the owner's CCXT shape without reading its detached Trade closure.
    return {
      **template,
      "id": f"entry-derisk-{next(serial)}",
      "side": kwargs["side"],
      "price": kwargs["rate"],
      "amount": kwargs["amount"],
      "remaining": kwargs["amount"],
      "timestamp": int(clock.return_value.timestamp() * 1000),
    }

  quantity_bot.exchange.create_order.side_effect = create
  return quantity_bot, clock


def assert_coins(actual, expected):
  # Exact decimal equality: even a single native eight-decimal atom matters.
  assert Decimal(str(actual)) == Decimal(expected)


def entry_records(trade):
  return {
    order.id: (
      order.order_id,
      order.ft_order_tag,
      order.amount,
      order.ft_amount,
      order.safe_filled,
      order.safe_price,
      order.cost,
      order.safe_fee_base,
    )
    for order in trade.orders
    if order.ft_order_side == trade.entry_side
  }


def assert_holdings(bot, trade, expected):
  assert_coins(trade.amount, expected)
  assert trade.is_open
  bot.wallets.update()
  if trade.trading_mode == TradingMode.FUTURES:
    assert_coins(bot.wallets.get_all_positions()[trade.pair].position, expected)
  else:
    assert_coins(bot.wallets.get_free("ETH"), expected)


def request_exit(bot, trade, amount, tag):
  order_count = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_not_called()
  assert len(trade.orders) == order_count + 1
  order = trade.orders[-1]
  # Native must first fail on whole-queue quantity, not merely changed tag text.
  assert_coins(order.amount, amount)
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == tag
  assert order.ft_is_open
  assert_coins(order.safe_filled, "0")
  return order


def settle_exit(bot, trade, order, clock):
  clock.return_value += timedelta(minutes=5)
  payload = {
    "id": order.order_id,
    "symbol": trade.pair,
    "type": "limit",
    "side": trade.exit_side,
    "status": "closed",
    "price": order.safe_price,
    "average": order.safe_price,
    "amount": order.amount,
    "filled": order.amount,
    "remaining": 0.0,
    "cost": order.amount * order.safe_price,
    "timestamp": int(order.order_date_utc.timestamp() * 1000),
    "lastTradeTimestamp": int(clock.return_value.timestamp() * 1000),
    "fee": {"cost": 0.0, "currency": "USDT", "rate": 0.0},
  }
  bot.update_trade_state(trade, order.order_id, action_order=payload, send_msg=True)
  assert order.status == "closed"
  assert not order.ft_is_open
  assert_coins(order.safe_filled, str(order.amount))
  assert_coins(order.safe_remaining, "0")


def reload_trade(trade):
  trade_id = trade.id
  system = trade.get_custom_data("system_version")
  Trade.session.commit()
  Trade.session.expunge_all()
  reloaded = Trade.session.get(Trade, trade_id)
  assert reloaded is not trade
  assert reloaded.get_custom_data("system_version") == system
  return reloaded


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
def test_two_derisks_then_remaining_group_profit_survive_settlement_and_reload(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  tag = f"grind_{level}_entry"
  oldest = trade.orders[-1]
  funding.fill(trade, trade.entry_side, 0.5, 256.0, tag)
  second = trade.orders[-1]
  funding.fill(trade, trade.entry_side, 0.25, 64.0, tag)
  third = trade.orders[-1]
  funding.fill(trade, trade.entry_side, 0.125, 128.0, tag)
  fourth = trade.orders[-1]
  other_level = level % 5 + 1
  funding.fill(trade, trade.entry_side, 0.125, 128.0, f"grind_{other_level}_entry")
  other_id = trade.orders[-1].id
  entry_ids = oldest.id, second.id, third.id, fourth.id
  originals = entry_records(trade)
  assert oldest.order_id != str(oldest.id)
  assert_holdings(bot, trade, "8")

  # Chronological prices 100,256,64,128 are not monotonic. The oldest
  # remaining entry is neither the maximum-price fill nor the newest fill.
  quantity.set_rate(bot, trade, 64.0)
  first = request_exit(bot, trade, "1", f"grind_{level}_derisk {entry_ids[0]}")
  assert_coins(trade.amount, "8")
  assert entry_records(trade) == originals
  # A pending real exit reserves this action without pretending it has sold.
  pending_count = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  assert len(trade.orders) == pending_count
  assert_coins(trade.amount, "8")
  settle_exit(bot, trade, first, clock)
  assert_coins(first.cost, "64")
  assert_holdings(bot, trade, "7")

  trade = reload_trade(trade)
  assert entry_records(trade) == originals
  quantity.set_rate(bot, trade, 64.0)
  second_exit = request_exit(bot, trade, "0.5", f"grind_{level}_derisk {entry_ids[1]}")
  assert_coins(trade.amount, "7")
  settle_exit(bot, trade, second_exit, clock)
  assert_coins(second_exit.cost, "32")
  assert_holdings(bot, trade, "6.5")

  trade = reload_trade(trade)
  assert entry_records(trade) == originals
  quantity.set_rate(bot, trade, 128.0)
  profit_exit = request_exit(bot, trade, "0.375", f"grind_{level}_exit {entry_ids[3]} {entry_ids[2]}")
  assert_coins(trade.amount, "6.5")
  settle_exit(bot, trade, profit_exit, clock)
  assert_coins(profit_exit.cost, "48")
  assert_holdings(bot, trade, "6.125")

  trade = reload_trade(trade)
  assert entry_records(trade) == originals
  assert trade.orders[0].safe_filled == 10.0
  assert trade.nr_of_successful_entries == 6
  assert entry_records(trade)[other_id][1] == f"grind_{other_level}_entry"
  # The sold group must not reappear on the next callback; the unrelated
  # 0.125 ETH queue and six original ETH remain, including all original rows.
  order_count = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  assert len(trade.orders) == order_count
  assert_holdings(bot, trade, "6.125")


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
def test_native_queue_average_triggers_oldest_even_when_that_entry_is_profitable(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 512.0, f"grind_{level}_entry")
  funding.fill(trade, trade.entry_side, 0.5, 64.0, f"grind_{level}_entry")
  originals = entry_records(trade)
  assert_holdings(bot, trade, "8")

  # Raw queue average is194: at160 only the512 fill breaches -22%.
  # A per-entry scan would act, but the actual native queue trigger does not.
  quantity.set_rate(bot, trade, 160.0)
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_not_called()
  assert len(trade.orders) == before
  assert_holdings(bot, trade, "8")
  assert entry_records(trade) == originals

  # At128 the queue breaches -22%, although the oldest100 fill is +28%.
  # Selecting the512 fill or requiring individual loss changes native policy.
  quantity.set_rate(bot, trade, 128.0)
  order = request_exit(bot, trade, "1", f"grind_{level}_derisk {oldest_id}")
  settle_exit(bot, trade, order, clock)
  assert_holdings(bot, trade, "7")
  assert entry_records(trade) == originals


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize(
  "oldest_amount,next_amount,expected,remainder",
  [
    (0.03125, 0.96875, None, "8"),
    (0.0390625, 0.9609375, None, "8"),
    (0.046875, 0.953125, "0.046875", "7.953125"),
  ],
  ids=["below-target-minimum", "exact-target-minimum", "above-target-minimum"],
)
def test_failed_oldest_minimum_never_selects_a_newer_entry(
  entry_derisk_bot, v4_case, level, oldest_amount, next_amount, expected, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1]
  # Model fully-filled admissions, not partially-filled exit allocation.
  oldest.amount = oldest.ft_amount = oldest.filled = oldest_amount
  oldest.cost = oldest_amount * 100.0
  trade.recalc_trade_from_orders()
  funding.fill(trade, trade.entry_side, next_amount, 512.0, f"grind_{level}_entry")
  funding.fill(trade, trade.entry_side, 1.0, 64.0, f"grind_{level}_entry")
  originals = entry_records(trade)
  quantity.set_rate(bot, trade, 128.0)
  assert_holdings(bot, trade, "8")

  # The oldest is worth4/5/6 USDT at exit, while the next entry alone is
  # executable. The native strict >5 minimum is applied to the chosen ID.
  if expected is None:
    before = len(trade.orders)
    bot.check_and_call_adjust_trade_position(trade)
    bot.execute_entry.assert_not_called()
    assert len(trade.orders) == before
  else:
    order = request_exit(bot, trade, expected, f"grind_{level}_derisk {oldest.id}")
    settle_exit(bot, trade, order, clock)
  assert_holdings(bot, trade, remainder)
  assert entry_records(trade) == originals


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
def test_selected_entry_owns_only_its_net_base_fee_inventory(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1]
  quantity.settle_base_fee(bot, trade, oldest, 0.0078125)
  funding.fill(trade, trade.entry_side, 1.0078125, 100.0, f"grind_{level}_entry")
  newer_id = trade.orders[-1].id
  originals = entry_records(trade)
  assert_coins(oldest.safe_filled, "1")
  assert_coins(oldest.safe_fee_base, "0.0078125")
  assert_coins(oldest.safe_amount_after_fee, "0.9921875")
  assert_holdings(bot, trade, "8")

  quantity.set_rate(bot, trade, 64.0)
  order = request_exit(bot, trade, "0.9921875", f"grind_{level}_derisk {oldest.id}")
  settle_exit(bot, trade, order, clock)
  assert_holdings(bot, trade, "7.0078125")
  trade = reload_trade(trade)
  assert entry_records(trade) == originals

  quantity.set_rate(bot, trade, 128.0)
  remaining_exit = request_exit(bot, trade, "1.0078125", f"grind_{level}_exit {newer_id}")
  settle_exit(bot, trade, remaining_exit, clock)
  assert_holdings(bot, trade, "6")
  assert entry_records(trade) == originals


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize("reason", ["exit", "derisk"])
def test_fully_filled_native_tag_omits_only_its_named_id(entry_derisk_bot, v4_case, level, reason):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 256.0, f"grind_{level}_entry")
  middle_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 64.0, f"grind_{level}_entry")
  originals = entry_records(trade)
  # Model an existing historical order naming one ID, and fully settle it
  # through the public bot. No multi-ID partial allocation rule is involved.
  quantity.set_rate(bot, trade, 256.0)
  assert bot.execute_trade_exit(
    trade,
    256.0,
    ExitCheckTuple(ExitType.PARTIAL_EXIT, f"grind_{level}_{reason} {middle_id}"),
    sub_trade_amt=0.5,
  )
  historical_exit = trade.orders[-1]
  assert_coins(historical_exit.amount, "0.5")
  settle_exit(bot, trade, historical_exit, clock)
  assert_holdings(bot, trade, "7.5")
  trade = reload_trade(trade)

  # Remaining raw queue is1@100 +0.5@64, average88. At64 it de-risks
  # the still-open oldest ID; a tag-as-history-cutoff loses that inventory.
  quantity.set_rate(bot, trade, 64.0)
  order = request_exit(bot, trade, "1", f"grind_{level}_derisk {oldest_id}")
  settle_exit(bot, trade, order, clock)
  assert_holdings(bot, trade, "6.5")
  assert entry_records(trade) == originals


@pytest.mark.parametrize("v4_case", [(True, 4.0)], indirect=True, ids=["futures-short"])
def test_original_short_route_keeps_aggregate_derisk(entry_derisk_bot, v4_case, level):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 1.0, 100.0, f"grind_{level}_entry")
  newest_id = trade.orders[-1].id
  originals = entry_records(trade)
  quantity.set_rate(bot, trade, 128.0)
  assert_holdings(bot, trade, "8")

  order = request_exit(bot, trade, "2", f"grind_{level}_derisk {newest_id} {oldest_id}")
  settle_exit(bot, trade, order, clock)
  assert_holdings(bot, trade, "6")
  assert entry_records(trade) == originals


@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize("system", ["system_v3", "system_v3_1", "system_v3_2"])
def test_other_stored_systems_keep_aggregate_derisk(entry_derisk_bot, v4_case, level, system):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  trade.set_custom_data("system_version", system)
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 1.0, 100.0, f"grind_{level}_entry")
  newest_id = trade.orders[-1].id
  originals = entry_records(trade)
  quantity.set_rate(bot, trade, 64.0)
  assert_holdings(bot, trade, "8")

  order = request_exit(bot, trade, "2", f"grind_{level}_derisk {newest_id} {oldest_id}")
  settle_exit(bot, trade, order, clock)
  assert_holdings(bot, trade, "6")
  assert entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
@pytest.mark.parametrize("enter_tag", ["120", "121"])
def test_legacy_modes_keep_native_aggregate_profit_exit(entry_derisk_bot, v4_case, enter_tag):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  trade.enter_tag = enter_tag
  trade.orders[1].ft_order_tag = "gm0"
  oldest = trade.orders[-1]
  oldest.ft_order_tag = "gd1"
  funding.fill(trade, trade.entry_side, 1.0, 100.0, "gd1")
  newest_id = trade.orders[-1].id
  originals = entry_records(trade)
  quantity.set_rate(bot, trade, 128.0)
  assert_holdings(bot, trade, "8")

  order = request_exit(bot, trade, "2", f"gd1 {newest_id} {oldest.id}")
  settle_exit(bot, trade, order, clock)
  assert_holdings(bot, trade, "6")
  assert entry_records(trade) == originals


def settle_reported_fill(bot, trade, order, clock, filled, remaining=0.0, status="closed"):
  clock.return_value += timedelta(minutes=5)
  # Reuse the owner's exchange response shape, not a second Order/Trade ledger.
  payload = bot.exchange.create_order.side_effect(side=order.ft_order_side, rate=order.safe_price, amount=order.amount)
  payload.update(
    id=order.order_id,
    status=status,
    average=order.safe_price,
    filled=filled,
    remaining=remaining,
    cost=filled * order.safe_price,
    lastTradeTimestamp=int(clock.return_value.timestamp() * 1000),
    fee={"cost": 0.0, "currency": "USDT", "rate": 0.0},
  )
  bot.update_trade_state(trade, order.order_id, action_order=payload, send_msg=True)
  assert order.status == status
  assert not order.ft_is_open
  assert_coins(order.safe_filled, str(filled))
  assert_coins(order.safe_remaining, str(remaining))


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
def test_cancelled_selected_exit_retries_physical_remainder_before_trigger_recheck(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 256.0, "grind_1_entry")
  next_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 64.0, "grind_1_entry")
  originals = entry_records(trade)
  tag = f"grind_1_derisk {oldest_id}"
  quantity.set_rate(bot, trade, 64.0)
  first = request_exit(bot, trade, "1", tag)
  first_id = first.id
  settle_reported_fill(bot, trade, first, clock, 0.4, 0.6, "canceled")
  assert_holdings(bot, trade, "7.6")
  trade = reload_trade(trade)
  cancelled = next(order for order in trade.orders if order.id == first_id)
  assert_coins(cancelled.safe_filled, "0.4")
  assert_coins(cancelled.safe_remaining, "0.6")

  # At128 the original queue average130 no longer meets -22%. Recovery
  # still owns the callback and retains the complete original native tag.
  quantity.set_rate(bot, trade, 128.0)
  retry = request_exit(bot, trade, "0.6", tag)
  assert_coins(trade.amount, "7.6")
  settle_exit(bot, trade, retry, clock)
  assert_holdings(bot, trade, "7")
  trade = reload_trade(trade)
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  assert len(trade.orders) == before
  assert_holdings(bot, trade, "7")

  quantity.set_rate(bot, trade, 64.0)
  next_exit = request_exit(bot, trade, "0.5", f"grind_1_derisk {next_id}")
  settle_exit(bot, trade, next_exit, clock)
  assert_holdings(bot, trade, "6.5")
  assert entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", LONG_CASES, indirect=True, ids=["spot", "futures-long"])
def test_partial_multi_id_profit_exit_recovers_complete_tag_without_reappearing_entries(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.5, 100.0, "grind_1_entry")
  newest_id = trade.orders[-1].id
  originals = entry_records(trade)
  tag = f"grind_1_exit {newest_id} {oldest_id}"
  quantity.set_rate(bot, trade, 128.0)
  first = request_exit(bot, trade, "1.5", tag)
  settle_reported_fill(bot, trade, first, clock, 0.5, 1.0, "canceled")
  assert_holdings(bot, trade, "7")
  trade = reload_trade(trade)

  # The now-losing64 price must not suppress recovery of the actual1 ETH,
  # or cause an allocation/rewrite of the two original admission records.
  quantity.set_rate(bot, trade, 64.0)
  retry = request_exit(bot, trade, "1", tag)
  settle_exit(bot, trade, retry, clock)
  assert_holdings(bot, trade, "6")
  trade = reload_trade(trade)
  for rate in (64.0, 128.0):
    quantity.set_rate(bot, trade, rate)
    before = len(trade.orders)
    bot.check_and_call_adjust_trade_position(trade)
    assert len(trade.orders) == before
    assert_holdings(bot, trade, "6")
  assert entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
def test_unexecutable_recovery_and_blocked_last_target_preserve_inventory_and_other_queue(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  strategy, trade, _ = v4_case
  oldest = trade.orders[-1]
  # Fully-filled modeled admissions give an exact147.5 trade basis.
  oldest.price = oldest.average = oldest.ft_price = 128.0
  oldest.cost = 128.0
  trade.recalc_trade_from_orders()
  funding.fill(trade, trade.entry_side, 0.03125, 128.0, "grind_1_entry")
  blocked_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 0.84375, 512.0, "grind_1_entry")
  funding.fill(trade, trade.entry_side, 0.125, 128.0, "grind_2_entry")
  other_id = trade.orders[-1].id
  strategy.system_v4_grind_2_use_derisk = True
  originals = entry_records(trade)
  quantity.set_rate(bot, trade, 64.0)
  assert_holdings(bot, trade, "8")
  first = request_exit(bot, trade, "1", f"grind_1_derisk {oldest.id}")
  first_id = first.id
  settle_reported_fill(bot, trade, first, clock, 0.96875, 0.03125, "canceled")
  assert_holdings(bot, trade, "7.03125")
  trade = reload_trade(trade)

  # Both the real recovery remainder and the next list-last target are
  # worth2 USDT, below5. The0.84375 newer same-queue fill is executable,
  # but cannot replace the blocked target. Another queue remains reachable.
  other_exit = request_exit(bot, trade, "0.125", f"grind_2_derisk {other_id}")
  settle_exit(bot, trade, other_exit, clock)
  assert_holdings(bot, trade, "6.90625")
  trade = reload_trade(trade)
  cancelled = next(order for order in trade.orders if order.id == first_id)
  assert cancelled.status == "canceled"
  assert_coins(cancelled.safe_filled, "0.96875")
  assert_coins(cancelled.safe_remaining, "0.03125")
  assert entry_records(trade) == originals
  assert_coins(next(order for order in trade.orders if order.id == blocked_id).safe_filled, "0.03125")
  # 6 original +0.875 still-open queue entries +0.03125 unsold physical
  # recovery coins. No FIFO/pro-rata attribution or synthetic balance repair.
  assert_holdings(bot, trade, "6.90625")


@pytest.mark.parametrize("level", [2])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
def test_funded_add_after_id_retirement_uses_real_entry_and_wallet_settlement(entry_derisk_bot, v4_case):
  bot, clock = entry_derisk_bot
  strategy, trade, _ = v4_case
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 1.0, 100.0, "grind_2_entry")
  originals = entry_records(trade)
  # Reuse funding_engine's real-Wallets pattern, with fixed initial capital:
  # 56 free before the64-USDT exit,120 afterwards. Never alter balances.
  bot.config["dry_run_wallet"] = 856.0
  bot.wallets = Wallets(bot.config, bot.exchange)
  assert_coins(bot.wallets.get_available_stake_amount(), "56")
  quantity.set_rate(bot, trade, 64.0)
  first = request_exit(bot, trade, "1", f"grind_2_derisk {oldest_id}")
  settle_exit(bot, trade, first, clock)
  assert_holdings(bot, trade, "7")
  assert_coins(bot.wallets.get_available_stake_amount(), "120")
  trade = reload_trade(trade)

  clock.return_value += timedelta(hours=7)
  strategy.long_grind_entry_v4.return_value = True
  bot.exchange.get_max_pair_stake_amount.return_value = 100000.0
  bot.exchange.get_fee.return_value = 0.0
  # Remove only the fixture's admission execution stub. Class lookup now runs
  # the real FreqtradeBot.execute_entry and native price/stake validation.
  del bot.execute_entry
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  assert len(trade.orders) == before + 1
  entry = trade.orders[-1]
  assert entry.ft_order_side == trade.entry_side
  assert entry.ft_order_tag == "grind_2_entry"
  # One remaining queue ID uses native second rung0.12, not first0.10:
  # 120 USDT /64 =1.875 ETH. It also takes priority over another de-risk.
  assert_coins(entry.amount, "1.875")
  assert_coins(entry.stake_amount, "120")
  assert entry.ft_is_open
  assert_coins(entry.safe_filled, "0")
  assert_coins(trade.amount, "7")
  settle_reported_fill(bot, trade, entry, clock, 1.875)
  assert_holdings(bot, trade, "8.875")
  assert_coins(trade.stake_amount, "820")
  assert_coins(bot.wallets.get_available_stake_amount(), "0")
  trade = reload_trade(trade)
  assert_holdings(bot, trade, "8.875")
  assert trade.nr_of_successful_entries == 4
  assert {key: entry_records(trade)[key] for key in originals} == originals
  assert trade.orders[-1].ft_order_tag == "grind_2_entry"


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize(
  "v4_case,precision,mode,contract_size,selected,newer,expected,remainder",
  [
    ((False, 1.0), 8, 2, 1.0, 0.3, 0.7, "0.3", "6.7"),
    ((False, 3.0), 8, 2, 1.0, 0.3, 0.7, "0.3", "6.7"),
    ((False, 1.0), 2, 2, 1.0, 0.375, 0.625, "0.37", "6.63"),
    ((False, 4.0), 1.0, 4, 0.25, 0.375, 0.625, "0.25", "6.75"),
  ],
  indirect=["v4_case"],
  ids=["nonbinary-eight-decimal", "nonbinary-futures-three", "decimal-half-quantum", "whole-quarter-coin-contract"],
)
def test_selected_quantity_uses_reloaded_native_precision_without_rounding_up(
  entry_derisk_bot, v4_case, precision, mode, contract_size, selected, newer, expected, remainder
):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest = trade.orders[-1]
  oldest.amount = oldest.ft_amount = oldest.filled = selected
  oldest.cost = selected * 100.0
  trade.recalc_trade_from_orders()
  funding.fill(trade, trade.entry_side, newer, 100.0, "grind_1_entry")
  oldest_id = oldest.id
  originals = entry_records(trade)
  trade.amount_precision = precision
  trade.precision_mode = mode
  trade.contract_size = contract_size
  trade = reload_trade(trade)
  # Unlike the unchanged core fixture's captured tuple, this intentionally
  # metadata-changing scenario must quantize from the current persisted Trade.
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  quantity.set_rate(bot, trade, 64.0)
  assert_holdings(bot, trade, "7")
  order = request_exit(bot, trade, expected, f"grind_1_derisk {oldest_id}")
  settle_exit(bot, trade, order, clock)
  # Native truncation can leave physical dust even with a fully-filled order.
  # Do not round up, mutate the entry, or pretend its entire gross lot sold.
  assert_holdings(bot, trade, remainder)
  assert entry_records(trade) == originals


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True, ids=["spot"])
@pytest.mark.parametrize("suffix_kind", ["unicode", "zero", "leading-zero"])
def test_malformed_historical_exit_keeps_native_unattributed_boundary(entry_derisk_bot, v4_case, suffix_kind):
  bot, clock = entry_derisk_bot
  _, trade, _ = v4_case
  oldest_id = trade.orders[-1].id
  funding.fill(trade, trade.entry_side, 1.0, 100.0, "grind_1_entry")
  originals = entry_records(trade)
  if suffix_kind == "unicode":
    suffix = str(oldest_id).translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
  elif suffix_kind == "zero":
    suffix = "0"
  else:
    suffix = f"0{oldest_id}"
  quantity.set_rate(bot, trade, 128.0)
  # An already-settled unattributed historical exit sold the whole2 ETH
  # queue. Invalid ID spelling must retain Native's old history boundary.
  assert bot.execute_trade_exit(
    trade,
    128.0,
    ExitCheckTuple(ExitType.PARTIAL_EXIT, f"grind_1_exit {suffix}"),
    sub_trade_amt=2.0,
  )
  historical_exit = trade.orders[-1]
  assert_coins(historical_exit.amount, "2")
  settle_exit(bot, trade, historical_exit, clock)
  assert_holdings(bot, trade, "6")
  trade = reload_trade(trade)

  quantity.set_rate(bot, trade, 64.0)
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_not_called()
  assert len(trade.orders) == before
  assert_holdings(bot, trade, "6")
  assert entry_records(trade) == originals
