"""Legacy queue profit exits use the current value of the requested coins."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_liquidation_rescue as rescue


rescue_case = rescue.rescue_case
buyback_quantity_bot = buyback.buyback_quantity_bot


@pytest.mark.parametrize("rescue_case", [(False, 1), (False, 3), (True, 3)], indirect=True)
@pytest.mark.parametrize(
  "mode,entry_tag",
  [("regular", f"g{n}") for n in range(1, 7)]
  + [("grind", f"gd{n}") for n in range(1, 7)]
  + [("grind", "dl1"), ("grind", "dl2")],
)
@pytest.mark.parametrize(
  "filled,minimum,gate,expected",
  [
    (0.046875, 5.0, "ready", 0.046875),
    (0.0625, 5.0, "ready", 0.0625),
    (0.03125, 5.0, "ready", None),
    (0.0390625, 5.0, "ready", None),
    (10.0, 640.0, "ready", 7.25),
    (0.046875, 5.0, "pending", None),
    (0.046875, 5.0, "no-profit", None),
  ],
  ids=["current-value-only", "both-values", "below-minimum", "exact-minimum", "reserve", "pending", "no-profit"],
)
def test_legacy_first_profit_exit_uses_current_value(
  buyback_quantity_bot, mode, entry_tag, filled, minimum, gate, expected
):
  bot, trade, _ = buyback_quantity_bot
  trade.set_custom_data("system_version", None)
  trade.open_date = rescue.NOW.replace(year=2024, month=5, day=1)
  trade.fee_open = trade.fee_close = 0.0
  bot.strategy.long_grind_entry = MagicMock(return_value=False)
  bot.strategy.short_grind_entry = MagicMock(return_value=False)
  if mode == "grind":
    trade.enter_tag = "620" if trade.is_short else "120"
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = first.filled = 5.0 if mode == "regular" else 10.0
  first.cost = first.filled * first.price
  first.order_date = first.order_filled_date = trade.open_date_utc
  if mode == "grind":
    rescue.add_order(trade, trade.exit_side, "gm0", 2.5 if entry_tag in ("dl1", "dl2") else 5.0)
    if entry_tag in ("dl1", "dl2"):
      rescue.add_order(trade, trade.exit_side, "d", 2.5)
  entry = rescue.add_order(trade, trade.entry_side, entry_tag, max(1.0, filled), filled, "canceled")
  entry.price = entry.average = entry.ft_price = 200.0 if trade.is_short else 100.0
  entry.cost = filled * entry.price
  trade.recalc_trade_from_orders()
  initial_amount = 5.0 + filled
  assert trade.amount == initial_amount
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, entry_tag, 1.0, 0.0, "open")
  rate = entry.price if gate == "no-profit" else 128.0
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  bot.exchange.get_rates.return_value = (rate, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  if expected is None:
    bot.exchange.create_order.assert_not_called()
    assert trade.amount == initial_amount
    return
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == f"{entry_tag} {entry.id}"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(initial_amount - expected))) <= Decimal("0.00000001")
