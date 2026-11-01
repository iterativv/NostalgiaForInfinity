"""Legacy spot exits preserve inventory outside their fee-bearing queue."""

from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import MarginMode, State
from freqtrade.exchange import amount_to_contract_precision
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import Trade
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_legacy_grind_funding as funding


NOW = funding.NOW
legacy_grind_case = funding.legacy_grind_case


@pytest.fixture
def quantity_bot(legacy_grind_case, mocker):
  strategy, trade, _ = legacy_grind_case
  funding.set_signal(strategy, False)
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  strategy.dp.send_msg = MagicMock()
  strategy.config.update(
    dry_run=True, dry_run_wallet=10000.0, tradable_balance_ratio=1.0, trading_mode=trade.trading_mode
  )
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = trade.trading_mode
  bot.margin_mode = MarginMode.ISOLATED if strategy.is_futures_mode else MarginMode.NONE
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0
  bot.exchange.get_max_pair_stake_amount.return_value = 100000.0
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  bot.exchange.get_funding_fees.return_value = 0.0
  bot.exchange.get_liquidation_price.return_value = None
  bot.exchange.check_order_canceled_empty.return_value = False
  bot.exchange.order_has_fee.return_value = True
  bot.exchange.extract_cost_curr_rate.side_effect = lambda fee, pair, cost, amount: (
    fee["cost"],
    fee["currency"],
    fee["rate"],
  )
  bot.exchange.create_order.side_effect = lambda **kw: {
    "id": f"reduction-{len(trade.orders)}",
    "symbol": trade.pair,
    "type": "limit",
    "side": kw["side"],
    "status": "open",
    "price": kw["rate"],
    "amount": kw["amount"],
    "filled": 0.0,
    "remaining": kw["amount"],
    "cost": 0.0,
    "timestamp": int(NOW.timestamp() * 1000),
  }
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_enter = MagicMock()
  bot._notify_exit = MagicMock()
  bot.execute_entry = MagicMock()
  mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now.return_value = NOW
  return bot


def settle_base_fee(bot, trade, order, fee):
  payload = {
    "id": order.order_id,
    "symbol": trade.pair,
    "type": "limit",
    "side": trade.entry_side,
    "status": order.status,
    "price": order.safe_price,
    "average": order.safe_price,
    "amount": order.amount,
    "filled": order.safe_filled,
    "remaining": order.safe_remaining,
    "cost": order.cost,
    "timestamp": int(order.order_date_utc.timestamp() * 1000),
    "fee": {"cost": fee, "currency": "ETH", "rate": fee / order.safe_filled},
  }
  bot.update_trade_state(trade, order.order_id, action_order=payload, send_msg=True)
  if not trade.fee_updated(trade.entry_side):
    bot.update_trade_state(trade, order.order_id, action_order=payload, send_msg=False)
  assert order.safe_fee_base == fee


def set_rate(bot, trade, rate):
  bot.exchange.get_rates.return_value = (rate, rate)
  frame, _ = bot.strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(close=rate)
  bot.strategy.dp._set_cached_df(trade.pair, "5m", frame, bot.config["candle_type_def"])


@pytest.mark.parametrize(
  "legacy_grind_case,fee_ratio",
  [((False, 1), 0.0), ((False, 1), 0.001), ((False, 3), 0.0), ((True, 3), 0.0)],
  indirect=["legacy_grind_case"],
  ids=["spot-no-base-fee", "spot-base-fee", "long-futures", "short-futures"],
)
@pytest.mark.parametrize(
  "entry_tag,stop_tag", [(f"gd{n}", f"dd{n}") for n in range(1, 7)] + [("dl1", "ddl1"), ("dl2", "ddl2")]
)
@pytest.mark.parametrize("minimum", [0.0, 5.0], ids=["no-minimum", "minimum"])
@pytest.mark.parametrize("reason", ["profit", "stop"])
def test_legacy_exit_preserves_inventory_outside_queue(
  quantity_bot, legacy_grind_case, fee_ratio, entry_tag, stop_tag, minimum, reason
):
  _, trade, stop_rate = legacy_grind_case
  if entry_tag in ("dl1", "dl2"):
    history = [
      (order.ft_order_side, order.safe_filled, order.safe_price, order.ft_order_tag) for order in trade.orders
    ]
    for order in list(trade.orders):
      Trade.session.delete(order)
    trade.orders.clear()
    Trade.session.flush()
    # Model both a completed initial exit and the preceding de-risk for dl queues.
    for side, amount, price, tag in history:
      if tag == "gm0":
        funding.fill(trade, side, amount / 2.0, price, "gm0")
        funding.fill(trade, side, amount / 2.0, price, "d")
      else:
        funding.fill(trade, side, amount, price, tag)
  entries = [order for order in trade.orders if order.ft_order_tag == "gd1"]
  gross_quantity = sum(order.safe_filled for order in entries)
  owner_quantity = trade.amount - gross_quantity
  fee_quantity = gross_quantity * fee_ratio
  # Reuse the real fills for each supported persisted queue tag.
  for entry in entries:
    entry.ft_order_tag = entry_tag
    settle_base_fee(quantity_bot, trade, entry, entry.safe_filled * fee_ratio)
  assert trade.amount == pytest.approx(owner_quantity + gross_quantity - fee_quantity, rel=0, abs=1e-8)
  profit_rate = 80.0 if trade.is_short else 120.0
  rate = profit_rate if reason == "profit" else stop_rate
  set_rate(quantity_bot, trade, rate)
  quantity_bot.exchange.get_min_pair_stake_amount.return_value = minimum
  bot_minimum = max(minimum, 5.0 / trade.leverage) if trade.leverage > 1 else minimum
  expected_quantity = min(gross_quantity - fee_quantity, trade.amount - bot_minimum * 1.55 * trade.leverage / rate)
  before_quantity = trade.amount

  quantity_bot.check_and_call_adjust_trade_position(trade)

  quantity_bot.execute_entry.assert_not_called()
  quantity_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  prefix = entry_tag if reason == "profit" else stop_tag
  assert order.ft_order_tag == prefix + " " + " ".join(str(entry.id) for entry in reversed(entries))
  quantity_error = Decimal(str(order.amount)) - Decimal(str(expected_quantity))
  assert abs(quantity_error) <= Decimal("0.00000001")
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
      "timestamp": int(NOW.timestamp() * 1000),
      "lastTradeTimestamp": int(NOW.timestamp() * 1000),
    }
  )
  trade.update_trade(order)
  expected_remaining = Decimal(str(before_quantity)) - Decimal(str(expected_quantity))
  assert abs(Decimal(str(trade.amount)) - expected_remaining) <= Decimal("0.00000001")


