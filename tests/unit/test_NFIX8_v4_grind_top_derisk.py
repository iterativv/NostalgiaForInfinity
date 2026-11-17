"""One long V4 queue reduces actual remaining top lots through the public bot."""

from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from freqtrade.exchange import amount_to_contract_precision
from freqtrade.persistence import Trade

from tests.unit import test_NFIX8_liquidation_rescue as rescue
from tests.unit import test_NFIX8_partial_exit_emergency as emergency
from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_quantity as quantity
from tests.unit.test_NFIX8_legacy_grind_funding import fill


v4_case = funding.v4_case
quantity_bot = quantity.quantity_bot
rescue_case = emergency.rescue_case
emergency_bot = emergency.emergency_bot


@pytest.fixture
def level():
  return 1


@pytest.fixture
def top_case(v4_case, quantity_bot, mocker):
  strategy, trade, _ = v4_case
  quantity_bot.exchange.get_pair_quote_currency.return_value = "USDT"
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  filled = mocker.spy(strategy, "order_filled")
  return strategy, trade, quantity_bot, adjustment, filled


def add_lots(trade, level=1, lots=((2.0, 90.0), (3.0, 80.0))):
  orders = []
  for amount, price in lots:
    fill(trade, trade.entry_side, amount, price, f"grind_{level}_entry")
    orders.append(trade.orders[-1])
  return orders


def drive(case, rate, trade=None):
  _, initial_trade, bot, adjustment, _ = case
  trade = initial_trade if trade is None else trade
  quantity.set_rate(bot, trade, rate)
  before = len(trade.orders)
  bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  return trade.orders[-1] if len(trade.orders) > before else None


def exit_order(case, rate, trade=None):
  order = drive(case, rate, trade)
  assert order is not None
  return order


