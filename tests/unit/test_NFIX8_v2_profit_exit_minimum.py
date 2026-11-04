"""V2 first managed exits use current order value, not converted callback stake."""

from decimal import Decimal

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_liquidation_rescue as rescue


rescue_case = rescue.rescue_case
buyback_quantity_bot = buyback.buyback_quantity_bot


@pytest.mark.parametrize("rescue_case", [(False, 1), (False, 3), (True, 3)], indirect=True)
@pytest.mark.parametrize("kind,level", [("grind", n) for n in range(1, 6)] + [("buyback", n) for n in range(1, 4)])
@pytest.mark.parametrize(
  "reason,filled,minimum,gate,expected",
  [
    ("exit", 0.046875, 5.0, "ready", 0.046875),
    ("exit", 0.0625, 5.0, "ready", 0.0625),
    ("exit", 0.03125, 5.0, "ready", None),
    ("exit", 0.0390625, 5.0, "ready", None),
    ("exit", 10.0, 640.0, "ready", 7.25),
    ("exit", 0.046875, 5.0, "pending", None),
    ("exit", 0.046875, 5.0, "indicator", None),
    ("derisk", 0.046875, 5.0, "ready", 0.046875),
    ("derisk", 0.0625, 5.0, "ready", 0.0625),
    ("derisk", 0.03125, 5.0, "ready", None),
    ("derisk", 0.0390625, 5.0, "ready", None),
    ("derisk", 0.1, 5.0, "reserve", 0.05945312),
    ("derisk", 0.046875, 5.0, "pending", None),
    ("derisk", 0.046875, 5.0, "disabled", None),
    ("derisk", 0.046875, 5.0, "no-loss", None),
    ("derisk", 0.046875, 5.0, "fees", 0.046875),
  ],
  ids=[
    "profit-current-only",
    "profit-both",
    "profit-below",
    "profit-equal",
    "profit-reserve",
    "profit-pending",
    "profit-indicator",
    "derisk-current-only",
    "derisk-both",
    "derisk-below",
    "derisk-equal",
    "derisk-reserve",
    "derisk-pending",
    "derisk-disabled",
    "derisk-no-loss",
    "derisk-fees",
  ],
)
def test_v2_first_managed_exit_uses_current_value(
  buyback_quantity_bot, mocker, caplog, kind, level, reason, filled, minimum, gate, expected
):
  bot, trade, _ = buyback_quantity_bot
  trade.set_custom_data("system_version", None)
  trade.fee_open = trade.fee_close = 0.001 if gate == "fees" else 0.0
  for entry_kind in ("grind", "buyback"):
    mocker.patch.object(bot.strategy, f"short_{entry_kind}_entry_v2", return_value=False)
  is_derisk = reason == "derisk"
  if is_derisk:
    # First-entry stake sets the unchanged loss threshold independently of total inventory.
    first = trade.orders[0]
    first.amount = first.ft_amount = first.filled = 0.05
    first.cost = 5.0
    trade.recalc_trade_from_orders()
    if gate == "reserve":
      rescue.add_order(trade, trade.exit_side, "exit_normal", 0.03)
    else:
      rescue.add_order(trade, trade.entry_side, trade.enter_tag, 0.95)
    setattr(bot.strategy, f"grinding_v2_{kind}_{level}_use_derisk", gate != "disabled")
  else:
    rescue.add_order(trade, trade.exit_side, "exit_normal", 5.0)
  entry = rescue.add_order(trade, trade.entry_side, f"{kind}_{level}_entry", max(1.0, filled), filled, "canceled")
  entry.price = entry.average = entry.ft_price = 200.0 if trade.is_short else 100.0
  if is_derisk:
    entry.price = entry.average = entry.ft_price = (100.0 if gate == "reserve" else 80.0) if trade.is_short else 200.0
    if gate == "no-loss":
      entry.price = entry.average = entry.ft_price = 128.0
  entry.cost = filled * entry.price
  trade.recalc_trade_from_orders()
  initial_amount = trade.amount
  frame, _ = bot.strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(
    RSI_3=0.0 if trade.is_short else 100.0,
    AROOND_14=100.0,
    AROOND_14_15m=100.0,
    protections_short_global=True,
    enter_short=False,
  )
  frame["BBL_20_2.0"] = 0.0
  if gate == "indicator":
    frame = frame.assign(RSI_3=50.0)
  bot.strategy.dp._set_cached_df(trade.pair, "5m", frame, bot.strategy.config["candle_type_def"])
  if gate == "pending":
    rescue.add_order(trade, trade.entry_side, f"{kind}_{level}_entry", 1.0, 0.0, "open")
  bot.exchange.get_min_pair_stake_amount.return_value = minimum / trade.leverage
  bot.exchange.get_rates.return_value = (128.0, 128.0)

  bot.check_and_call_adjust_trade_position(trade)

  assert all(record.levelno < 40 for record in caplog.records)
  bot.execute_entry.assert_not_called()
  if expected is None:
    bot.exchange.create_order.assert_not_called()
    assert trade.amount == initial_amount
    return
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == f"{kind}_{level}_{reason} {entry.id}"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  buyback.settle_exit(trade, order, order.amount)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(initial_amount - expected))) <= Decimal("0.00000001")
