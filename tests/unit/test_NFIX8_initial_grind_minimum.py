"""The initial grind profit exit validates its current order value."""

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_liquidation_rescue as rescue
from tests.unit.test_NFIX8_legacy_grind_funding import fill


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


INITIAL_ROUTES = [
  ((False, 1), "gmd0", 192.0),
  ((False, 3), "gmd0", 192.0),
  ((True, 3), "gm0", 192.0),
  ((True, 3), "gmd0", 100.0),
]
REDUCED_CASES = [
  ("current-only", 0.109375, 64.0, 0.04882812),
  ("both-values", 0.1875, 112.0, 0.12695312),
  ("unclipped", 2.0, 112.0, 1.0),
  ("current-below", 0.9375, 100.0, None),
  ("current-equal", 0.99609375, 100.0, None),
  ("outer-below", 0.109375, 64.0, None),
  ("outer-equal", 0.109375, 64.0, None),
  ("no-threshold", 0.109375, 64.0, None),
  ("pending", 0.109375, 64.0, None),
  ("prior-profit", 0.109375, 64.0, None),
  ("prior-stop", 0.109375, 64.0, None),
  ("stop-disabled", 0.109375, 64.0, None),
  ("legacy", 0.109375, 64.0, 0.04882812),
]


@pytest.mark.parametrize(
  "rescue_case,exit_tag,first_price,case",
  [
    pytest.param(
      (mode[0], 2 if case[0] in ("outer-equal", "current-equal") and mode[1] > 1 else mode[1]),
      exit_tag,
      first_price,
      case,
      id=f"{case[0]}-{exit_tag}-{'short' if mode[0] else 'long'}-{'futures' if mode[1] > 1 else 'spot'}",
    )
    for mode, exit_tag, first_price in INITIAL_ROUTES
    for case in REDUCED_CASES
  ],
  indirect=["rescue_case"],
)
def test_initial_exit_after_reductions_uses_current_value(
  buyback_quantity_bot, mocker, caplog, exit_tag, first_price, case
):
  gate, inventory, entry_price, expected = case
  bot, trade, _ = buyback_quantity_bot
  trade.enter_tag = "620" if trade.is_short else "120"
  trade.set_custom_data("system_version", {"legacy": "legacy"}.get(gate, "system_v4"))
  trade.open_date = rescue.NOW - timedelta(days=5)
  mocker.patch.object(bot.strategy, "long_grind_entry", return_value=False)
  mocker.patch.object(bot.strategy, "short_grind_entry", return_value=False)
  bot.strategy.derisk_use_grind_stops = gate != "stop-disabled"
  bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  bot.exchange.get_rates.return_value = (128.0, 128.0)
  minimum = 5.0 / trade.leverage
  first_quantity = 1.0
  scale = 1.0
  if gate in ("current-below", "current-equal"):
    minimum = 50.0 / trade.leverage
    first_quantity = 4.0
  if gate == "outer-below":
    minimum = 2.0
    scale = trade.leverage
    first_quantity = 0.04 * trade.leverage
  if gate == "outer-equal":
    # Binary-exact 1x/2x inputs distinguish the strict outer comparison.
    first_quantity = 0.125
  initial_price = 128.0 if gate == "no-threshold" else first_price
  bot.exchange.get_min_pair_stake_amount.return_value = minimum
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = first.filled = first_quantity
  first.price = first.average = first.ft_price = initial_price
  first.cost = first_quantity * initial_price
  first.order_date = first.order_filled_date = trade.open_date_utc
  trade.recalc_trade_from_orders()
  # Modeled prior reduction and repriced additions retain the original entry.
  # Their remaining basis is independent of its profit/stop distance.
  fill(trade, trade.entry_side, first_quantity * 2.0, (336.0 - initial_price) / 2.0, "d1")
  barrier = {"prior-profit": "gm0", "prior-stop": "gmd0"}.get(gate, "p")
  fill(trade, trade.exit_side, trade.amount - 0.0625 * scale, 128.0, barrier)
  fill(trade, trade.entry_side, 2.0, entry_price, "d1", (inventory - 0.078125) * scale)
  fill(trade, trade.entry_side, 1.0, 124.0, "d1", 0.015625 * scale)
  before = trade.amount
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, "d1", 1.0, 0.0, "open")
  if gate in ("current-only", "legacy"):
    assert 0.048828125 * trade.stake_amount / trade.amount < minimum
    assert first_quantity * trade.stake_amount / trade.amount - minimum * 1.5 > minimum
  if gate == "outer-equal":
    assert first_quantity * (trade.stake_amount / trade.amount) - minimum * 1.5 == minimum
  if gate == "current-equal":
    assert before * 128.0 / trade.leverage - minimum * 1.55 == minimum
  if gate == "stop-disabled" and exit_tag == "gm0":
    expected = 0.04882812

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
  assert order.ft_order_tag == exit_tag
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(before - expected))) <= Decimal("0.00000001")
  assert trade.is_open
