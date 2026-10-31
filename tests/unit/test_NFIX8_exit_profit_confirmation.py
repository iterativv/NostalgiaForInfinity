import json
from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import ExitCheckTuple
from freqtrade.enums import ExitType
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_bad_trade_profit as profit_tests


NOW = profit_tests.NOW
profit_case = profit_tests.profit_case


@pytest.mark.parametrize("fee", [0.0, 0.001])
@pytest.mark.parametrize("partial_price,rate", [(110.0, 98.0), (90.0, 102.0), (None, 98.0)])
@pytest.mark.parametrize("profit_only", [False, True])
def test_engine_confirms_exit_using_realized_and_remaining_profit(
  profit_case, mocker, fee, partial_price, rate, profit_only
):
  strategy, trade = profit_case
  strategy.hold_support_enabled = False
  strategy.exit_profit_only = profit_only
  strategy.exit_profit_offset = 0.0
  trade.fee_open = trade.fee_close = fee
  profit_tests.fill(trade, True, 10.0, 100.0)
  if trade.is_short:
    rate = 200.0 - rate
    if partial_price is not None:
      partial_price = 200.0 - partial_price
  partial_amount = 0.0
  partial_value = 0.0
  if partial_price is not None:
    partial_amount = 1.0
    partial_value = partial_price
    profit_tests.fill(trade, False, partial_amount, partial_price)
  remaining_amount = 10.0 - partial_amount
  gross_profit = partial_value + remaining_amount * rate - 1000.0
  if trade.is_short:
    gross_profit = -gross_profit
  expected_profit = gross_profit - fee * (1000.0 + partial_value + remaining_amount * rate)
  assert trade.calculate_profit(rate).total_profit == pytest.approx(expected_profit)
  expected_allowed = not profit_only or expected_profit >= 0.0

  strategy.config.update(dry_run=True, dry_run_wallet=10000.0, trading_mode=trade.trading_mode)
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = trade.trading_mode
  bot._exit_reason_cache = {}
  # Keep the actual wallet, confirmation and order persistence; replace exchange/RPC I/O.
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_funding_fees.return_value = 0.0

  def create_order(**kwargs):
    return {
      "id": "profit-confirmation-exit",
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
  mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now.return_value = NOW
  confirmation = mocker.spy(strategy, "confirm_trade_exit")
  order_count = len(trade.orders)

  result = bot.execute_trade_exit(trade, rate, ExitCheckTuple(ExitType.CUSTOM_EXIT, "exit_fixture"))

  assert result is expected_allowed
  confirmation.assert_called_once()
  assert confirmation.call_args.kwargs["amount"] == pytest.approx(remaining_amount)
  assert confirmation.call_args.kwargs["rate"] == rate
  if expected_allowed:
    bot.exchange.create_order.assert_called_once()
    order_args = bot.exchange.create_order.call_args.kwargs
    assert order_args["side"] == trade.exit_side
    assert order_args["amount"] == pytest.approx(remaining_amount)
    assert order_args["reduceOnly"] == (trade.leverage > 1)
    assert len(trade.orders) == order_count + 1
    assert trade.orders[-1].ft_order_tag == "exit_fixture"
    assert trade.orders[-1].ft_is_open
  else:
    bot.exchange.create_order.assert_not_called()
    assert len(trade.orders) == order_count


@pytest.mark.parametrize("offset_delta", [-0.0001, 0.0, 0.0001])
def test_profit_offset_keeps_current_stake_basis_and_inclusive_boundary(profit_case, offset_delta):
  strategy, trade = profit_case
  strategy.hold_support_enabled = False
  strategy.exit_profit_only = True
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 5.0, 98.0 if trade.is_short else 102.0)
  assert trade.realized_profit == pytest.approx(10.0)
  strategy.exit_profit_offset = 10.0 / trade.stake_amount + offset_delta

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, 100.0, "gtc", "exit_fixture", NOW)

  assert result is (offset_delta <= 0.0)


@pytest.mark.parametrize("profit_case", [(False, 3), (True, 3)], indirect=True, ids=["long", "short"])
@pytest.mark.parametrize("funding_fee", [-9.0, 9.0])
def test_profit_confirmation_includes_remaining_position_funding(profit_case, funding_fee):
  strategy, trade = profit_case
  strategy.hold_support_enabled = False
  strategy.exit_profit_only = True
  strategy.exit_profit_offset = 0.0
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 1.0, 90.0 if trade.is_short else 110.0)
  trade.set_funding_fees(funding_fee)
  rate = 102.0 if trade.is_short else 98.0
  assert trade.calculate_profit(rate).total_profit == pytest.approx(-8.0 + funding_fee)

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, rate, "gtc", "exit_fixture", NOW)

  assert result is (funding_fee > 8.0)


@pytest.mark.parametrize("reason", ["force_exit", "stop_loss", "trailing_stop_loss"])
def test_profit_confirmation_preserves_force_and_stop_rules(profit_case, reason):
  strategy, trade = profit_case
  strategy.hold_support_enabled = False
  strategy.exit_profit_only = True
  strategy.exit_profit_offset = 10.0 if reason == "force_exit" else 0.0
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 1.0, 90.0 if trade.is_short else 110.0)

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, 100.0, "gtc", reason, NOW)

  assert result is (reason == "force_exit")


def test_profit_confirmation_preserves_configured_hold(profit_case, tmp_path):
  strategy, trade = profit_case
  strategy.config["user_data_dir"] = tmp_path
  strategy.exit_profit_only = True
  strategy.exit_profit_offset = 0.0
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 1.0, 90.0 if trade.is_short else 110.0)
  (tmp_path / "nfi-hold-trades.json").write_text(json.dumps({"trade_ids": {str(trade.id): 1.0}}))

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, 100.0, "gtc", "exit_fixture", NOW)

  assert not result
