"""First grind exits use current order value, not callback stake."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import MarginMode
from freqtrade.exchange import amount_to_contract_precision

from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


pytestmark = pytest.mark.parametrize(
  "v4_case",
  [(False, 1.0), (False, 3.0), (True, 3.0)],
  indirect=True,
  ids=["spot", "long-futures", "short-futures"],
)
v4_case = funding.v4_case
quantity_bot = quantity.quantity_bot


@pytest.fixture(params=[1, 5])
def level(request):
  return request.param


@pytest.fixture(params=["system_v3_2", "system_v4"])
def profit_exit_bot(request, quantity_bot, v4_case):
  strategy, trade, _ = v4_case
  trade.set_custom_data("system_version", request.param)
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  strategy.long_grind_entry_v3 = MagicMock(return_value=False)
  strategy.long_buyback_entry_v3 = MagicMock(return_value=False)
  strategy.long_rebuy_entry_v3 = MagicMock(return_value=False)
  strategy.short_grind_entry_v3 = MagicMock(return_value=False)
  strategy.short_grind_entry_v4 = MagicMock(return_value=False)
  strategy.short_rebuy_entry_v3 = MagicMock(return_value=False)
  quantity_bot.margin_mode = MarginMode.ISOLATED if strategy.is_futures_mode else MarginMode.NONE
  quantity_bot.exchange.get_min_pair_stake_amount.return_value = 5.0 / trade.leverage
  quantity_bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  quantity_bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  quantity.set_rate(quantity_bot, trade, 128.0)
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(RSI_3=0.0 if trade.is_short else 100.0, RSI_3_1h=50.0, AROONU_14_15m=100.0)
  frame["BBL_20_2.0"] = 64.0
  strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
  return quantity_bot


@pytest.mark.parametrize(
  "filled,initial_price,initial_remainder,eligible",
  [
    (0.046875, 100.0, 6.0, True),
    (0.125, 100.0, 6.0, True),
    (0.03125, 400.0, 6.0, False),
    (0.0390625, 100.0, 6.0, False),
    (0.046875, 100.0, 0.02, False),
  ],
  ids=["current-value-only", "both-values", "below-current-minimum", "exact-current-minimum", "reserve"],
)
def test_first_profit_exit_checks_current_order_value(
  profit_exit_bot, v4_case, level, mocker, filled, initial_price, initial_remainder, eligible
):
  strategy, trade, _ = v4_case
  initial, prior_exit, entry = trade.orders
  initial.price = initial.average = initial.ft_price = initial_price
  initial.cost = initial.filled * initial_price
  prior_exit.amount = prior_exit.ft_amount = prior_exit.filled = 10.0 - initial_remainder
  prior_exit.cost = prior_exit.filled * prior_exit.safe_price
  entry.amount = entry.ft_amount = 0.25
  entry.filled = filled
  entry.remaining = entry.amount - filled
  entry.price = entry.average = entry.ft_price = 200.0 if trade.is_short else 100.0
  entry.cost = filled * entry.safe_price
  entry.status = "canceled"
  trade.recalc_trade_from_orders()
  assert trade.amount == pytest.approx(initial_remainder + filled)
  if eligible:
    callback_stake = filled * trade.stake_amount / trade.amount
    assert (callback_stake < 5.0 / trade.leverage) == (filled == 0.046875)
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  profit_exit_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  profit_exit_bot.execute_entry.assert_not_called()
  if not eligible:
    profit_exit_bot.exchange.create_order.assert_not_called()
    return
  profit_exit_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == f"grind_{level}_exit {entry.id}"
  assert abs(Decimal(str(order.amount)) - Decimal(str(filled))) <= Decimal("0.00000001")
  order.update_from_ccxt_object(
    {
      "id": order.order_id,
      "status": "closed",
      "amount": order.amount,
      "filled": order.amount,
      "remaining": 0.0,
      "price": 128.0,
      "average": 128.0,
      "cost": order.amount * 128.0,
      "timestamp": int(funding.NOW.timestamp() * 1000),
      "lastTradeTimestamp": int(funding.NOW.timestamp() * 1000),
    }
  )
  trade.update_trade(order)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(initial_remainder))) <= Decimal("0.00000001")


@pytest.mark.parametrize("level", range(1, 6))
@pytest.mark.parametrize(
  "filled,gate,expected",
  [
    (0.046875, "ready", 0.046875),
    (0.125, "ready", 0.125),
    (0.03125, "ready", None),
    (0.0390625, "ready", None),
    (0.1, "reserve", 0.05945312),
    (0.046875, "pending", None),
    (0.046875, "disabled", None),
    (0.046875, "no-loss", None),
    (0.046875, "fees", 0.046875),
  ],
  ids=[
    "current-only",
    "both-values",
    "below-minimum",
    "exact-minimum",
    "reserve",
    "pending",
    "disabled",
    "no-loss",
    "fees",
  ],
)
def test_first_derisk_exit_checks_current_order_value(profit_exit_bot, v4_case, level, caplog, filled, gate, expected):
  strategy, trade, _ = v4_case
  system = "system_v4" if trade.get_custom_data("system_version") == "system_v4" else "system_v3"
  # Restore native thresholds; the shared funding fixture lowers V4's threshold.
  for mode in ("spot", "futures"):
    setting = f"{system}_grind_{level}_derisk_{mode}"
    setattr(strategy, setting, getattr(type(strategy), setting))
  setattr(strategy, f"{system}_grind_{level}_use_derisk", gate != "disabled")
  trade.fee_open = trade.fee_close = 0.001 if gate == "fees" else 0.0
  _, prior_exit, entry = trade.orders
  if gate == "reserve":
    prior_exit.amount = prior_exit.ft_amount = prior_exit.filled = 9.98
    prior_exit.cost = prior_exit.filled * prior_exit.safe_price
  entry.amount = entry.ft_amount = 0.25
  entry.filled = filled
  entry.remaining = entry.amount - filled
  entry.price = entry.average = entry.ft_price = 100.0 if trade.is_short else 200.0
  if gate == "no-loss":
    entry.price = entry.average = entry.ft_price = 128.0
  entry.cost = filled * entry.safe_price
  entry.status = "canceled"
  trade.recalc_trade_from_orders()
  before = trade.amount
  if gate == "pending":
    entry.status = "open"
    entry.ft_is_open = True

  profit_exit_bot.check_and_call_adjust_trade_position(trade)

  assert all(record.levelno < 40 for record in caplog.records)
  profit_exit_bot.execute_entry.assert_not_called()
  if expected is None:
    profit_exit_bot.exchange.create_order.assert_not_called()
    assert trade.amount == before
    return
  profit_exit_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == f"grind_{level}_derisk {entry.id}"
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected))) <= Decimal("0.00000001")
  order.update_from_ccxt_object(
    {
      "id": order.order_id,
      "status": "closed",
      "amount": order.amount,
      "filled": order.amount,
      "remaining": 0.0,
      "price": 128.0,
      "average": 128.0,
      "cost": order.amount * 128.0,
      "timestamp": int(funding.NOW.timestamp() * 1000),
      "lastTradeTimestamp": int(funding.NOW.timestamp() * 1000),
    }
  )
  trade.update_trade(order)
  assert abs(Decimal(str(trade.amount)) - Decimal(str(before - expected))) <= Decimal("0.00000001")
  assert trade.is_open
