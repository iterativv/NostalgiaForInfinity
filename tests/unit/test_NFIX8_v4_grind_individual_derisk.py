"""Original long V4 queues de-risk eligible lots and profit-exit remaining inventory."""

from unittest.mock import MagicMock

import pytest
from freqtrade.enums import MarginMode
from freqtrade.exchange import amount_to_contract_precision
from freqtrade.persistence import Trade
from freqtrade.util import FtPrecise
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_legacy_grind_funding as legacy_funding
from tests.unit import test_NFIX8_legacy_grind_quantity as legacy_quantity
from tests.unit import test_NFIX8_liquidation_rescue as rescue
from tests.unit import test_NFIX8_partial_exit_emergency as emergency
from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_funding_engine as funding_engine
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


level = funding.level
v4_case = funding.v4_case
quantity_bot = quantity.quantity_bot
funding_case = funding_engine.funding_case
funded_grind_case = funding_engine.funded_grind_case
legacy_grind_case = legacy_funding.legacy_grind_case
legacy_quantity_bot = legacy_quantity.quantity_bot
rescue_case = emergency.rescue_case
emergency_bot = emergency.emergency_bot


@pytest.fixture(autouse=True)
def no_swallowed_callback_errors(caplog):
  yield
  assert not [
    record.getMessage()
    for when in ("setup", "call", "teardown")
    for record in caplog.get_records(when)
    if record.levelno >= 40
  ]


def observe_bot(strategy, trade, bot, mocker):
  bot.exchange.get_pair_quote_currency.return_value = "USDT"
  bot.margin_mode = MarginMode.ISOLATED if trade.leverage > 1 else MarginMode.NONE
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  filled = mocker.spy(strategy, "order_filled")
  return strategy, trade, bot, adjustment, filled


@pytest.fixture
def individual_case(v4_case, quantity_bot, level, mocker):
  strategy, trade, _ = v4_case
  strategy.short_grind_entry_v4 = MagicMock(return_value=False)
  for queue in range(1, 6):
    setattr(strategy, f"system_v4_grind_{queue}_use_derisk", queue == level)
  for market in ("spot", "futures"):
    setting = f"system_v4_grind_{level}_derisk_{market}"
    setattr(strategy, setting, getattr(type(strategy), setting))
  quantity_bot.exchange.get_min_pair_stake_amount.return_value = 5.0 / trade.leverage
  return observe_bot(strategy, trade, quantity_bot, mocker)


def add_lots(trade, level, lots):
  orders = []
  for amount, price in lots:
    funding.fill(trade, trade.entry_side, amount, price, f"grind_{level}_entry")
    orders.append(trade.orders[-1])
  return orders


def entry_snapshot(trade):
  return [
    (order.id, order.amount, order.ft_amount, order.filled, order.remaining, order.cost, order.safe_fee_base)
    for order in trade.orders
    if order.ft_order_side == trade.entry_side
  ]


def drive(case, rate, trade=None):
  _, initial_trade, bot, adjustment, filled = case
  trade = initial_trade if trade is None else trade
  quantity.set_rate(bot, trade, rate)
  order_count = len(trade.orders)
  create_count = bot.exchange.create_order.call_count
  balances = trade.amount, trade.stake_amount, trade.open_rate
  entries = entry_snapshot(trade)

  bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  assert filled.spy_exception is None
  assert (trade.amount, trade.stake_amount, trade.open_rate) == balances
  assert entry_snapshot(trade) == entries
  if len(trade.orders) == order_count:
    assert bot.exchange.create_order.call_count == create_count
    return None
  assert len(trade.orders) == order_count + 1
  assert bot.exchange.create_order.call_count == create_count + 1
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_is_open
  assert bot.exchange.create_order.call_args.kwargs["amount"] == order.amount
  assert bot.exchange.create_order.call_args.kwargs["reduceOnly"] == (trade.leverage > 1)
  return order


def exit_order(case, rate, trade=None):
  order = drive(case, rate, trade)
  assert order is not None
  case[2].execute_entry.assert_not_called()
  return order


def settle(case, order, rate, *, amount=None, status="closed", trade=None):
  _, initial_trade, bot, _, filled = case
  trade = initial_trade if trade is None else trade
  amount = order.amount if amount is None else amount
  callbacks = filled.call_count
  entries = entry_snapshot(trade)
  payload = {
    "id": order.order_id,
    "symbol": trade.pair,
    "type": "limit",
    "side": trade.exit_side,
    "status": status,
    "price": rate,
    "average": rate,
    "amount": order.amount,
    "filled": amount,
    "remaining": float(FtPrecise(order.amount) - FtPrecise(amount)),
    "cost": amount * rate,
    "timestamp": int(funding.NOW.timestamp() * 1000),
    "fee": {"cost": 0.0, "currency": "USDT", "rate": 0.0},
  }

  bot.update_trade_state(trade, order.order_id, action_order=payload, send_msg=False)

  assert filled.call_count > callbacks
  assert filled.spy_exception is None
  assert order.ft_is_open is False
  assert order.safe_filled == pytest.approx(amount, abs=1e-8)
  assert entry_snapshot(trade) == entries


