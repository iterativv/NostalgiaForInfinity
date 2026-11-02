"""Legacy regular queues must not spend the initial position's base coins."""

from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import MarginMode
from freqtrade.exchange import amount_to_contract_precision

from tests.unit import test_NFIX8_legacy_grind_quantity as quantity
from tests.unit import test_NFIX8_partial_exit as partial
from tests.unit import test_NFIX8_partial_exit_minimum_engine as minimum


partial_exit_case = partial.partial_exit_case
partial_bot = minimum.partial_bot


@pytest.fixture(params=range(1, 7))
def level(request):
  return request.param


@pytest.fixture
def regular_case(partial_bot, partial_exit_case, level, mocker):
  strategy, trade = partial_exit_case
  trade.set_custom_data("system_version", None)
  trade.open_date = partial.NOW.replace(year=2024, month=5, day=1)
  trade.orders[0].ft_order_tag = trade.enter_tag
  entry = trade.orders[1]
  entry.ft_order_tag = f"g{level}"
  entry.amount = entry.ft_amount = entry.filled = 10.0
  entry.cost = 1000.0
  for index, order in enumerate(trade.orders):
    order.order_date = order.order_filled_date = trade.open_date_utc + timedelta(hours=index)
  trade.fee_open = trade.fee_close = 0.0
  trade.funding_fees = trade.funding_fee_running = 0.0
  trade.recalc_trade_from_orders()
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  strategy.regular_mode_use_grind_stops = True
  strategy.long_grind_entry = MagicMock(return_value=False)
  strategy.long_grind_entry_v3 = MagicMock(return_value=False)
  strategy.short_grind_entry = MagicMock(return_value=False)
  partial_bot.margin_mode = MarginMode.ISOLATED if trade.leverage > 1 else MarginMode.NONE
  partial_bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  partial_bot.exchange.get_liquidation_price.return_value = None
  partial_bot.exchange.check_order_canceled_empty.return_value = False
  partial_bot.exchange.order_has_fee.return_value = True
  partial_bot.exchange.extract_cost_curr_rate.side_effect = lambda fee, pair, cost, amount: (
    fee["cost"],
    fee["currency"],
    fee["rate"],
  )
  partial_bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  partial_bot._notify_enter = MagicMock()
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  clock.return_value = partial.NOW
  create_order = partial_bot.exchange.create_order.side_effect
  partial_bot.exchange.create_order.side_effect = lambda **kwargs: {
    **create_order(**kwargs),
    "id": f"regular-quantity-{len(trade.orders)}",
    "timestamp": int(clock.return_value.timestamp() * 1000),
  }

  def settle(order, filled, status="closed"):
    order.update_from_ccxt_object(
      {
        "id": order.order_id,
        "status": status,
        "amount": order.amount,
        "filled": filled,
        "remaining": order.amount - filled,
        "price": order.price,
        "average": order.price,
        "cost": filled * order.price,
        "timestamp": int(clock.return_value.timestamp() * 1000),
        "lastTradeTimestamp": int(clock.return_value.timestamp() * 1000),
      }
    )
    trade.update_trade(order)

  return partial_bot, trade, settle, clock


@pytest.mark.parametrize(
  "partial_exit_case,fee_ratio",
  [((False, 1), 0.0), ((False, 1), 0.001), ((False, 3), 0.0), ((True, 3), 0.0)],
  indirect=["partial_exit_case"],
  ids=["spot-no-base-fee", "spot-base-fee", "long-futures", "short-futures"],
)
@pytest.mark.parametrize("reason", ["profit", "stop"])
def test_regular_exit_preserves_initial_inventory(regular_case, level, fee_ratio, reason):
  bot, trade, settle, _ = regular_case
  entry = trade.orders[1]
  quantity.settle_base_fee(bot, trade, entry, 10.0 * fee_ratio)
  rate = (80.0 if trade.is_short else 128.0) if reason == "profit" else (121.0 if trade.is_short else 79.0)
  quantity.set_rate(bot, trade, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  prefix = "g" if reason == "profit" else "sg"
  assert order.ft_order_tag == f"{prefix}{level} {entry.id}"
  assert order.ft_order_side == trade.exit_side
  expected = Decimal("10") * (Decimal("1") - Decimal(str(fee_ratio)))
  assert abs(Decimal(str(order.amount)) - expected) <= Decimal("0.00000001")
  settle(order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal("10")) <= Decimal("0.00000001")


@pytest.mark.parametrize("partial_exit_case", [(False, 1)], indirect=True)
def test_regular_exit_keeps_gross_weighted_price(regular_case, level):
  bot, trade, _, _ = regular_case
  entry = trade.orders[1]
  entry.amount = entry.ft_amount = entry.filled = 1.0
  entry.cost = 100.0
  partial.add_order(trade, trade.entry_side, f"g{level}", 9.0, 9.0, price=200.0)
  for order in trade.orders[1:]:
    quantity.settle_base_fee(bot, trade, order, order.safe_filled * 0.001)
  threshold = getattr(bot.strategy, f"regular_mode_grind_{level}_profit_threshold_spot")
  rate = 190.0 * (1.0 + threshold + trade.fee_open + trade.fee_close) + 0.000001
  quantity.set_rate(bot, trade, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  assert trade.orders[-1].ft_order_tag.startswith(f"g{level} ")


@pytest.mark.parametrize("partial_exit_case", [(False, 1)], indirect=True)
def test_regular_exit_keeps_minimum_reserve(regular_case, level):
  bot, trade, settle, _ = regular_case
  entry = trade.orders[1]
  quantity.settle_base_fee(bot, trade, entry, 0.01)
  bot.exchange.get_min_pair_stake_amount.return_value = 850.0
  quantity.set_rate(bot, trade, 128.0)
  expected = trade.amount - 850.0 * 1.55 / 128.0

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"g{level} {entry.id}"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  assert order.amount < 9.99
  settle(order, order.amount)
  assert trade.amount * 128.0 == pytest.approx(850.0 * 1.55, rel=0, abs=0.000002)


@pytest.mark.parametrize("partial_exit_case", [(False, 1)], indirect=True)
@pytest.mark.parametrize("level", [1, 6])
def test_regular_partial_exit_retries_only_net_remainder(regular_case, level):
  bot, trade, settle, clock = regular_case
  entry = trade.orders[1]
  quantity.settle_base_fee(bot, trade, entry, 0.01)
  quantity.set_rate(bot, trade, 128.0)
  bot.check_and_call_adjust_trade_position(trade)
  original = trade.orders[-1]
  assert original.ft_order_tag == f"g{level} {entry.id}"
  settle(original, 4.0, "canceled")
  clock.return_value += timedelta(minutes=5)
  bot.exchange.create_order.reset_mock()

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry is not original
  assert retry.ft_order_tag == original.ft_order_tag
  assert abs(Decimal(str(retry.amount)) - Decimal("5.99")) <= Decimal("0.00000002")
  settle(retry, retry.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal("10")) <= Decimal("0.00000002")


@pytest.mark.parametrize("partial_exit_case", [(False, 1)], indirect=True)
@pytest.mark.parametrize("level", [1])
def test_initial_fee_does_not_reduce_regular_queue(regular_case):
  bot, trade, settle, _ = regular_case
  quantity.settle_base_fee(bot, trade, trade.orders[0], 0.01)
  quantity.set_rate(bot, trade, 128.0)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"g1 {trade.orders[1].id}"
  assert abs(Decimal(str(order.amount)) - Decimal("10")) <= Decimal("0.00000001")
  settle(order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal("9.99")) <= Decimal("0.00000001")
