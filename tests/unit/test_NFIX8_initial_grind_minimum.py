"""The initial grind profit exit validates its current order value."""

from decimal import Decimal

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_liquidation_rescue as rescue


rescue_case = rescue.rescue_case
buyback_quantity_bot = buyback.buyback_quantity_bot
CASES = [
  ("current-only", 0.1251, 102.5, 0.001, None, 0.04949024),
  ("both-values", 0.13, 102.5, 0.001, None, 0.05439024),
  ("outer-below", 0.12, 110.0, 0.001, None, None),
  ("outer-equal", None, 110.0, 0.001, None, None),
  ("current-below", 0.1252, 101.81, 0.0, None, None),
  ("current-equal", 0.1252, 12.75 / 0.1252, 0.0, None, None),
  ("no-profit", 0.13, 100.0, 0.001, None, None),
  ("pending", 0.1251, 102.5, 0.001, "pending", None),
  ("prior-profit", 1.0, 102.5, 0.001, "gm0", None),
  ("prior-stop", 1.0, 102.5, 0.001, "gmd0", None),
]


@pytest.mark.parametrize(
  "rescue_case,system,case",
  [
    pytest.param((False, leverage), "system_v4", case, id=f"{case[0]}-{leverage}x")
    for leverage in (1, 3, 5)
    for case in CASES
  ]
  + [
    pytest.param((False, 1), None, CASES[0], id="legacy-route"),
    pytest.param((False, 1), "system_v3_2", CASES[0], id="v3-route"),
  ],
  indirect=["rescue_case"],
)
def test_initial_grind_profit_uses_current_minimum(buyback_quantity_bot, system, case):
  name, amount, rate, fee, barrier, expected = case
  bot, trade, _ = buyback_quantity_bot
  if name == "outer-equal":
    # Exact 5 margin against a 2 minimum avoids 5 / 3 boundary roundoff.
    amount = trade.leverage / 20.0
    bot.exchange.get_min_pair_stake_amount.return_value = 2.0
  trade.enter_tag = "120"
  trade.set_custom_data("system_version", system)
  trade.fee_open = trade.fee_close = fee
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = first.filled = amount
  first.cost = amount * first.price
  trade.recalc_trade_from_orders()
  if barrier == "pending":
    rescue.add_order(trade, trade.entry_side, "gd1", 1.0, 0.0, "open")
  elif barrier is not None:
    rescue.add_order(trade, trade.exit_side, barrier, 0.1)
  before = trade.amount
  bot.exchange.get_rates.return_value = (rate, rate)
  bot.exchange.get_max_pair_stake_amount.return_value = 0.0

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  if expected is None:
    bot.exchange.create_order.assert_not_called()
    assert trade.amount == before
    return
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == "gm0"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(before - expected))) <= Decimal("0.00000001")
  assert trade.is_open
