from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import State
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFI_rebuy_margin as rebuy_tests


NOW = rebuy_tests.NOW
rebuy_case = rebuy_tests.rebuy_case
rebuy_system = rebuy_tests.rebuy_system


@pytest.mark.parametrize(
  "funding_ratio,exchange_ratio,derisk_enabled,rebuy_signal",
  [
    (0.0, 100.0, True, True),
    (0.999, 100.0, True, True),
    (1.0, 100.0, True, True),
    (1.25, 100.0, True, True),
    (2.999, 100.0, True, True),
    (3.0, 100.0, True, True),
    (0.0, 100.0, False, True),
    (1.25, 100.0, False, True),
    (1.25, 0.5, True, True),
    (0.0, 100.0, True, False),
  ],
  ids=[
    "empty",
    "below-margin",
    "exact-margin",
    "funded-500",
    "below-old-limit",
    "old-limit",
    "disabled-empty",
    "disabled-funded",
    "exchange-limit",
    "native-derisk",
  ],
)
def test_engine_preserves_rebuy_and_derisk_routing(
  rebuy_case, mocker, funding_ratio, exchange_ratio, derisk_enabled, rebuy_signal
):
  strategy, trade, rate, dataframe = rebuy_case
  rebuy_margin = 1200.0 / trade.leverage
  free_stake = rebuy_margin * funding_ratio
  exchange_limit = rebuy_margin * exchange_ratio
  affordable = min(free_stake, exchange_limit) >= rebuy_margin
  expected = "entry" if affordable and rebuy_signal else None
  if rebuy_signal:
    # Exercise affordability without assuming a rebuy/de-risk priority.
    rate = 125.0 if trade.is_short else 79.0
  else:
    dataframe["RSI_3"] = 100.0 if trade.is_short else 0.0
    if derisk_enabled:
      expected = "exit"
  strategy.derisk_enable = derisk_enabled
  strategy.config.update(
    dry_run=True,
    dry_run_wallet=trade.stake_amount + free_stake,
    tradable_balance_ratio=1.0,
    trading_mode=trade.trading_mode,
  )
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = trade.trading_mode
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  # Replace external exchange/RPC boundaries, not wallet or adjustment logic.
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_rates.return_value = (rate, rate)
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0
  bot.exchange.get_max_pair_stake_amount.return_value = exchange_limit
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: round(amount, 8)
  bot.exchange.get_funding_fees.return_value = 0.0
  bot.exchange.create_order.return_value = {
    "id": "derisk-exit",
    "symbol": trade.pair,
    "type": "limit",
    "side": trade.exit_side,
    "status": "open",
    "price": rate,
    "amount": trade.amount - 7.75 * trade.leverage / rate,
    "filled": 0.0,
    "remaining": trade.amount - 7.75 * trade.leverage / rate,
    "cost": 0.0,
    "timestamp": int(NOW.timestamp() * 1000),
  }
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_exit = MagicMock()
  bot.execute_entry = MagicMock()
  mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now.return_value = NOW
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  assert bot.wallets.get_available_stake_amount() == pytest.approx(free_stake)

  bot.check_and_call_adjust_trade_position(trade)

  # The engine supplies the real wallet limit without multiplying by leverage.
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(min(free_stake, exchange_limit))
  if expected == "exit":
    bot.execute_entry.assert_not_called()
    bot.exchange.create_order.assert_called_once()
    order_args = bot.exchange.create_order.call_args.kwargs
    assert order_args["side"] == trade.exit_side
    assert order_args["reduceOnly"] == (trade.leverage > 1)
    assert order_args["amount"] == pytest.approx(trade.amount - 7.75 * trade.leverage / rate)
    assert trade.orders[-1].ft_order_tag == "derisk_level_3"
    assert trade.orders[-1].ft_is_open
  elif expected == "entry":
    bot.execute_entry.assert_called_once_with(
      trade.pair,
      1200.0 / trade.leverage,
      price=rate,
      trade=trade,
      is_short=trade.is_short,
      mode="pos_adjust",
      enter_tag="r",
    )
    bot.exchange.create_order.assert_not_called()
  else:
    bot.execute_entry.assert_not_called()
    bot.exchange.create_order.assert_not_called()
