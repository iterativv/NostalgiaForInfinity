"""Rebuy de-risk checks the order's current value, not its entry-basis stake."""

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_legacy_grind_funding as funding
from tests.unit import test_NFIX8_liquidation_rescue as rescue


rescue_case = rescue.rescue_case
buyback_quantity_bot = buyback.buyback_quantity_bot
CASES = [
  ("current-only", 0.13, 53.0, True, False, 0.0525),
  ("both-values", 0.15, 53.0, True, False, 0.0725),
  ("current-below", 0.1274, 53.0, True, False, None),
  ("current-equal", 0.1275, 53.0, True, False, None),
  ("no-loss", 0.13, 80.0, True, False, None),
  ("disabled", 0.13, 53.0, False, False, None),
  ("pending", 0.13, 53.0, True, True, None),
]


@pytest.mark.parametrize(
  "rescue_case,system,case",
  [
    pytest.param((False, leverage), system, case, id=f"{system}-{leverage}x-{case[0]}")
    for system in (None, "system_v3", "system_v4")
    for leverage in (1, 2, 3)
    for case in CASES
  ]
  + [pytest.param((False, 3), system, CASES[0], id=system) for system in ("system_v3_1", "system_v3_2")],
  indirect=["rescue_case"],
)
def test_rebuy_derisk_uses_current_minimum(buyback_quantity_bot, system, case, caplog):
  _, remaining, prior_rate, enabled, pending, expected = case
  bot, trade, _ = buyback_quantity_bot
  trade.enter_tag = "61"
  trade.open_date = rescue.NOW - timedelta(days=4)
  trade.set_custom_data("system_version", system)
  bot.strategy.derisk_enable = enabled
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = first.filled = 0.05
  first.cost = 5.0
  first.order_date = first.order_filled_date = trade.open_date
  trade.recalc_trade_from_orders()
  # Modeled fills: realized losses can remain after the residual price recovers.
  for amount, rate in ((0.15, 80.0), (0.25, 70.0)):
    funding.fill(trade, trade.entry_side, amount, rate, "r")
  funding.fill(trade, trade.exit_side, 0.45 - remaining, prior_rate, "partial_exit")
  if pending:
    rescue.add_order(trade, trade.entry_side, "r", 0.1, 0.0, "open")
  before = trade.amount
  bot.exchange.get_rates.return_value = (100.0, 100.0)
  bot.exchange.get_max_pair_stake_amount.return_value = 0.0

  bot.check_and_call_adjust_trade_position(trade)

  assert all(record.levelno < 40 for record in caplog.records)
  bot.execute_entry.assert_not_called()
  if expected is None:
    bot.exchange.create_order.assert_not_called()
    assert trade.amount == before
    return
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == "derisk_level_3"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal("0.0775")) <= Decimal("0.00000001")
  assert trade.is_open


@pytest.mark.parametrize(
  "rescue_case,system,case",
  [
    pytest.param((True, leverage), system, case, id=f"{system}-{leverage}x-{case[0]}")
    for system in (None, "system_v3", "system_v4")
    for leverage, rate, expected in ((2, 142.0, 0.04542253), (3, 136.0, 0.04301470))
    for case in (
      ("current-only", rate, 0.05, 5.0, True, False, expected),
      ("both-values", rate, 0.06, 5.0, True, False, expected + 0.02),
      ("current-below", rate, 0.05, 6.0, True, False, None),
      ("no-loss", 105.0, 0.05, 5.0, True, False, None),
      ("disabled", rate, 0.05, 5.0, False, False, None),
      ("pending", rate, 0.05, 5.0, True, True, None),
    )
  ]
  + [
    pytest.param((True, 3), system, ("current-equal", 136.0, 0.5625, 60.0, True, False, None), id=f"{system}-equal")
    for system in (None, "system_v3", "system_v4")
  ]
  + [
    pytest.param((True, 3), system, ("current-only", 136.0, 0.05, 5.0, True, False, 0.04301470), id=system)
    for system in ("system_v3_1", "system_v3_2")
  ],
  indirect=["rescue_case"],
)
def test_short_rebuy_derisk_uses_current_minimum(buyback_quantity_bot, system, case, caplog):
  _, rate, amount, minimum, enabled, pending, expected = case
  bot, trade, _ = buyback_quantity_bot
  trade.enter_tag = "561"
  trade.open_date = rescue.NOW - timedelta(days=2)
  trade.set_custom_data("system_version", system)
  bot.strategy.derisk_enable = enabled
  frame, _ = bot.strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame["protections_short_global"] = True
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = first.filled = amount
  first.cost = amount * 100.0
  first.order_date = first.order_filled_date = trade.open_date
  trade.recalc_trade_from_orders()
  funding.fill(trade, trade.entry_side, amount, 110.0, "r")
  if pending:
    rescue.add_order(trade, trade.entry_side, "r", 0.1, 0.0, "open")
  before = trade.amount
  bot.exchange.get_rates.return_value = (rate, rate)
  # Boundary controls model a higher exchange minimum after the earlier fills.
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  bot.exchange.get_max_pair_stake_amount.return_value = 0.0

  bot.check_and_call_adjust_trade_position(trade)

  assert all(record.levelno < 40 for record in caplog.records)
  bot.execute_entry.assert_not_called()
  if expected is None:
    bot.exchange.create_order.assert_not_called()
    assert trade.amount == before
    return
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == "derisk_level_3"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(before - expected))) <= Decimal("0.00000001")
  assert trade.is_open
