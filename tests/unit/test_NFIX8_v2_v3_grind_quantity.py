"""Older-system exits must preserve inventory outside a fee-bearing grind."""

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import MarginMode
from freqtrade.exchange import amount_to_contract_precision

from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


level = funding.level
v4_case = funding.v4_case
quantity_bot = quantity.quantity_bot


@pytest.fixture(params=[None, "system_v3_2"], ids=["v2", "v3"])
def system_version(request):
  return request.param


@pytest.fixture
def older_grind_bot(quantity_bot, v4_case, level, system_version):
  strategy, trade, _ = v4_case
  trade.set_custom_data("system_version", system_version)
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  strategy.long_grind_entry_v3 = MagicMock(return_value=False)
  strategy.long_buyback_entry_v2 = MagicMock(return_value=False)
  strategy.long_buyback_entry_v3 = MagicMock(return_value=False)
  strategy.long_rebuy_entry_v3 = MagicMock(return_value=False)
  funding.fill(trade, trade.entry_side, 9.0, 100.0, f"grind_{level}_entry")
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(RSI_3_1h=50.0, AROONU_14_15m=100.0)
  strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
  quantity_bot.margin_mode = MarginMode.ISOLATED if strategy.is_futures_mode else MarginMode.NONE
  quantity_bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  return quantity_bot


@pytest.mark.parametrize(
  "v4_case,fee_ratio",
  [((False, 1), 0.0), ((False, 1), 0.001), ((False, 3), 0.0)],
  indirect=["v4_case"],
  ids=["spot-no-base-fee", "spot-base-fee", "futures-no-base-fee"],
)
@pytest.mark.parametrize("reason,rate", [("exit", 120.0), ("derisk", 70.0)])
def test_older_grind_exit_preserves_initial_inventory(older_grind_bot, v4_case, level, fee_ratio, reason, rate):
  _, trade, _ = v4_case
  entries = [order for order in trade.orders if order.ft_order_tag == f"grind_{level}_entry"]
  for entry in entries:
    quantity.settle_base_fee(older_grind_bot, trade, entry, entry.safe_filled * fee_ratio)
  assert trade.amount == pytest.approx(16.0 - 10.0 * fee_ratio, rel=0, abs=1e-8)
  quantity.set_rate(older_grind_bot, trade, rate)

  older_grind_bot.check_and_call_adjust_trade_position(trade)

  older_grind_bot.execute_entry.assert_not_called()
  older_grind_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_{level}_{reason} " + " ".join(str(entry.id) for entry in reversed(entries))
  expected_quantity = 10.0 * (1.0 - fee_ratio)
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected_quantity))) <= Decimal("0.00000001")
  order.update_from_ccxt_object(
    {
      "id": order.order_id,
      "status": "closed",
      "amount": order.amount,
      "filled": order.amount,
      "remaining": 0.0,
      "price": rate,
      "average": rate,
      "cost": order.amount * rate,
      "timestamp": int(funding.NOW.timestamp() * 1000),
      "lastTradeTimestamp": int(funding.NOW.timestamp() * 1000),
    }
  )
  trade.update_trade(order)
  assert abs(Decimal(str(trade.amount)) - Decimal("6")) <= Decimal("0.00000001")


@pytest.mark.parametrize("v4_case", [(False, 1)], indirect=True)
def test_older_grind_keeps_minimum_reserve(older_grind_bot, v4_case, level):
  _, trade, _ = v4_case
  prior_exit = trade.orders[1]
  prior_exit.amount = prior_exit.ft_amount = prior_exit.filled = 9.99
  prior_exit.cost = 999.0
  trade.recalc_trade_from_orders()
  for entry in trade.orders:
    if entry.ft_order_tag == f"grind_{level}_entry":
      quantity.settle_base_fee(older_grind_bot, trade, entry, entry.safe_filled * 0.001)
  quantity.set_rate(older_grind_bot, trade, 120.0)

  older_grind_bot.check_and_call_adjust_trade_position(trade)

  older_grind_bot.execute_entry.assert_not_called()
  older_grind_bot.exchange.create_order.assert_called_once()
  expected_quantity = 10.0 - 5.0 * 1.55 / 120.0
  order = trade.orders[-1]
  assert order.ft_order_tag.startswith(f"grind_{level}_exit ")
  assert abs(Decimal(str(order.amount)) - Decimal(str(expected_quantity))) <= Decimal("0.00000001")
  assert order.amount < 9.99


@pytest.mark.parametrize("v4_case", [(False, 1)], indirect=True)
def test_older_grind_keeps_gross_weighted_price(older_grind_bot, v4_case, level, system_version):
  strategy, trade, _ = v4_case
  last_entry = trade.orders[-1]
  last_entry.price = last_entry.average = last_entry.ft_price = 200.0
  last_entry.cost = 1800.0
  trade.recalc_trade_from_orders()
  for entry in trade.orders:
    if entry.ft_order_tag == f"grind_{level}_entry":
      quantity.settle_base_fee(older_grind_bot, trade, entry, entry.safe_filled * 0.001)
  prefix = "grinding_v2" if system_version is None else "system_v3"
  threshold = getattr(strategy, f"{prefix}_grind_{level}_profit_threshold_spot")
  rate = 190.0 * (1.0 + threshold + trade.fee_open + trade.fee_close) + 0.000001
  quantity.set_rate(older_grind_bot, trade, rate)

  older_grind_bot.check_and_call_adjust_trade_position(trade)

  older_grind_bot.execute_entry.assert_not_called()
  older_grind_bot.exchange.create_order.assert_called_once()
  assert trade.orders[-1].ft_order_tag.startswith(f"grind_{level}_exit ")
