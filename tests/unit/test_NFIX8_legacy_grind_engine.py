from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import State
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_legacy_grind_funding as funding_tests


NOW = funding_tests.NOW
legacy_grind_case = funding_tests.legacy_grind_case


@pytest.mark.parametrize(
  "funding_ratio,exchange_ratio",
  [(0.0, 100.0), (0.999, 100.0), (1.25, 100.0), (10.0, 1.0), (10.0, 0.999)],
  ids=["empty", "below-wallet", "funded", "exact-exchange", "below-exchange"],
)
@pytest.mark.parametrize("entry_signal", [False, True])
def test_engine_reaches_stop_when_addition_cannot_execute(
  legacy_grind_case, mocker, funding_ratio, exchange_ratio, entry_signal
):
  strategy, trade, rate = legacy_grind_case
  funding_tests.set_signal(strategy, entry_signal)
  entry_stake = 140.0 / trade.leverage
  free_stake = entry_stake * funding_ratio
  exchange_limit = entry_stake * exchange_ratio
  strategy.config.update(
    dry_run=True,
    dry_run_wallet=trade.stake_amount - trade.realized_profit + free_stake,
    tradable_balance_ratio=1.0,
    trading_mode=trade.trading_mode,
  )
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = trade.trading_mode
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  # Replace only external exchange/RPC boundaries; use actual wallet and order logic.
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_rates.return_value = (rate, rate)
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0
  bot.exchange.get_max_pair_stake_amount.return_value = exchange_limit
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: round(amount, 8)
  bot.exchange.get_funding_fees.return_value = 0.0

  def create_order(**kwargs):
    return {
      "id": "legacy-grind-stop",
      "symbol": trade.pair,
      "type": "limit",
      "side": kwargs["side"],
      "status": "open",
      "price": kwargs["rate"],
      "amount": kwargs["amount"],
      "filled": 0.0,
      "remaining": kwargs["amount"],
      "cost": 0.0,
      "timestamp": int(NOW.timestamp() * 1000),
    }

  bot.exchange.create_order.side_effect = create_order
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_exit = MagicMock()
  bot.execute_entry = MagicMock()
  mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now.return_value = NOW
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  assert bot.wallets.get_available_stake_amount() == pytest.approx(free_stake)

  bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(min(free_stake, exchange_limit))
  if entry_signal and min(funding_ratio, exchange_ratio) >= 1.0:
    bot.execute_entry.assert_called_once_with(
      trade.pair,
      entry_stake,
      price=rate,
      trade=trade,
      is_short=trade.is_short,
      mode="pos_adjust",
      enter_tag="gd1",
    )
    bot.exchange.create_order.assert_not_called()
  else:
    bot.execute_entry.assert_not_called()
    bot.exchange.create_order.assert_called_once()
    order_args = bot.exchange.create_order.call_args.kwargs
    stake, tag = funding_tests.expected_stop(trade, rate)
    expected_quantity = -stake * trade.amount / trade.stake_amount
    assert order_args["side"] == trade.exit_side
    assert order_args["reduceOnly"] == (trade.leverage > 1)
    assert order_args["amount"] == pytest.approx(expected_quantity)
    assert trade.orders[-1].ft_order_tag == tag
    assert trade.orders[-1].ft_is_open
