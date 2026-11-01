from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import State
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_partial_exit as partial


partial_exit_case = partial.partial_exit_case


@pytest.fixture
def partial_bot(partial_exit_case, mocker):
  strategy, trade = partial_exit_case
  strategy.config.update(
    dry_run=True,
    dry_run_wallet=10000.0,
    tradable_balance_ratio=1.0,
    trading_mode=trade.trading_mode,
  )
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = trade.trading_mode
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0 / trade.leverage
  bot.exchange.get_max_pair_stake_amount.return_value = 10000.0
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: round(amount, 8)
  bot.exchange.get_funding_fees.return_value = 0.0

  def create_order(**kwargs):
    return {
      "id": "minimum-retry",
      "symbol": trade.pair,
      "type": "limit",
      "side": kwargs["side"],
      "status": "open",
      "price": kwargs["rate"],
      "amount": kwargs["amount"],
      "filled": 0.0,
      "remaining": kwargs["amount"],
      "cost": 0.0,
      "timestamp": int(partial.NOW.timestamp() * 1000),
    }

  bot.exchange.create_order.side_effect = create_order
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_exit = MagicMock()
  bot.execute_entry = MagicMock()
  mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now.return_value = partial.NOW
  return bot


@pytest.mark.parametrize(
  "requested,remainder,rate,eligible",
  [
    (4.0, 0.04, 128.0, True),
    (4.0, 0.046875, 128.0, True),
    (4.0, 0.06, 128.0, True),
    (4.0, 0.02, 128.0, False),
    (4.0, 0.0625, 80.0, False),
    (14.0, 0.046875, 128.0, True),
  ],
  ids=["current-value-only", "binary-current-value", "both-values", "below-minimum", "exact-minimum", "full-close"],
)
def test_engine_retries_using_current_value_minimum(
  partial_bot, partial_exit_case, requested, remainder, rate, eligible
):
  _, trade = partial_exit_case
  if trade.leverage > 1:
    trade.liquidation_price = 132.0 if trade.is_short else 68.0
  tag = "derisk_global" if requested == 14.0 else f"grind_1_exit {trade.orders[1].id}"
  partial.add_order(trade, trade.exit_side, tag, requested, requested - remainder, "canceled", price=rate)
  partial_bot.exchange.get_rates.return_value = (rate, rate)

  partial_bot.check_and_call_adjust_trade_position(trade)

  partial_bot.execute_entry.assert_not_called()
  if not eligible:
    partial_bot.exchange.create_order.assert_not_called()
    assert trade.orders[-1].status == "canceled"
    return
  partial_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.amount == pytest.approx(remainder)
  assert order.ft_order_tag == tag
  assert order.ft_is_open
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
      "timestamp": int(partial.NOW.timestamp() * 1000),
      "lastTradeTimestamp": int(partial.NOW.timestamp() * 1000),
    }
  )
  trade.update_trade(order)
  if requested == 14.0:
    assert not trade.is_open
  else:
    assert trade.amount == pytest.approx(10.0)