@pytest.mark.parametrize("legacy_grind_case", [(False, 1)], indirect=True)
@pytest.mark.parametrize("entry_tag", ["gd1", "gd6"])
def test_legacy_partial_exit_retries_only_requested_net_remainder(quantity_bot, legacy_grind_case, entry_tag):
  _, trade, _ = legacy_grind_case
  entries = [order for order in trade.orders if order.ft_order_tag == "gd1"]
  net_quantity = sum(order.safe_filled for order in entries) * 0.999
  for entry in entries:
    entry.ft_order_tag = entry_tag
    settle_base_fee(quantity_bot, trade, entry, entry.safe_filled * 0.001)
  set_rate(quantity_bot, trade, 120.0)
  quantity_bot.check_and_call_adjust_trade_position(trade)
  first = trade.orders[-1]
  assert abs(Decimal(str(first.amount)) - Decimal(str(net_quantity))) <= Decimal("0.00000001")
  first.update_from_ccxt_object(
    {
      "id": first.order_id,
      "status": "canceled",
      "amount": first.amount,
      "filled": 0.4,
      "remaining": first.amount - 0.4,
      "price": 120.0,
      "average": 120.0,
      "cost": 48.0,
      "timestamp": int(NOW.timestamp() * 1000),
      "lastTradeTimestamp": int(NOW.timestamp() * 1000),
    }
  )
  trade.update_trade(first)
  quantity_bot.exchange.create_order.reset_mock()
  set_rate(quantity_bot, trade, 121.0)

  quantity_bot.check_and_call_adjust_trade_position(trade)

  quantity_bot.execute_entry.assert_not_called()
  quantity_bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry is not first
  assert retry.ft_order_tag == first.ft_order_tag
  quantity_error = Decimal(str(retry.amount)) - Decimal(str(first.safe_remaining))
  assert abs(quantity_error) <= Decimal("0.00000001")


@pytest.mark.parametrize("legacy_grind_case", [(False, 1)], indirect=True)
@pytest.mark.parametrize(
  "entry_tag,threshold_name",
  [
    ("gd1", "grind_1_profit_threshold_spot"),
    ("gd5", "grind_5_profit_threshold_spot"),
    ("", "grind_1_profit_threshold_spot"),
  ],
)
def test_base_fee_keeps_raw_weighted_profit_boundary(quantity_bot, legacy_grind_case, entry_tag, threshold_name):
  strategy, trade, _ = legacy_grind_case
  entries = [order for order in trade.orders if order.ft_order_tag == "gd1"]
  gross_quantity = sum(order.safe_filled for order in entries)
  raw_average = sum(order.safe_filled * order.safe_price for order in entries) / gross_quantity
  for entry in entries:
    entry.ft_order_tag = entry_tag
    settle_base_fee(quantity_bot, trade, entry, entry.safe_filled * 0.001)
  threshold = getattr(strategy, threshold_name) + trade.fee_open + trade.fee_close
  set_rate(quantity_bot, trade, raw_average * (1.0 + threshold) + 0.000001)

  quantity_bot.check_and_call_adjust_trade_position(trade)

  quantity_bot.execute_entry.assert_not_called()
  quantity_bot.exchange.create_order.assert_called_once()
  assert trade.orders[-1].ft_order_tag == (entry_tag or "gd1") + " " + " ".join(
    str(entry.id) for entry in reversed(entries)
  )
