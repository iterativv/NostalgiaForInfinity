"""Stage reductions use current exchange value after prior realized losses."""

from datetime import timedelta
from decimal import Decimal

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_liquidation_rescue as rescue
from tests.unit.test_NFIX8_legacy_grind_funding import fill


rescue_case = rescue.rescue_case
buyback_quantity_bot = buyback.buyback_quantity_bot
MODES = [(False, 1), (False, 3), (True, 3)]
STAGES = [
  (mode, version, level)
  for mode in MODES
  for version, count in [("legacy", 3), ("system_v3", 3), ("system_v3_2", 4), ("system_v4", 4)]
  for level in range(1, count + 1)
  if not (mode[0] and level == 4)
]


@pytest.fixture
def stage_bot(buyback_quantity_bot, mocker):
  bot, trade, _ = buyback_quantity_bot
  strategy = bot.strategy
  for version in ("v2", "v3", "v4"):
    mocker.patch.object(strategy, f"short_grind_entry_{version}", return_value=False)
  mocker.patch.object(strategy, "short_buyback_entry_v2", return_value=False)
  mocker.patch.object(strategy, "short_rebuy_entry_v3", return_value=False)
  mocker.patch.object(strategy, "_bad_trade_controller_derisk_hold", return_value=False)
  bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  bot.exchange.get_rates.return_value = (128.0, 128.0)
  trade.open_date = rescue.NOW - timedelta(days=5)
  trade.orders[0].order_date = trade.orders[0].order_filled_date = trade.open_date
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(AROOND_14=100.0, AROOND_14_15m=100.0, protections_short_global=True, enter_short=False)
  frame["BBL_20_2.0"] = 0.0
  strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
  return bot, trade


@pytest.mark.parametrize("rescue_case,version,level", STAGES, indirect=["rescue_case"])
@pytest.mark.parametrize(
  "quantity,gate,expected",
  [
    (0.046875, "ready", 0.046875),
    (0.09375, "ready", 0.09375),
    (0.046875, "below", None),
    (0.046875, "equal", None),
    (0.09375, "reserve", 0.05945312),
    (0.046875, "reserve-blocked", None),
    (0.046875, "disabled", None),
    (0.046875, "pending", None),
    (0.046875, "done", None),
    (0.046875, "no-loss", None),
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
  ],
)
def test_stage_exit_checks_current_value(stage_bot, version, level, quantity, gate, expected, caplog):
  bot, trade = stage_bot
  strategy = bot.strategy
  minimum = {"below": 6.25, "equal": 6.0}.get(gate, 5.0)
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  trade.set_custom_data("system_version", version)
  prefix = {"legacy": "grinding_v2"}.get(version, version)
  strategy.derisk_enable = gate != "disabled"
  for other in range(1, 5):
    setattr(strategy, f"{prefix}_derisk_level_{other}_enable", other == level)
  market = "futures" if trade.leverage > 1 else "spot"
  fraction = getattr(strategy, f"{prefix}_derisk_level_{level}_stake_{market}")
  first = trade.orders[0]
  first.filled = quantity / fraction
  first.amount = first.ft_amount = max(0.25, first.filled)
  first.remaining = first.amount - first.filled
  first.status = "canceled"
  first.price = first.average = first.ft_price = 128.0 if gate == "no-loss" else 100.0
  first.cost = first.filled * first.price
  trade.recalc_trade_from_orders()
  # Modeled filled history: a closed losing cycle, then unrelated inventory.
  # Realized loss can coexist with current price above the remaining basis.
  if gate != "no-loss":
    fill(trade, trade.entry_side, 4.0, 100.0, "grind_1_entry")
    fill(trade, trade.exit_side, 4.0, 120.0 if trade.is_short else 80.0, "grind_1_exit")
  fill(trade, trade.entry_side, 1.0, 128.0 if gate == "no-loss" else 100.0, trade.enter_tag)
  if gate in ("reserve", "reserve-blocked"):
    remainder = 0.12 if gate == "reserve" else 0.08
    fill(trade, trade.exit_side, trade.amount - remainder, 100.0, "exit_normal")
  if gate == "done":
    fill(trade, trade.exit_side, 0.0625, 100.0, f"derisk_level_{level}")
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, trade.enter_tag, 1.0, 0.0, "open")
  before = trade.amount
  if gate == "ready" and quantity == 0.046875:
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
  assert order.ft_order_tag == f"derisk_level_{level}"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(before - expected))) <= Decimal("0.00000001")
  assert trade.is_open


@pytest.mark.parametrize("rescue_case", MODES, indirect=True)
@pytest.mark.parametrize(
  "inventory,gate,expected",
  [
    (0.109375, "ready", 0.04882812),
    (0.1875, "ready", 0.12695312),
    (0.9375, "below", None),
    (0.99609375, "equal", None),
    (0.109375, "disabled", None),
    (0.109375, "pending", None),
    (0.109375, "no-stage", None),
    (0.109375, "no-loss", None),
  ],
  ids=["current-only", "both-values", "below", "equal", "disabled", "pending", "no-stage", "no-loss"],
)
def test_v2_global_exit_checks_current_value(stage_bot, inventory, gate, expected, caplog):
  bot, trade = stage_bot
  strategy = bot.strategy
  minimum = 50.0 if gate in ("below", "equal") else 5.0
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  trade.set_custom_data("system_version", "legacy")
  strategy.grinding_v2_derisk_global_enable = gate != "disabled"
  strategy.grinding_v2_grind_1_enable = False
  first = trade.orders[0]
  first.amount = first.ft_amount = first.filled = 0.25 if trade.is_short else 3.5
  first.price = first.average = first.ft_price = 140.0 if trade.is_short else 10.0
  first.cost = 35.0
  trade.recalc_trade_from_orders()
  prior_tag = "exit_normal" if gate == "no-stage" else "derisk_level_1"
  fill(trade, trade.exit_side, first.filled * 0.2, 168.0 if trade.is_short else 8.0, prior_tag)
  fill(trade, trade.exit_side, trade.amount - 0.0625, 140.0 if trade.is_short else 160.0, "exit_normal")
  entry_price = 48.0 if trade.is_short else 208.0
  if gate == "no-loss":
    entry_price = 128.0
  fill(trade, trade.entry_side, 1.0, entry_price, "grind_1_entry", inventory - 0.0625)
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, "grind_1_entry", 1.0, 0.0, "open")
  before = trade.amount
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
  assert order.ft_order_tag == "derisk_global"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal("0.060546875")) <= Decimal("0.00000001")
  assert trade.is_open