def reload_trade(trade):
  trade_id = trade.id
  Trade.session.flush()
  Trade.session.expunge_all()
  reloaded = Trade.session.get(Trade, trade_id)
  assert reloaded is not None
  return reloaded


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True, ids=["spot", "long-futures"])
def test_individual_derisk_selects_first_eligible_remaining_entry(individual_case, level):
  _, trade, bot, _, _ = individual_case
  oldest = trade.orders[-1]
  highest, newest = add_lots(trade, level, ((2.0, 140.0), (3.0, 120.0)))
  other_queue = level % 5 + 1
  untouched = add_lots(trade, other_queue, ((0.5, 100.0),))[0]
  original_entries = entry_snapshot(trade)
  identities = [order.id for order in trade.orders]

  first = exit_order(individual_case, 60.0)

  assert first.amount == pytest.approx(1.0, abs=1e-8)
  assert first.ft_order_tag == f"grind_{level}_derisk_entry {oldest.id}"
  assert trade.amount == pytest.approx(12.5, abs=1e-8)
  assert drive(individual_case, 60.0) is None
  settle(individual_case, first, 60.0)
  assert trade.amount == pytest.approx(11.5, abs=1e-8)
  reloaded = reload_trade(trade)
  assert [order.id for order in reloaded.orders[: len(identities)]] == identities
  assert entry_snapshot(reloaded) == original_entries
  assert Trade.session.get(type(untouched), untouched.id).safe_filled == pytest.approx(0.5)

  second = exit_order(individual_case, 60.0, reloaded)

  assert second.order_id != first.order_id
  assert second.ft_order_tag == f"grind_{level}_derisk_entry {highest.id}"
  assert second.amount == pytest.approx(2.0, abs=1e-8)
  settle(individual_case, second, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(9.5, abs=1e-8)
  third = exit_order(individual_case, 60.0, reloaded)
  assert third.ft_order_tag == f"grind_{level}_derisk_entry {newest.id}"
  assert third.amount == pytest.approx(3.0, abs=1e-8)
  settle(individual_case, third, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(6.5, abs=1e-8)
  assert entry_snapshot(reloaded) == original_entries
  assert drive(individual_case, 60.0, reloaded) is None
  assert bot.exchange.create_order.call_count == 3


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_own_entry_loss_skips_unqualified_newest_and_oldest_without_queue_average_gate(individual_case, level):
  _, trade, _, _, _ = individual_case
  oldest = trade.orders[-1]
  eligible, newest = add_lots(trade, level, ((1.0, 200.0), (10.0, 80.0)))
  average = (oldest.cost + eligible.cost + newest.cost) / 12.0
  assert (85.0 - average) / average > -0.22
  assert (85.0 - oldest.safe_price) / oldest.safe_price > -0.22
  assert (85.0 - newest.safe_price) / newest.safe_price > -0.22

  order = exit_order(individual_case, 85.0)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {eligible.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(individual_case, order, 85.0)
  assert trade.amount == pytest.approx(17.0, abs=1e-8)
  assert drive(individual_case, 80.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (False, 5.0)], indirect=True)
def test_own_raw_loss_boundary_is_strict_and_leverage_independent(individual_case, level):
  _, trade, bot, _, _ = individual_case
  entry = trade.orders[-1]
  before = trade.amount

  assert drive(individual_case, 78.000001) is None
  assert drive(individual_case, 78.0) is None
  assert trade.amount == before
  order = exit_order(individual_case, 77.999999)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {entry.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  assert bot.exchange.create_order.call_count == 1
  settle(individual_case, order, 77.999999)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_selection_uses_actual_average_not_limit_price(individual_case, level):
  _, trade, _, _, _ = individual_case
  eligible = trade.orders[-1]
  unqualified = add_lots(trade, level, ((2.0, 80.0),))[0]
  eligible.price = eligible.ft_price = 1.0
  unqualified.price = unqualified.ft_price = 1000.0
  Trade.session.flush()
  assert eligible.safe_price == 100.0
  assert unqualified.safe_price == 80.0

  order = exit_order(individual_case, 70.0)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {eligible.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(individual_case, order, 70.0)
  assert trade.amount == pytest.approx(8.0, abs=1e-8)
  assert drive(individual_case, 70.0) is None


@pytest.mark.parametrize(
  "v4_case,fee",
  [((False, 1.0), 0.0), ((False, 1.0), 0.003), ((False, 3.0), 0.0)],
  indirect=["v4_case"],
  ids=["spot", "spot-base-fee", "long-futures"],
)
def test_partial_cancel_retries_exact_net_entry_after_reload_and_resets_only_own_highwater(
  individual_case, level, fee
):
  _, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  middle, _ = add_lots(trade, level, ((2.0, 140.0), (3.0, 120.0)))
  quantity.settle_base_fee(bot, trade, selected, fee)
  for queue in range(1, 6):
    trade.set_custom_data(f"grind_{queue}_cluster_max_profit_stake", 1000.0 + queue)
    trade.set_custom_data(f"grind_{queue}_cluster_max_profit_rate", 10.0 + queue)
  entries = entry_snapshot(trade)
  first = exit_order(individual_case, 60.0)
  assert first.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert first.amount == pytest.approx(1.0 - fee, abs=1e-8)

  settle(individual_case, first, 60.0, amount=0.4, status="canceled")

  for queue in range(1, 6):
    assert trade.get_custom_data(f"grind_{queue}_cluster_max_profit_stake") == (
      0.0 if queue == level else 1000.0 + queue
    )
    assert trade.get_custom_data(f"grind_{queue}_cluster_max_profit_rate") == (0.0 if queue == level else 10.0 + queue)
  assert trade.amount == pytest.approx(11.6 - fee, abs=1e-8)
  reloaded = reload_trade(trade)
  retry = exit_order(individual_case, 61.0, reloaded)
  assert retry.order_id != first.order_id
  assert retry.ft_order_tag == first.ft_order_tag
  assert retry.amount == pytest.approx(0.6 - fee, abs=1e-8)
  assert drive(individual_case, 61.0, reloaded) is None
  settle(individual_case, retry, 61.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(11.0, abs=1e-8)
  assert entry_snapshot(reloaded) == entries

  next_order = exit_order(individual_case, 60.0, reloaded)

  assert next_order.ft_order_tag == f"grind_{level}_derisk_entry {middle.id}"
  assert next_order.amount == pytest.approx(2.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "precision_mode,amount_precision,contract_size",
  [(2, 2, 1.0), (4, 0.01, 1.0), (2, 1, 0.1), (4, 0.1, 0.1)],
  ids=["decimal", "tick", "decimal-contracts", "tick-contracts"],
)
@pytest.mark.parametrize("minimum", [0.1, 5.0], ids=["low-value-minimum", "high-value-minimum"])
def test_stored_native_precision_dust_releases_next_entry_after_settlement_and_reload(
  individual_case, level, precision_mode, amount_precision, contract_size, minimum
):
  _, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  selected.amount = selected.ft_amount = selected.filled = 1.009
  selected.price = selected.average = selected.ft_price = 120.0
  selected.cost = selected.safe_filled * selected.safe_price
  middle, newest = add_lots(trade, level, ((2.0, 140.0), (1.0, 100.0)))
  trade.precision_mode = precision_mode
  trade.amount_precision = amount_precision
  trade.contract_size = contract_size
  trade.recalc_trade_from_orders()
  if trade.leverage == 1:
    quantity.settle_base_fee(bot, trade, selected, 0.001)
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage

  first = exit_order(individual_case, 60.0)

  assert first.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert first.amount == pytest.approx(1.0, abs=1e-8)
  assert (
    amount_to_contract_precision(
      selected.safe_amount_after_fee - first.amount,
      trade.amount_precision,
      trade.precision_mode,
      trade.contract_size,
    )
    == 0.0
  )
  settle(individual_case, first, 60.0)
  assert trade.amount == pytest.approx(9.0, abs=1e-8)
  reloaded = reload_trade(trade)
  assert (reloaded.precision_mode, reloaded.amount_precision, reloaded.contract_size) == (
    precision_mode,
    amount_precision,
    contract_size,
  )

  second = exit_order(individual_case, 60.0, reloaded)

  assert second.ft_order_tag == f"grind_{level}_derisk_entry {middle.id}"
  assert second.amount == pytest.approx(2.0, abs=1e-8)
  settle(individual_case, second, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(7.0, abs=1e-8)
  last = exit_order(individual_case, 60.0, reloaded)
  assert last.ft_order_tag == f"grind_{level}_derisk_entry {newest.id}"
  assert last.amount == pytest.approx(1.0, abs=1e-8)
  settle(individual_case, last, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(6.0, abs=1e-8)
  assert drive(individual_case, 60.0, reloaded) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("funding_ratio", [0.0, 0.999, 1.0], ids=["empty", "below-funded", "exact-funded"])
def test_add_after_targeted_fill_keeps_funding_guards_then_normal_profit_sells_all_remaining(
  individual_case, level, funding_ratio
):
  strategy, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  middle, newest = add_lots(trade, level, ((2.0, 140.0), (3.0, 120.0)))
  selected_exit = exit_order(individual_case, 60.0)
  assert selected_exit.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert selected_exit.amount == pytest.approx(1.0, abs=1e-8)
  settle(individual_case, selected_exit, 60.0)
  assert trade.amount == pytest.approx(11.0, abs=1e-8)
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", False)
  strategy.long_grind_entry_v4.return_value = True
  strategy._bad_trade_controller_capitulation = MagicMock(return_value=False)
  proposal = 150.0 / trade.leverage
  free_stake = proposal * funding_ratio
  bot.config["dry_run_wallet"] = trade.stake_amount - trade.realized_profit + free_stake
  bot.wallets = Wallets(bot.config, bot.exchange)
  assert bot.wallets.get_available_stake_amount() == pytest.approx(free_stake, abs=1e-8)

  assert drive(individual_case, 50.0) is None

  remaining = [newest, middle]
  if funding_ratio == 1.0:
    bot.execute_entry.assert_called_once_with(
      trade.pair,
      proposal,
      price=50.0,
      trade=trade,
      is_short=False,
      mode="pos_adjust",
      enter_tag=f"grind_{level}_entry",
    )
    # Model the accepted add at exactly the public bot's funded request.
    remaining = add_lots(trade, level, ((proposal * trade.leverage / 50.0, 50.0),)) + remaining
  else:
    bot.execute_entry.assert_not_called()
  strategy.long_grind_entry_v4.return_value = False
  bot.execute_entry.reset_mock()
  before = trade.amount
  expected = sum(entry.safe_amount_after_fee for entry in remaining)

  profit = exit_order(individual_case, 160.0)

  assert profit.ft_order_tag == f"grind_{level}_exit " + " ".join(str(entry.id) for entry in remaining)
  assert str(selected.id) not in profit.ft_order_tag.split()[1:]
  assert profit.amount == pytest.approx(expected, abs=1e-8)
  assert trade.amount == before
  settle(individual_case, profit, 160.0)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize(
  "v4_case,fee_ratio",
  [((False, 1.0), 0.0), ((False, 1.0), 0.001), ((False, 3.0), 0.0)],
  indirect=["v4_case"],
)
def test_orderable_below_minimum_retry_falls_through_to_all_remaining_net_profit_exit(
  individual_case, level, fee_ratio
):
  _, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  middle, newest = add_lots(trade, level, ((2.0, 80.0), (3.0, 120.0)))
  entries = [selected, middle, newest]
  for entry in entries:
    quantity.settle_base_fee(bot, trade, entry, entry.safe_filled * fee_ratio)
  targeted = exit_order(individual_case, 60.0)
  assert targeted.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert targeted.amount == pytest.approx(1.0 * (1.0 - fee_ratio), abs=1e-8)
  settle(individual_case, targeted, 60.0, amount=0.98, status="canceled")
  selected_remainder = selected.safe_amount_after_fee - 0.98
  assert selected_remainder > 0.0
  assert selected_remainder * 120.0 < 5.0
  assert (
    amount_to_contract_precision(selected_remainder, trade.amount_precision, trade.precision_mode, trade.contract_size)
    > 0.0
  )
  reloaded = reload_trade(trade)

  profit = exit_order(individual_case, 120.0, reloaded)

  assert profit.ft_order_tag == f"grind_{level}_exit {newest.id} {middle.id} {selected.id}"
  assert profit.amount == pytest.approx(
    selected_remainder + middle.safe_amount_after_fee + newest.safe_amount_after_fee, abs=1e-8
  )
  settle(individual_case, profit, 120.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_remaining_profit_keeps_gross_weighted_average_instead_of_individual_profit_policy(individual_case, level):
  strategy, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  selected.amount = selected.ft_amount = selected.filled = 3.0
  selected.price = selected.average = selected.ft_price = 120.0
  selected.cost = selected.safe_filled * selected.safe_price
  middle, newest = add_lots(trade, level, ((2.0, 200.0), (1.0, 100.0)))
  for entry in (selected, middle, newest):
    quantity.settle_base_fee(bot, trade, entry, entry.safe_filled * 0.001)
  targeted = exit_order(individual_case, 60.0)
  assert targeted.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert targeted.amount == pytest.approx(2.997, abs=1e-8)
  settle(individual_case, targeted, 60.0)
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", False)
  assert drive(individual_case, 110.0) is None  # The 100-price lot alone is profitable; the remaining queue is not.
  average = (newest.cost + middle.cost) / (newest.safe_filled + middle.safe_filled)
  threshold = getattr(strategy, f"system_v4_grind_{level}_profit_threshold_spot")
  boundary = average * (1.0 + threshold + trade.fee_open + trade.fee_close)
  assert drive(individual_case, boundary - 0.000001) is None

  profit = exit_order(individual_case, boundary + 0.000001)

  assert profit.ft_order_tag == f"grind_{level}_exit {newest.id} {middle.id}"
  assert profit.amount == pytest.approx(2.997, abs=1e-8)
  settle(individual_case, profit, boundary + 0.000001)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("amount", [0.0625, 0.078125], ids=["below-value-minimum", "exact-value-minimum"])
def test_small_eligible_lots_are_not_combined_or_enlarged_to_meet_minimum(individual_case, level, amount):
  _, trade, bot, _, _ = individual_case
  oldest = trade.orders[-1]
  oldest.amount = oldest.ft_amount = oldest.filled = amount
  oldest.cost = amount * oldest.safe_price
  trade.recalc_trade_from_orders()
  newest = add_lots(trade, level, ((amount, 100.0),))[0]
  assert amount * 64.0 <= 5.0
  assert 2.0 * amount * 64.0 > 5.0
  before = trade.amount

  assert drive(individual_case, 64.0) is None

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_not_called()
  assert trade.amount == before
  assert newest.safe_filled == oldest.safe_filled == amount


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_oldest_below_minimum_does_not_hide_a_newer_executable_entry(individual_case, level):
  _, trade, _, _, _ = individual_case
  tiny = trade.orders[-1]
  tiny.amount = tiny.ft_amount = tiny.filled = 0.01
  tiny.cost = tiny.safe_filled * tiny.safe_price
  executable = add_lots(trade, level, ((1.0, 100.0),))[0]
  assert (60.0 - tiny.safe_price) / tiny.safe_price < -0.22
  assert 0.0 < tiny.safe_amount_after_fee * 60.0 < 5.0

  order = exit_order(individual_case, 60.0)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {executable.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(individual_case, order, 60.0)
  assert trade.amount == pytest.approx(6.01, abs=1e-8)
  assert tiny.safe_filled == 0.01
  assert drive(individual_case, 60.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_native_reserve_clips_only_the_selected_entry(individual_case, level):
  _, trade, _, _, _ = individual_case
  selected = trade.orders[-1]
  previous_exit = trade.orders[1]
  previous_exit.amount = previous_exit.ft_amount = previous_exit.filled = 9.99
  previous_exit.cost = 999.0
  trade.recalc_trade_from_orders()
  tiny = add_lots(trade, level, ((0.01, 80.0),))[0]

  order = exit_order(individual_case, 60.0)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert 0.0 < order.amount < selected.safe_amount_after_fee
  reserve = 5.0 * 1.55 / 60.0
  assert order.amount == pytest.approx(1.02 - reserve, abs=1e-8)
  settle(individual_case, order, 60.0)
  assert trade.amount == pytest.approx(reserve, abs=1e-8)
  assert tiny.safe_filled == 0.01
  assert drive(individual_case, 60.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (False, 5.0)], indirect=True)
def test_raw_entry_loss_boundary_does_not_include_trade_fees(individual_case, level):
  _, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  trade.fee_open = trade.fee_close = 0.005
  assert drive(individual_case, 78.000001) is None
  assert drive(individual_case, 78.0) is None

  order = exit_order(individual_case, 77.999999)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert order.amount == pytest.approx(1.0, abs=1e-8)
  settle(individual_case, order, 77.999999)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)
  assert bot.exchange.create_order.call_count == 1


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_initial_position_is_not_enrolled_by_a_grind_like_entry_tag(individual_case, level):
  _, trade, _, _, _ = individual_case
  trade.orders[0].ft_order_tag = f"grind_{level}_entry"
  original = trade.orders[-1]
  selected = add_lots(trade, level, ((2.0, 120.0),))[0]
  order = exit_order(individual_case, 60.0)
  assert order.ft_order_tag == f"grind_{level}_derisk_entry {original.id}"
  assert order.amount == pytest.approx(1.0)
  settle(individual_case, order, 60.0)
  next_order = exit_order(individual_case, 60.0)
  assert next_order.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert next_order.amount == pytest.approx(2.0)
  settle(individual_case, next_order, 60.0)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)
  assert drive(individual_case, 60.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("gate", ["open-entry", "open-exit", "disabled-derisk"])
def test_existing_open_order_and_derisk_switch_guards_preserve_inventory(individual_case, level, gate):
  strategy, trade, bot, _, _ = individual_case
  add_lots(trade, level, ((2.0, 140.0), (3.0, 120.0)))
  if gate == "disabled-derisk":
    setattr(strategy, f"system_v4_grind_{level}_use_derisk", False)
  else:
    funding.fill(
      trade,
      trade.entry_side if gate == "open-entry" else trade.exit_side,
      1.0,
      60.0,
      f"grind_{level}_entry" if gate == "open-entry" else f"grind_{level}_derisk_entry {trade.orders[-1].id}",
      filled=0.0,
    )
    trade.orders[-1].status = "open"
    trade.orders[-1].ft_is_open = True
  before = trade.amount
  count = len(trade.orders)

  assert drive(individual_case, 60.0) is None

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_not_called()
  assert trade.amount == before
  assert len(trade.orders) == count


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_targeted_retry_is_capped_by_referenced_entry_not_oversized_order_remainder(individual_case, level):
  _, trade, _, _, _ = individual_case
  selected = trade.orders[-1]
  add_lots(trade, level, ((2.0, 140.0),))
  tag = f"grind_{level}_derisk_entry {selected.id}"
  funding.fill(trade, trade.exit_side, 5.0, 60.0, tag, filled=0.25)
  assert trade.orders[-1].safe_remaining == 4.75

  retry = exit_order(individual_case, 60.0)

  assert retry.ft_order_tag == tag
  assert retry.amount == pytest.approx(0.75, abs=1e-8)
  settle(individual_case, retry, 60.0)
  assert trade.amount == pytest.approx(8.0, abs=1e-8)
  next_order = exit_order(individual_case, 60.0)
  assert next_order.ft_order_tag == f"grind_{level}_derisk_entry {trade.orders[3].id}"
  assert next_order.amount == pytest.approx(2.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("suffix", ["missing", "nonnumeric", "unknown", "zero", "negative", "multiple", "other-queue"])
def test_malformed_or_unknown_target_history_never_debits_unrelated_entries(individual_case, level, suffix):
  _, trade, _, _, _ = individual_case
  oldest = trade.orders[-1]
  newest = add_lots(trade, level, ((2.0, 120.0),))[0]
  other = add_lots(trade, level % 5 + 1, ((0.5, 100.0),))[0] if suffix == "other-queue" else None
  ids = {
    "missing": "",
    "nonnumeric": "not-an-id",
    "unknown": "999999",
    "zero": "0",
    "negative": "-1",
    "multiple": f"{oldest.id} {newest.id}",
    "other-queue": str(other.id) if other is not None else "",
  }
  tag = f"grind_{level}_derisk_entry" + (f" {ids[suffix]}" if ids[suffix] else "")
  funding.fill(trade, trade.exit_side, 1.0, 60.0, tag, filled=0.125)
  before = trade.amount
  reloaded = reload_trade(trade)

  first = exit_order(individual_case, 60.0, reloaded)

  assert first.ft_order_tag == f"grind_{level}_derisk_entry {oldest.id}"
  assert first.amount == pytest.approx(1.0, abs=1e-8)
  settle(individual_case, first, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(before - 1.0, abs=1e-8)
  second = exit_order(individual_case, 60.0, reloaded)
  assert second.ft_order_tag == f"grind_{level}_derisk_entry {newest.id}"
  assert second.amount == pytest.approx(2.0, abs=1e-8)
  settle(individual_case, second, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(before - 3.0, abs=1e-8)
  if other is not None:
    assert Trade.session.get(type(other), other.id).safe_filled == 0.5
  assert drive(individual_case, 60.0, reloaded) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("boundary", ["derisk", "exit", "global"])
def test_historical_native_queue_boundaries_do_not_resurrect_closed_cohorts(individual_case, level, boundary):
  _, trade, _, _, _ = individual_case
  oldest = trade.orders[-1]
  add_lots(trade, level, ((2.0, 140.0),))
  tag = "derisk_global" if boundary == "global" else f"grind_{level}_{boundary} {oldest.id}"
  # Historical native tags close the whole older cohort, not just the listed ID.
  funding.fill(trade, trade.exit_side, 3.0, 100.0, tag)
  older, newest = add_lots(trade, level, ((1.0, 90.0), (2.0, 80.0)))
  # Exercise history accounting outside the native grind-5 liquidation-add band.
  if trade.leverage > 1:
    trade.liquidation_price = 30.0
  reloaded = reload_trade(trade)
  assert reloaded.leverage == 1 or reloaded.liquidation_price is None or 50.0 > reloaded.liquidation_price * 1.2

  first = exit_order(individual_case, 50.0, reloaded)

  assert first.ft_order_tag == f"grind_{level}_derisk_entry {older.id}"
  assert first.amount == pytest.approx(1.0)
  settle(individual_case, first, 50.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(8.0, abs=1e-8)
  next_order = exit_order(individual_case, 50.0, reloaded)
  assert next_order.ft_order_tag == f"grind_{level}_derisk_entry {newest.id}"
  assert next_order.amount == pytest.approx(2.0)
  settle(individual_case, next_order, 50.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(6.0, abs=1e-8)
  assert drive(individual_case, 50.0, reloaded) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [1])
def test_historical_global_boundary_cuts_all_five_native_cohorts(individual_case):
  strategy, trade, _, _, _ = individual_case
  for queue in range(2, 6):
    add_lots(trade, queue, ((1.0, 120.0),))
  funding.fill(trade, trade.exit_side, 5.0, 100.0, "derisk_global")
  current = add_lots(trade, 5, ((2.0, 100.0),))[0]
  for queue in range(1, 6):
    setattr(strategy, f"system_v4_grind_{queue}_use_derisk", True)
  reloaded = reload_trade(trade)

  order = exit_order(individual_case, 50.0, reloaded)

  assert order.ft_order_tag == f"grind_5_derisk_entry {current.id}"
  assert order.amount == pytest.approx(2.0)
  settle(individual_case, order, 50.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(6.0, abs=1e-8)
  assert drive(individual_case, 50.0, reloaded) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("sold", [0.4, 1.0], ids=["partial-target-history", "completed-target-history"])
def test_accepted_top_tag_is_read_as_targeted_history_without_becoming_a_producer(individual_case, sold):
  _, trade, _, _, _ = individual_case
  oldest = trade.orders[-1]
  middle, newest = add_lots(trade, 1, ((2.0, 90.0), (3.0, 80.0)))
  funding.fill(trade, trade.exit_side, sold, 60.0, f"grind_1_derisk_top {oldest.id}")
  reloaded = reload_trade(trade)

  profit = exit_order(individual_case, 200.0, reloaded)

  expected_ids = [newest.id, middle.id] + ([oldest.id] if sold < 1.0 else [])
  assert profit.ft_order_tag == "grind_1_exit " + " ".join(str(entry_id) for entry_id in expected_ids)
  assert profit.amount == pytest.approx(6.0 - sold, abs=1e-8)
  settle(individual_case, profit, 200.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(True, 3.0)], indirect=True)
def test_original_short_queues_keep_native_whole_queue_derisk(individual_case, level):
  _, trade, _, _, _ = individual_case
  oldest = trade.orders[-1]
  middle, newest = add_lots(trade, level, ((2.0, 90.0), (3.0, 80.0)))

  order = exit_order(individual_case, 140.0)

  assert order.ft_order_tag == f"grind_{level}_derisk {newest.id} {middle.id} {oldest.id}"
  assert order.amount == pytest.approx(6.0, abs=1e-8)
  settle(individual_case, order, 140.0)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "funding_case",
  [(version, 1, "grind") for version in (None, "system_v3", "system_v3_1", "system_v3_2")],
  indirect=True,
)
def test_stored_older_systems_keep_native_whole_queue_accounting(funded_grind_case, quantity_bot, level, mocker):
  strategy, trade, _ = funded_grind_case
  strategy.long_grind_entry_v3 = MagicMock(return_value=False)
  case = observe_bot(strategy, trade, quantity_bot, mocker)
  oldest = trade.orders[-1]
  middle, newest = add_lots(trade, level, ((2.0, 90.0), (3.0, 80.0)))
  # Keep this accounting control outside the older futures grind-5 liquidation-add band.
  rate = 70.0
  assert trade.liquidation_price is None or rate > trade.liquidation_price * 1.2

  order = exit_order(case, rate)

  assert order.ft_order_tag == f"grind_{level}_derisk {newest.id} {middle.id} {oldest.id}"
  assert order.amount == pytest.approx(6.0, abs=1e-8)
  settle(case, order, rate)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("legacy_grind_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_legacy_mode_keeps_native_stop_quantity_and_settled_remainder(legacy_grind_case, legacy_quantity_bot, mocker):
  strategy, trade, rate = legacy_grind_case
  case = observe_bot(strategy, trade, legacy_quantity_bot, mocker)
  stake, tag = legacy_funding.expected_stop(trade, rate)
  expected = -stake * trade.amount / trade.stake_amount
  before = trade.amount

  order = exit_order(case, rate)

  assert order.ft_order_tag == tag
  assert order.amount == pytest.approx(expected, abs=1e-8)
  settle(case, order, rate)
  assert trade.amount == pytest.approx(before - expected, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [1])
def test_earlier_queue_profit_keeps_priority_over_later_queue_entry_derisk(individual_case):
  strategy, trade, _, _, _ = individual_case
  oldest = trade.orders[-1]
  newest = add_lots(trade, 1, ((1.0, 50.0),))[0]
  later = add_lots(trade, 2, ((2.0, 150.0),))[0]
  strategy.system_v4_grind_2_use_derisk = True

  profit = exit_order(individual_case, 80.0)

  assert profit.ft_order_tag == f"grind_1_exit {newest.id} {oldest.id}"
  assert profit.amount == pytest.approx(2.0, abs=1e-8)
  settle(individual_case, profit, 80.0)
  next_order = exit_order(individual_case, 80.0)
  assert next_order.ft_order_tag == f"grind_2_derisk_entry {later.id}"
  assert next_order.amount == pytest.approx(2.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_below_minimum_target_retry_keeps_other_queue_normal_profit_reachable(individual_case, level):
  strategy, trade, _, _, _ = individual_case
  selected = trade.orders[-1]
  setattr(strategy, f"system_v4_grind_{level}_enable", False)
  targeted = exit_order(individual_case, 60.0)
  assert targeted.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  settle(individual_case, targeted, 60.0, amount=0.99, status="canceled")
  other_queue = level % 5 + 1
  other = add_lots(trade, other_queue, ((1.0, 50.0),))[0]

  order = exit_order(individual_case, 60.0)

  assert order.ft_order_tag == f"grind_{other_queue}_exit {other.id}"
  assert order.amount == pytest.approx(1.0)
  settle(individual_case, order, 60.0)
  assert trade.amount == pytest.approx(6.01, abs=1e-8)


@pytest.mark.parametrize("rescue_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize("filled,emergency_expected", [(3.99, True), (3.8, False)])
def test_targeted_retry_preserves_native_emergency_priority(
  emergency_bot, rescue_case, level, filled, emergency_expected, mocker
):
  strategy, trade = rescue_case
  strategy.system_v4_grind_1_enable = False
  selected = trade.orders[1]
  selected.ft_order_tag = f"grind_{level}_entry"
  tag = f"grind_{level}_derisk_entry {selected.id}"
  rescue.add_order(trade, trade.exit_side, tag, 4.0, filled, "canceled")
  # The placement-only emergency fixture also needs concrete exchange settlement responses.
  emergency_bot.exchange.check_order_canceled_empty.return_value = False
  emergency_bot.exchange.order_has_fee.return_value = True
  emergency_bot.exchange.extract_cost_curr_rate.side_effect = lambda fee, pair, cost, amount: (
    fee["cost"],
    fee["currency"],
    fee["rate"],
  )
  emergency_bot.exchange.get_liquidation_price.return_value = None
  case = observe_bot(strategy, trade, emergency_bot, mocker)
  before = trade.amount
  rate = emergency_bot.exchange.get_rates.return_value[1]

  order = exit_order(case, rate)

  assert order.ft_order_tag == ("derisk_level_3" if emergency_expected else tag)
  expected = 5.0 if emergency_expected else 0.2
  assert order.amount == pytest.approx(expected, abs=1e-8)
  strategy._bad_trade_controller_derisk_hold.assert_not_called()
  assert len({entry.order_id for entry in trade.orders}) == len(trade.orders)
  filled_amount = order.amount
  settle(case, order, rate)
  emergency_bot.exchange.check_order_canceled_empty.assert_called_once()
  assert trade.amount == pytest.approx(before - filled_amount, abs=1e-8)


@pytest.mark.parametrize(
  "v4_case,newer_fee,selected_fee",
  [((False, 1.0), 0.001, 0.004), ((False, 3.0), 0.0, 0.0)],
  indirect=["v4_case"],
  ids=["unequal-base-fees", "long-futures"],
)
def test_partial_target_fill_preserves_proportional_gross_profit_basis_and_remaining_net(
  individual_case, level, newer_fee, selected_fee
):
  strategy, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  selected.amount = selected.ft_amount = selected.filled = 2.0
  selected.price = selected.average = selected.ft_price = 200.0
  selected.cost = selected.safe_filled * selected.safe_price
  newer = add_lots(trade, level, ((1.0, 100.0),))[0]
  quantity.settle_base_fee(bot, trade, selected, selected_fee)
  quantity.settle_base_fee(bot, trade, newer, newer_fee)
  targeted = exit_order(individual_case, 60.0)
  assert targeted.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert targeted.amount == pytest.approx(2.0 - selected_fee, abs=1e-8)
  settle(individual_case, targeted, 60.0, amount=1.0, status="canceled")
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", False)
  remaining_net = selected.safe_amount_after_fee - 1.0
  remaining_gross = selected.safe_filled * remaining_net / selected.safe_amount_after_fee
  average = (newer.cost + remaining_gross * selected.safe_price) / (newer.safe_filled + remaining_gross)
  mode = "futures" if trade.leverage > 1 else "spot"
  threshold = getattr(strategy, f"system_v4_grind_{level}_profit_threshold_{mode}")
  boundary = average * (1.0 + threshold + trade.fee_open + trade.fee_close)
  # Only the selected retry misses this value minimum; the whole remaining queue is executable.
  bot.exchange.get_min_pair_stake_amount.return_value = 160.0 / trade.leverage
  assert remaining_net * (boundary + 0.000001) < 160.0
  assert (newer.safe_amount_after_fee + remaining_net) * boundary > 160.0
  assert drive(individual_case, boundary - 0.000001) is None

  profit = exit_order(individual_case, boundary + 0.000001)

  assert profit.ft_order_tag == f"grind_{level}_exit {newer.id} {selected.id}"
  assert profit.amount == pytest.approx(newer.safe_amount_after_fee + remaining_net, abs=1e-8)
  settle(individual_case, profit, boundary + 0.000001)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("funded", [False, True])
def test_settled_target_history_keeps_native_liquidation_rescue_admission_and_funding(individual_case, level, funded):
  strategy, trade, bot, _, _ = individual_case
  strategy._bad_trade_controller_capitulation = MagicMock(return_value=False)
  selected = trade.orders[-1]
  order = exit_order(individual_case, 60.0)
  assert order.ft_order_tag == f"grind_{level}_derisk_entry {selected.id}"
  assert order.amount == pytest.approx(1.0)
  settle(individual_case, order, 60.0)
  funding.fill(trade, trade.exit_side, 4.0, 100.0, "exit_normal")
  assert trade.amount == pytest.approx(2.0, abs=1e-8)
  setattr(strategy, f"system_v4_grind_{level}_enable", False)
  for queue in range(1, 6):
    setattr(strategy, f"system_v4_grind_{queue}_use_derisk", False)
  strategy.system_v4_grind_5_enable = True
  strategy.system_v4_grind_5_liquidation_rescue_enable = True
  strategy.system_v4_grind_5_liquidation_rescue_threshold = 0.05
  strategy.system_v4_grind_5_liquidation_rescue_max_stake = 0.5
  trade.liquidation_price = 92.0
  proposal = max(
    1000.0 * strategy.system_v4_grind_5_stakes_futures[0] / trade.leverage,
    5.0 * 1.5 / trade.leverage,
  )
  budget = proposal if funded else 0.0
  bot.config["dry_run_wallet"] = trade.stake_amount - trade.realized_profit + budget
  bot.wallets = Wallets(bot.config, bot.exchange)
  assert bot.wallets.get_available_stake_amount() == pytest.approx(budget, abs=1e-8)
  calls = bot.exchange.create_order.call_count

  assert drive(individual_case, 94.0) is None

  assert bot.exchange.create_order.call_count == calls
  if funded:
    bot.execute_entry.assert_called_once_with(
      trade.pair,
      proposal,
      price=94.0,
      trade=trade,
      is_short=False,
      mode="pos_adjust",
      enter_tag="grind_5_entry",
    )
    assert strategy._grind_entry_tag == "g5_liq2"
  else:
    bot.execute_entry.assert_not_called()
  assert trade.amount == pytest.approx(2.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("rate", [29.0, 50.0], ids=["native-below-minimum", "native-equal-minimum"])
def test_native_selected_entry_minimum_uses_normalized_quantity(individual_case, level, rate):
  _, trade, bot, _, _ = individual_case
  tiny = trade.orders[-1]
  tiny.amount = tiny.ft_amount = tiny.filled = 0.2
  tiny.cost = tiny.safe_filled * tiny.safe_price
  trade.precision_mode = 2
  trade.amount_precision = 1
  trade.contract_size = 1.0
  executable = add_lots(trade, level, ((1.0, 100.0),))[0]
  quantity.settle_base_fee(bot, trade, tiny, 0.0002)
  raw_amount = tiny.safe_amount_after_fee
  native_amount = amount_to_contract_precision(
    raw_amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  assert raw_amount == pytest.approx(0.1998, abs=1e-8)
  assert native_amount == 0.1
  assert raw_amount * rate > 5.0
  assert native_amount * rate <= 5.0
  if rate == 50.0:
    assert native_amount * rate == 5.0
  else:
    assert native_amount * rate < 5.0
  assert trade.amount == 7.1
  entries = entry_snapshot(trade)

  order = exit_order(individual_case, rate)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {executable.id}"
  assert order.amount == 1.0
  settle(individual_case, order, rate)
  assert trade.amount == 6.1
  assert tiny.safe_filled == 0.2
  assert tiny.safe_fee_base == 0.0002
  assert entry_snapshot(trade) == entries
  assert drive(individual_case, rate) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_native_reserve_clip_below_normalized_minimum_preserves_position(individual_case):
  _, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  selected.amount = selected.ft_amount = selected.filled = 0.3
  selected.cost = selected.safe_filled * selected.safe_price
  previous_exit = trade.orders[1]
  previous_exit.amount = previous_exit.ft_amount = previous_exit.filled = 10.0
  previous_exit.cost = 1000.0
  trade.precision_mode = 2
  trade.amount_precision = 1
  trade.contract_size = 1.0
  trade.recalc_trade_from_orders()
  rate = 45.0
  if trade.leverage > 1:
    trade.liquidation_price = 30.0
    assert rate > trade.liquidation_price * 1.2
  assert trade.amount == 0.3
  minimum = 5.0 / trade.leverage
  raw_amount = (0.3 * rate - 7.75) / rate
  native_amount = amount_to_contract_precision(
    raw_amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  assert 0.1 < raw_amount < 0.2
  assert raw_amount * rate / trade.leverage > minimum
  assert native_amount == 0.1
  assert native_amount * rate / trade.leverage < minimum
  entries = entry_snapshot(trade)
  orders = len(trade.orders)

  assert drive(individual_case, rate) is None

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_not_called()
  assert trade.amount == 0.3
  assert len(trade.orders) == orders
  assert entry_snapshot(trade) == entries


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "partial_fills,expected_remainders,expected_balances",
  [((0.4,), (0.2,), (6.2,)), ((0.1, 0.2), (0.5, 0.3), (6.5, 6.3))],
  ids=["one-partial-fill", "two-partial-fills"],
)
def test_native_partial_fills_retry_exact_decimal_remainder_after_reload(
  individual_case, level, partial_fills, expected_remainders, expected_balances
):
  _, trade, _, _, filled = individual_case
  selected = trade.orders[-1]
  selected.amount = selected.ft_amount = selected.filled = 0.6
  selected.cost = selected.safe_filled * selected.safe_price
  trade.precision_mode = 2
  trade.amount_precision = 1
  trade.contract_size = 1.0
  trade.recalc_trade_from_orders()
  assert trade.amount == 6.6
  tag = f"grind_{level}_derisk_entry {selected.id}"
  entries = entry_snapshot(trade)
  order = exit_order(individual_case, 60.0)
  assert order.ft_order_tag == tag
  assert order.amount == 0.6

  for partial_fill, remainder, balance in zip(partial_fills, expected_remainders, expected_balances, strict=True):
    settle(individual_case, order, 60.0, amount=partial_fill, status="canceled", trade=trade)
    assert order.safe_filled == partial_fill
    assert order.safe_remaining == remainder
    assert trade.amount == balance
    trade = reload_trade(trade)
    persisted = Trade.session.get(type(order), order.id)
    assert persisted.safe_remaining == remainder
    assert persisted.ft_order_tag == tag

    retry = exit_order(individual_case, 60.0, trade)

    assert retry.order_id != order.order_id
    assert retry.ft_order_tag == tag
    assert retry.amount == remainder
    assert drive(individual_case, 60.0, trade) is None
    order = retry

  settle(individual_case, order, 60.0, trade=trade)
  assert filled.call_count == len(partial_fills) + 1
  assert filled.spy_exception is None
  assert trade.amount == 6.0
  assert entry_snapshot(trade) == entries
  assert drive(individual_case, 60.0, trade) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_native_targeted_retry_below_normalized_minimum_selects_next_entry(individual_case, level):
  _, trade, bot, _, _ = individual_case
  tiny = trade.orders[-1]
  tiny.amount = tiny.ft_amount = tiny.filled = 0.21
  tiny.cost = tiny.safe_filled * tiny.safe_price
  trade.precision_mode = 2
  trade.amount_precision = 2
  trade.contract_size = 1.0
  executable = add_lots(trade, level, ((1.0, 100.0),))[0]
  quantity.settle_base_fee(bot, trade, tiny, 0.001)
  tag = f"grind_{level}_derisk_entry {tiny.id}"
  funding.fill(trade, trade.exit_side, 0.21, 49.0, tag, filled=0.1)
  historical = trade.orders[-1]
  remainder = float(FtPrecise(tiny.safe_amount_after_fee) - FtPrecise(historical.safe_filled))
  native_amount = amount_to_contract_precision(
    remainder, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  assert historical.safe_remaining > remainder
  assert remainder == 0.109
  assert remainder * 49.0 > 5.0
  assert native_amount == 0.1
  assert native_amount * 49.0 < 5.0
  assert trade.amount == 7.1
  entries = entry_snapshot(trade)
  history = (
    historical.amount,
    historical.safe_filled,
    historical.safe_remaining,
    historical.cost,
    historical.ft_order_tag,
  )

  order = exit_order(individual_case, 49.0)

  assert order.ft_order_tag == f"grind_{level}_derisk_entry {executable.id}"
  assert order.amount == 1.0
  settle(individual_case, order, 49.0)
  assert trade.amount == 6.1
  assert tiny.safe_filled == 0.21
  assert tiny.safe_fee_base == 0.001
  assert entry_snapshot(trade) == entries
  assert (
    historical.amount,
    historical.safe_filled,
    historical.safe_remaining,
    historical.cost,
    historical.ft_order_tag,
  ) == history
  assert drive(individual_case, 49.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_native_remaining_profit_requires_normalized_value_above_minimum(individual_case, level):
  strategy, trade, bot, _, _ = individual_case
  selected = trade.orders[-1]
  selected.amount = selected.ft_amount = selected.filled = 0.21
  selected.price = selected.average = selected.ft_price = 40.0
  selected.cost = selected.safe_filled * selected.safe_price
  trade.precision_mode = 2
  trade.amount_precision = 2
  trade.contract_size = 1.0
  trade.recalc_trade_from_orders()
  quantity.settle_base_fee(bot, trade, selected, 0.001)
  funding.fill(trade, trade.exit_side, 0.1, 49.0, f"grind_{level}_derisk_entry {selected.id}")
  historical = trade.orders[-1]
  assert historical.safe_remaining == 0.0
  remainder = float(FtPrecise(selected.safe_amount_after_fee) - FtPrecise(historical.safe_filled))
  native_amount = amount_to_contract_precision(
    remainder, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  assert remainder == 0.109
  assert native_amount == 0.1
  assert remainder * 49.0 > 5.0 > native_amount * 49.0
  threshold = getattr(strategy, f"system_v4_grind_{level}_profit_threshold_spot")
  assert (49.0 - selected.safe_price) / selected.safe_price > threshold + trade.fee_open + trade.fee_close
  assert trade.amount == 6.1
  entries = entry_snapshot(trade)

  assert drive(individual_case, 49.0) is None

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_not_called()
  assert trade.amount == 6.1
  assert entry_snapshot(trade) == entries
  assert trade.get_custom_data(f"grind_{level}_cluster_max_profit_rate") == pytest.approx(0.225, abs=1e-8)
  assert native_amount * 50.1 > 5.0

  profit = exit_order(individual_case, 50.1)

  assert profit.ft_order_tag == f"grind_{level}_exit {selected.id}"
  assert profit.amount == 0.1
  settle(individual_case, profit, 50.1)
  assert trade.amount == 6.0
  assert entry_snapshot(trade) == entries
  assert historical.safe_filled == 0.1
  assert historical.safe_remaining == 0.0
  assert drive(individual_case, 50.1) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_native_remaining_queue_net_sum_keeps_exact_amount_quantum(individual_case, level):
  _, trade, _, _, _ = individual_case
  oldest = trade.orders[-1]
  oldest.amount = oldest.ft_amount = oldest.filled = 0.1
  oldest.cost = oldest.safe_filled * oldest.safe_price
  trade.precision_mode = 2
  trade.amount_precision = 1
  trade.contract_size = 1.0
  newest = add_lots(trade, level, ((0.7, 100.0),))[0]
  trade.recalc_trade_from_orders()
  assert oldest.safe_fee_base == newest.safe_fee_base == 0.0
  assert trade.amount == 6.8
  entries = entry_snapshot(trade)

  profit = exit_order(individual_case, 120.0)

  assert profit.ft_order_tag == f"grind_{level}_exit {newest.id} {oldest.id}"
  assert profit.amount == 0.8
  settle(individual_case, profit, 120.0)
  assert trade.amount == 6.0
  assert entry_snapshot(trade) == entries
  assert drive(individual_case, 120.0) is None