def settle(case, order, rate, *, amount=None, status="closed", trade=None):
  _, initial_trade, bot, _, filled = case
  trade = initial_trade if trade is None else trade
  amount = order.amount if amount is None else amount
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
    "remaining": order.amount - amount,
    "cost": amount * rate,
    "timestamp": int(funding.NOW.timestamp() * 1000),
    "fee": {"cost": 0.0, "currency": "USDT", "rate": 0.0},
  }
  bot.update_trade_state(trade, order.order_id, action_order=payload, send_msg=False)
  assert filled.called
  assert filled.spy_exception is None
  assert order.ft_is_open is False


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_top_derisk_settles_one_lot_then_keeps_other_lots_after_reload(top_case):
  _, trade, _, _, _ = top_case
  first = trade.orders[-1]
  second, third = add_lots(trade)

  order = exit_order(top_case, 60.0)

  assert order.amount == pytest.approx(1.0)
  assert order.ft_order_tag == f"grind_1_derisk_top {first.id}"
  assert drive(top_case, 60.0) is None  # The actual open exit blocks another order.
  settle(top_case, order, 60.0)
  assert trade.amount == pytest.approx(11.0)
  trade_id = trade.id
  Trade.session.expunge_all()
  reloaded = Trade.session.get(Trade, trade_id)

  next_order = exit_order(top_case, 60.0, reloaded)

  assert next_order.ft_order_tag == f"grind_1_derisk_top {second.id}"
  assert next_order.amount == pytest.approx(2.0)
  settle(top_case, next_order, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(9.0)
  last_order = exit_order(top_case, 60.0, reloaded)
  assert last_order.ft_order_tag == f"grind_1_derisk_top {third.id}"
  assert last_order.amount == pytest.approx(3.0)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("selection", ["actual-average", "oldest-fill", "native-id", "missing-fill-date"])
def test_top_selection_uses_actual_fill_price_then_native_chronology(top_case, selection):
  _, trade, _, _, _ = top_case
  first = trade.orders[-1]
  second, third = add_lots(trade, lots=((2.0, 90.0), (3.0, 80.0)))
  if selection == "actual-average":
    second.price = 1000.0  # A high limit price must not outrank an actual120 average fill.
    second.average = 90.0
    third.price = 1.0
    third.average = 120.0
    third.cost = third.safe_filled * third.average
    expected = third
  else:
    second.average = second.price = 100.0
    second.cost = second.safe_filled * second.average
    first.order_filled_date = funding.NOW - timedelta(hours=2)
    second.order_filled_date = funding.NOW - timedelta(hours=3)
    if selection == "oldest-fill":
      expected = second
    elif selection == "native-id":
      second.order_filled_date = first.order_filled_date
      expected = first
    else:
      first.order_filled_date = second.order_filled_date = None
      expected = first
  Trade.session.flush()
  trade.recalc_trade_from_orders()

  order = exit_order(top_case, 60.0)

  assert order.ft_order_tag == f"grind_1_derisk_top {expected.id}"
  assert order.amount == pytest.approx(expected.safe_amount_after_fee)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_initial_position_is_never_enrolled_as_a_top_grind(top_case):
  _, trade, _, _, _ = top_case
  trade.orders[0].ft_order_tag = "grind_1_entry"
  current = trade.orders[-1]
  add_lots(trade)

  order = exit_order(top_case, 60.0)

  assert order.ft_order_tag == f"grind_1_derisk_top {current.id}"
  assert order.amount == pytest.approx(1.0)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("fee", [0.0, 0.001])
def test_partial_cancel_retries_net_remainder_once_and_preserves_other_queue_peaks(top_case, fee):
  strategy, trade, bot, _, _ = top_case
  selected = trade.orders[-1]
  second, _ = add_lots(trade)
  quantity.settle_base_fee(bot, trade, selected, fee)
  strategy.system_v4_grind_1_enable = False
  trade.set_custom_data("grind_1_cluster_max_profit_stake", 50.0)
  trade.set_custom_data("grind_1_cluster_max_profit_rate", 0.5)
  trade.set_custom_data("grind_2_cluster_max_profit_stake", 60.0)
  trade.set_custom_data("grind_2_cluster_max_profit_rate", 0.6)
  first = exit_order(top_case, 60.0)
  assert first.amount == pytest.approx(1.0 - fee)

  settle(top_case, first, 60.0, amount=0.4, status="canceled")

  assert trade.get_custom_data("grind_1_cluster_max_profit_stake") == 0.0
  assert trade.get_custom_data("grind_1_cluster_max_profit_rate") == 0.0
  assert trade.get_custom_data("grind_2_cluster_max_profit_stake") == 60.0
  assert trade.get_custom_data("grind_2_cluster_max_profit_rate") == 0.6
  trade_id = trade.id
  Trade.session.expunge_all()
  reloaded = Trade.session.get(Trade, trade_id)
  retry = exit_order(top_case, 61.0, reloaded)
  assert retry.ft_order_tag == first.ft_order_tag
  assert retry.amount == pytest.approx(0.6 - fee, abs=1e-8)
  settle(top_case, retry, 61.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(11.0, abs=1e-8)

  next_order = exit_order(top_case, 60.0, reloaded)

  assert next_order.ft_order_tag == f"grind_1_derisk_top {second.id}"
  assert next_order.amount == pytest.approx(2.0)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("precision_mode,amount_precision", [(2, 2), (4, 0.01)])
@pytest.mark.parametrize("minimum", [0.1, 5.0])
def test_completed_top_sale_releases_unorderable_base_fee_dust_after_reload(
  top_case, precision_mode, amount_precision, minimum
):
  _, trade, bot, _, _ = top_case
  selected = trade.orders[-1]
  second, third = add_lots(trade)
  quantity.settle_base_fee(bot, trade, selected, 0.001)
  trade.precision_mode = precision_mode
  trade.amount_precision = amount_precision
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  bot.exchange.get_min_pair_stake_amount.return_value = minimum
  trade.set_custom_data("grind_1_cluster_max_profit_stake", 50.0)
  trade.set_custom_data("grind_1_cluster_max_profit_rate", 0.5)
  trade.set_custom_data("grind_2_cluster_max_profit_stake", 60.0)
  trade.set_custom_data("grind_2_cluster_max_profit_rate", 0.6)
  Trade.session.flush()

  first = exit_order(top_case, 60.0)
  assert first.ft_order_tag == f"grind_1_derisk_top {selected.id}"
  assert first.amount == pytest.approx(0.99)
  settle(top_case, first, 60.0)
  assert trade.amount == pytest.approx(11.0)
  assert trade.get_custom_data("grind_1_cluster_max_profit_stake") == 0.0
  assert trade.get_custom_data("grind_1_cluster_max_profit_rate") == 0.0
  assert trade.get_custom_data("grind_2_cluster_max_profit_stake") == 60.0
  assert trade.get_custom_data("grind_2_cluster_max_profit_rate") == 0.6
  trade_id = trade.id
  Trade.session.expunge_all()
  reloaded = Trade.session.get(Trade, trade_id)

  next_order = exit_order(top_case, 60.0, reloaded)

  assert next_order.ft_order_tag == f"grind_1_derisk_top {second.id}"
  assert next_order.amount == pytest.approx(2.0)
  settle(top_case, next_order, 60.0, trade=reloaded)
  last_order = exit_order(top_case, 60.0, reloaded)
  assert last_order.ft_order_tag == f"grind_1_derisk_top {third.id}"
  assert last_order.amount == pytest.approx(3.0)
  settle(top_case, last_order, 60.0, trade=reloaded)
  assert reloaded.amount == pytest.approx(6.0)  # Native Trade applies the stored amount precision.


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_profit_exit_after_unexecutable_top_retry_sells_only_remaining_net_inventory(top_case):
  strategy, trade, bot, _, _ = top_case
  selected = trade.orders[-1]
  second, third = add_lots(trade)
  quantity.settle_base_fee(bot, trade, selected, 0.001)
  quantity.settle_base_fee(bot, trade, second, 0.002)
  strategy.system_v4_grind_1_enable = False
  top_exit = exit_order(top_case, 60.0)
  settle(top_case, top_exit, 60.0, amount=0.98, status="canceled")

  profit_exit = exit_order(top_case, 120.0)

  assert profit_exit.ft_order_tag.startswith("grind_1_exit ")
  assert set(profit_exit.ft_order_tag.split()[1:]) == {str(selected.id), str(second.id), str(third.id)}
  assert profit_exit.amount == pytest.approx(0.019 + 1.998 + 3.0, abs=1e-8)
  settle(top_case, profit_exit, 120.0)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_tiny_top_is_not_combined_with_other_lots_to_meet_minimum(top_case):
  _, trade, _, _, _ = top_case
  first = trade.orders[-1]
  first.amount = first.ft_amount = first.filled = 0.01
  first.cost = 1.0
  trade.recalc_trade_from_orders()
  add_lots(trade)
  before = trade.amount

  assert drive(top_case, 60.0) is None
  assert trade.amount == before


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_reserve_clips_only_selected_lot_without_consuming_other_inventory(top_case):
  _, trade, _, _, _ = top_case
  selected = trade.orders[-1]
  previous_exit = trade.orders[1]
  previous_exit.amount = previous_exit.ft_amount = previous_exit.filled = 9.99
  previous_exit.cost = 999.0
  trade.recalc_trade_from_orders()
  add_lots(trade, lots=((0.01, 80.0),))

  order = exit_order(top_case, 60.0)

  assert order.ft_order_tag == f"grind_1_derisk_top {selected.id}"
  assert 0.0 < order.amount < 1.0
  assert trade.amount - order.amount == pytest.approx(5.0 * 1.55 / 60.0, abs=1e-8)
  settle(top_case, order, 60.0)
  assert drive(top_case, 60.0) is None
  assert trade.amount == pytest.approx(5.0 * 1.55 / 60.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (False, 5.0)], indirect=True)
def test_shipped_raw_queue_average_trigger_does_not_become_leveraged_pnl(top_case):
  strategy, trade, _, _, _ = top_case
  add_lots(trade)
  strategy.system_v4_grind_1_enable = False
  for market in ("spot", "futures"):
    strategy.__dict__.pop(f"system_v4_grind_1_derisk_{market}")

  assert drive(top_case, 67.61) is None
  order = exit_order(top_case, 67.59)
  assert order.ft_order_tag == f"grind_1_derisk_top {trade.orders[2].id}"
  assert order.amount == pytest.approx(1.0)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("boundary", ["grind_1_derisk", "grind_1_exit", "derisk_global"])
def test_legacy_whole_queue_boundaries_do_not_resurrect_historical_top_lots(top_case, boundary):
  _, trade, _, _, _ = top_case
  old = trade.orders[-1]
  fill(trade, trade.exit_side, 1.0, 100.0, f"{boundary} {old.id}")
  current, _ = add_lots(trade, lots=((1.0, 90.0), (2.0, 80.0)))

  order = exit_order(top_case, 50.0)

  assert order.ft_order_tag == f"grind_1_derisk_top {current.id}"
  assert order.amount == pytest.approx(1.0)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("level", [2, 3, 4, 5])
def test_other_original_long_queues_keep_native_whole_queue_derisk(top_case, level):
  _, trade, _, _, _ = top_case
  add_lots(trade, level=level)

  order = exit_order(top_case, 60.0)

  assert order.amount == pytest.approx(6.0)
  assert order.ft_order_tag.startswith(f"grind_{level}_derisk ")


@pytest.mark.parametrize("v4_case", [(True, 3.0)], indirect=True)
def test_original_short_queue_keeps_native_whole_queue_derisk(top_case):
  strategy, trade, _, _, _ = top_case
  strategy.short_grind_entry_v4 = MagicMock(return_value=False)
  add_lots(trade)

  order = exit_order(top_case, 140.0)

  assert order.amount == pytest.approx(6.0)
  assert order.ft_order_tag.startswith("grind_1_derisk ")


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_unexecutable_top_retry_keeps_other_queue_profit_exit_reachable(top_case):
  strategy, trade, _, _, _ = top_case
  add_lots(trade)
  strategy.system_v4_grind_1_enable = False
  top_exit = exit_order(top_case, 60.0)
  settle(top_case, top_exit, 60.0, amount=0.99, status="canceled")
  fill(trade, trade.entry_side, 1.0, 50.0, "grind_2_entry")
  other = trade.orders[-1]

  order = exit_order(top_case, 60.0)

  assert order.ft_order_tag == f"grind_2_exit {other.id}"
  assert order.amount == pytest.approx(1.0)


@pytest.mark.parametrize("rescue_case", [(False, 3)], indirect=True)
@pytest.mark.parametrize("filled,emergency_expected", [(3.99, True), (3.8, False)])
def test_targeted_retry_keeps_native_emergency_priority(
  emergency_bot, rescue_case, mocker, filled, emergency_expected
):
  strategy, trade = rescue_case
  strategy.system_v4_grind_1_enable = False
  selected = trade.orders[1]
  tag = f"grind_1_derisk_top {selected.id}"
  rescue.add_order(trade, trade.exit_side, tag, 4.0, filled, "canceled")
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  emergency_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  order = trade.orders[-1]
  assert order.ft_is_open
  assert order.ft_order_tag == ("derisk_level_3" if emergency_expected else tag)
  assert order.amount == pytest.approx(5.0 if emergency_expected else 0.2)
