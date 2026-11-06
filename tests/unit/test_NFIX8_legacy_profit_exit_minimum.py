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


@pytest.mark.parametrize("rescue_case", [(False, 1), (False, 3), (True, 3)], indirect=True)
@pytest.mark.parametrize(
  "mode,entry_tag,exit_tag",
  [("regular", f"g{n}", f"sg{n}") for n in range(1, 7)]
  + [("grind", f"gd{n}", f"dd{n}") for n in range(1, 7)]
  + [("grind", "dl1", "ddl1"), ("grind", "dl2", "ddl2")],
)
@pytest.mark.parametrize(
  "filled,gate,expected",
  [
    (0.046875, "ready", 0.046875),
    (0.125, "ready", 0.125),
    (0.03125, "ready", None),
    (0.0390625, "ready", None),
    (0.1, "reserve", 0.05945312),
    (0.046875, "reserve-blocked", None),
    (0.046875, "disabled", None),
    (0.046875, "pending", None),
    (0.046875, "no-loss", None),
    (0.046875, "old-trade", None),
  ],
  ids=[
    "current-only",
    "both-values",
    "below",
    "equal",
    "reserve",
    "reserve-blocked",
    "disabled",
    "pending",
    "no-loss",
    "old",
  ],
)
def test_legacy_queue_stop_uses_current_value(
  buyback_quantity_bot, mode, entry_tag, exit_tag, filled, gate, expected, caplog
):
  bot, trade, _ = buyback_quantity_bot
  trade.set_custom_data("system_version", None)
  bot.strategy.long_grind_entry = MagicMock(return_value=False)
  bot.strategy.short_grind_entry = MagicMock(return_value=False)
  # Explicitly exercise opt-in regular stops without changing their default.
  bot.strategy.regular_mode_use_grind_stops = gate != "disabled"
  bot.strategy.derisk_use_grind_stops = gate != "disabled"
  trade.open_date = rescue.NOW.replace(year=2024, month=5, day=1)
  if mode == "grind":
    trade.enter_tag = "620" if trade.is_short else "120"
    trade.open_date = rescue.NOW.replace(month=7, day=1)
  if gate == "old-trade":
    trade.open_date = rescue.NOW.replace(year=2024, month=4, day=15)
    if mode == "grind":
      trade.open_date = rescue.NOW.replace(year=2024, month=9, day=12)
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = 0.05
  first.filled = 0.01 if gate in ("reserve", "reserve-blocked") else 0.02
  first.remaining = first.amount - first.filled
  first.status = "canceled" if first.remaining else "closed"
  first.cost = first.filled * first.price
  first.order_date = first.order_filled_date = trade.open_date_utc
  trade.recalc_trade_from_orders()
  rescue.add_order(trade, trade.entry_side, "r", 1.0 - first.filled)
  if mode == "grind" or gate in ("reserve", "reserve-blocked"):
    amount = 0.98 if gate in ("reserve", "reserve-blocked") else 0.01
    rescue.add_order(trade, trade.exit_side, "d" if mode == "grind" else "p", amount)
  entry = rescue.add_order(trade, trade.entry_side, entry_tag, 0.25, filled, "canceled")
  # Qualify the native stop without triggering the earlier futures emergency
  # add at 65% / leverage. Both modeled entries have minimum-compliant requests.
  entry.price = entry.average = entry.ft_price = 106.0 if trade.is_short else 162.0
  if gate == "no-loss":
    entry.price = entry.average = entry.ft_price = 128.0
  entry.cost = filled * entry.safe_price
  trade.recalc_trade_from_orders()
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, entry_tag, 0.25, 0.0, "open")
  bot.exchange.get_rates.return_value = (128.0, 128.0)
  before = trade.amount
  if gate == "ready" and filled == 0.046875:
    assert filled * trade.stake_amount / trade.amount < 5.0 / trade.leverage

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
  assert order.ft_order_tag == f"{exit_tag} {entry.id}"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(before - expected))) <= Decimal("0.00000001")
  assert trade.is_open
