"""V4 spot reductions must not sell entry fees out of the initial position."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import MarginMode, State
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_v4_grind_funding as funding


NOW = funding.NOW
level = funding.level
v4_case = funding.v4_case


@pytest.fixture
def quantity_bot(v4_case, mocker):
  strategy, trade, _ = v4_case
  strategy.long_grind_entry_v4 = MagicMock(return_value=False)
  strategy.dp.send_msg = MagicMock()
  strategy.config.update(
    dry_run=True, dry_run_wallet=10000.0, tradable_balance_ratio=1.0, trading_mode=trade.trading_mode
  )
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = trade.trading_mode
  bot.margin_mode = MarginMode.NONE
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0
  bot.exchange.get_max_pair_stake_amount.return_value = 100000.0
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: round(amount, 8)
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
  frame = frame.assign(close=rate, RSI_3=100.0, WILLR_14=-50.0, STOCHRSIk_14_14_3_3=50.0)
  frame["BBU_20_2.0"] = rate * 2.0
  bot.strategy.dp._set_cached_df(trade.pair, "5m", frame, bot.config["candle_type_def"])


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("fee", [0.0, 0.001], ids=["no-base-fee", "base-fee"])
@pytest.mark.parametrize("reason,rate", [("exit", 110.0), ("derisk", 86.0)])
def test_grind_reduction_preserves_initial_inventory(quantity_bot, v4_case, level, fee, reason, rate):
  _, trade, _ = v4_case
  settle_base_fee(quantity_bot, trade, trade.orders[-1], fee)
  set_rate(quantity_bot, trade, rate)

  quantity_bot.check_and_call_adjust_trade_position(trade)

  quantity_bot.execute_entry.assert_not_called()
  quantity_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag.startswith(f"grind_{level}_{reason} ")
  assert order.amount == pytest.approx(1.0 - fee, abs=1e-8)
  order.status = "closed"
  order.ft_is_open = False
  order.filled = order.amount
  order.remaining = 0.0
  order.average = rate
  order.cost = order.filled * rate
  order.order_filled_date = NOW
  trade.update_trade(order)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 110.0), ("derisk", 86.0)])
def test_canceled_partial_reduction_retries_only_net_remainder(quantity_bot, v4_case, level, reason, rate):
  _, trade, _ = v4_case
  settle_base_fee(quantity_bot, trade, trade.orders[-1], 0.001)
  set_rate(quantity_bot, trade, rate)
  quantity_bot.check_and_call_adjust_trade_position(trade)
  first = trade.orders[-1]
  first.status = "canceled"
  first.ft_is_open = False
  first.filled = 0.4
  first.remaining = first.amount - first.filled
  first.average = rate
  first.cost = first.filled * rate
  first.order_filled_date = NOW
  trade.update_trade(first)
  set_rate(quantity_bot, trade, rate + 1.0)

  quantity_bot.check_and_call_adjust_trade_position(trade)

  retry = trade.orders[-1]
  assert retry is not first
  assert retry.ft_order_tag == first.ft_order_tag
  assert retry.ft_order_tag.startswith(f"grind_{level}_{reason} ")
  assert retry.amount == pytest.approx(0.599, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_base_fee_reduction_keeps_existing_minimum_remainder(quantity_bot, v4_case, level):
  _, trade, _ = v4_case
  previous_exit = trade.orders[1]
  previous_exit.amount = previous_exit.ft_amount = previous_exit.filled = 9.99
  previous_exit.cost = 999.0
  trade.recalc_trade_from_orders()
  settle_base_fee(quantity_bot, trade, trade.orders[-1], 0.001)
  set_rate(quantity_bot, trade, 110.0)

  quantity_bot.check_and_call_adjust_trade_position(trade)

  order = trade.orders[-1]
  assert order.ft_order_tag.startswith(f"grind_{level}_exit ")
  expected = 1.009 - 5.0 * 1.55 / 110.0
  assert order.amount == pytest.approx(expected, abs=1e-8)
  assert order.amount < 0.999


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_unequal_price_fills_keep_raw_profit_and_derisk_boundaries(quantity_bot, v4_case, level):
  strategy, trade, _ = v4_case
  settle_base_fee(quantity_bot, trade, trade.orders[-1], 0.001)
  funding.fill(trade, trade.entry_side, 1.0, 200.0, f"grind_{level}_entry")
  settle_base_fee(quantity_bot, trade, trade.orders[-1], 0.001)
  # Gross-fill weighted price remains150, not300/1.998 after the base fee.
  set_rate(quantity_bot, trade, 135.01)
  quantity_bot.check_and_call_adjust_trade_position(trade)
  quantity_bot.exchange.create_order.assert_not_called()
  threshold = getattr(strategy, f"system_v4_grind_{level}_profit_threshold_spot")
  set_rate(quantity_bot, trade, 150.0 * (1.0 + threshold + trade.fee_open + trade.fee_close) + 0.01)

  quantity_bot.check_and_call_adjust_trade_position(trade)

  order = trade.orders[-1]
  assert order.ft_order_tag.startswith(f"grind_{level}_exit ")
  assert order.amount == pytest.approx(1.998, abs=1e-8)
