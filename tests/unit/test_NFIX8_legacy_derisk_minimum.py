"""Legacy whole-trade and re-entry reductions use current exchange value."""

from decimal import Decimal

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_liquidation_rescue as rescue
from tests.unit.test_NFIX8_legacy_grind_funding import fill


rescue_case = rescue.rescue_case
buyback_quantity_bot = buyback.buyback_quantity_bot
MODES = [(False, 1), (False, 3), (True, 3)]


@pytest.fixture
def legacy_derisk_bot(buyback_quantity_bot, mocker):
  bot, trade, _ = buyback_quantity_bot
  mocker.patch.object(bot.strategy, "long_grind_entry", return_value=False)
  mocker.patch.object(bot.strategy, "long_grind_entry_v3", return_value=False)
  mocker.patch.object(bot.strategy, "short_grind_entry", return_value=False)
  bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  bot.exchange.get_rates.return_value = (128.0, 128.0)
  frame, _ = bot.strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(AROOND_14=100.0, AROOND_14_15m=100.0, protections_short_global=True, enter_short=False)
  frame["BBL_20_2.0"] = 0.0
  bot.strategy.dp._set_cached_df(trade.pair, "5m", frame, bot.strategy.config["candle_type_def"])
  return bot, trade


@pytest.mark.parametrize("rescue_case", MODES, indirect=True)
@pytest.mark.parametrize("scalp", [False, True], ids=["overall", "scalp"])
@pytest.mark.parametrize(
  "inventory,gate,expected",
  [
    (0.109375, "ready", 0.04882812),
    (0.1875, "ready", 0.12695312),
    (0.9375, "below", None),
    (0.99609375, "equal", None),
    (0.078125, "reserve-blocked", None),
    (0.109375, "disabled", None),
    (0.109375, "pending", None),
    (0.109375, "old", None),
    (0.109375, "no-loss", None),
  ],
  ids=["current-only", "both-values", "below", "equal", "reserve-blocked", "disabled", "pending", "old", "no-loss"],
)
def test_regular_derisk_checks_current_value(legacy_derisk_bot, scalp, inventory, gate, expected, caplog):
  bot, trade = legacy_derisk_bot
  trade.set_custom_data("system_version", "legacy")
  trade.open_date = rescue.NOW.replace(year=2024, month=10, day=1)
  if gate == "old":
    trade.open_date = rescue.NOW.replace(year=2024, month=9, day=12)
  if scalp:
    trade.enter_tag = "661" if trade.is_short else "161"
  bot.strategy.derisk_enable = gate != "disabled"
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = first.filled = 0.0625
  first.price = first.average = first.ft_price = 90.0
  first.cost = 5.625
  first.order_date = first.order_filled_date = trade.open_date_utc
  trade.recalc_trade_from_orders()
  # Fix whole-trade loss through completed cashflows, without mocking profit.
  target_profit = first.cost * (0.25 if gate == "no-loss" else (-0.10 if scalp else -0.50))
  entry_cost = first.cost + 90.0 + (inventory - first.filled) * 112.0
  if trade.is_short:
    exit_price = entry_cost - inventory * 128.0 - target_profit
  else:
    exit_price = entry_cost - inventory * 128.0 + target_profit
  fill(trade, trade.entry_side, 1.0, 90.0, "r")
  fill(trade, trade.exit_side, 1.0, exit_price, "exit_normal")
  fill(trade, trade.entry_side, 1.0, 112.0, "r", inventory - first.filled)
  before = trade.amount
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, "r", 1.0, 0.0, "open")
  minimum = 50.0 if gate in ("below", "equal") else 5.0
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  if gate == "ready" and inventory == 0.109375:
    assert 0.048828125 * trade.stake_amount / trade.amount < 5.0 / trade.leverage

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
  assert order.ft_order_tag == ("d1" if scalp else "d")
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal("0.060546875")) <= Decimal("0.00000001")
  assert trade.is_open


@pytest.mark.parametrize("rescue_case", MODES, indirect=True)
@pytest.mark.parametrize(
  "quantity,gate,expected",
  [
    (0.046875, "ready", 0.046875),
    (0.125, "ready", 0.125),
    (0.046875, "below", None),
    (0.046875, "equal", None),
    (0.1, "reserve", 0.05945312),
    (0.046875, "reserve-blocked", None),
    (0.046875, "disabled", None),
    (0.046875, "pending", None),
    (0.046875, "done", None),
    (0.046875, "no-loss", None),
    (0.046875, "legacy", 0.046875),
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
    "done",
    "no-loss",
    "legacy",
  ],
)
def test_reentry_derisk_checks_current_value(legacy_derisk_bot, quantity, gate, expected, caplog):
  bot, trade = legacy_derisk_bot
  trade.set_custom_data("system_version", {"legacy": "legacy"}.get(gate, "system_v4"))
  trade.open_date = rescue.NOW.replace(month=7, day=1)
  trade.enter_tag = "620" if trade.is_short else "120"
  bot.strategy.position_adjustment_enable = gate != "disabled"
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.amount = first.ft_amount = first.filled = 1.0
  first.cost = 100.0
  first.order_date = first.order_filled_date = trade.open_date_utc
  trade.recalc_trade_from_orders()
  fill(trade, trade.exit_side, 0.5, 90.0 if trade.is_short else 110.0, "gm0")
  remaining = 0.02 if gate in ("reserve", "reserve-blocked") else 0.375
  fill(trade, trade.exit_side, 0.5 - remaining, 100.0, "d1")
  price = 112.0 if trade.is_short else 144.0
  if gate == "no-loss":
    price = 128.0
  fill(trade, trade.entry_side, 0.25, price, "d1", quantity)
  if gate == "done":
    fill(trade, trade.exit_side, quantity, 128.0, "d1")
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, "d1", 0.25, 0.0, "open")
  before = trade.amount
  minimum = {"below": 6.25, "equal": 6.0}.get(gate, 5.0)
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  if gate in ("ready", "legacy") and quantity == 0.046875:
    assert quantity * trade.stake_amount / trade.amount < 5.0 / trade.leverage

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
  assert order.ft_order_tag == "d1"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(before - expected))) <= Decimal("0.00000001")
  assert trade.is_open
