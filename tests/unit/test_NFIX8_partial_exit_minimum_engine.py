from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import MarginMode, State
from freqtrade.exchange import amount_to_contract_precision
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


@pytest.fixture(params=["grind", "regular"])
def legacy_partial_bot(partial_bot, partial_exit_case, request, mocker):
  strategy, trade = partial_exit_case
  trade.set_custom_data("system_version", None)
  trade.open_date = partial.NOW.replace(year=2024, month=2, day=6)
  trade.enter_tag = ("620" if trade.is_short else "120") if request.param == "grind" else trade.enter_tag
  trade.orders[0].ft_order_tag = trade.enter_tag
  trade.orders[1].ft_order_tag = "gd1" if request.param == "grind" else "g1"
  for index, order in enumerate(trade.orders):
    order.order_date = order.order_filled_date = trade.open_date_utc + timedelta(hours=index)
  trade.fee_open = trade.fee_close = 0.0
  trade.funding_fees = trade.funding_fee_running = 0.0
  trade.recalc_trade_from_orders()
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  strategy.derisk_use_grind_stops = strategy.regular_mode_use_grind_stops = False
  strategy.grind_1_profit_threshold_spot = strategy.grind_1_profit_threshold_futures = 10.0
  strategy.long_grind_entry = MagicMock(return_value=False)
  strategy.long_grind_entry_v3 = MagicMock(return_value=False)
  strategy.short_grind_entry = MagicMock(return_value=False)
  partial_bot.margin_mode = MarginMode.ISOLATED if trade.leverage > 1 else MarginMode.NONE
  partial_bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  clock.return_value = partial.NOW
  create_order = partial_bot.exchange.create_order.side_effect
  partial_bot.exchange.create_order.side_effect = lambda **kwargs: {
    **create_order(**kwargs),
    "id": f"legacy-retry-{len(trade.orders)}",
    "timestamp": int(clock.return_value.timestamp() * 1000),
  }
  partial_bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  rate = 80.0 if trade.is_short else 128.0
  partial_bot.exchange.get_rates.return_value = (rate, rate)
  partial_bot.check_and_call_adjust_trade_position(trade)
  partial_bot.execute_entry.assert_not_called()
  partial_bot.exchange.create_order.assert_called_once()
  first = trade.orders[-1]
  assert first.ft_order_tag.split()[0] == ("gm0" if request.param == "grind" else "g1")
  partial_bot.exchange.create_order.reset_mock()

  def settle(order, filled, status):
    order.update_from_ccxt_object(
      {
        "id": order.order_id,
        "status": status,
        "amount": order.amount,
        "filled": filled,
        "remaining": order.amount - filled,
        "price": order.price,
        "average": order.price,
        "cost": filled * order.price,
        "timestamp": int(clock.return_value.timestamp() * 1000),
        "lastTradeTimestamp": int(clock.return_value.timestamp() * 1000),
      }
    )
    trade.update_trade(order)

  return partial_bot, trade, settle, clock


@pytest.mark.parametrize(
  "remainder,rate,eligible",
  [(0.046875, 128.0, True), (0.0625, 128.0, True), (0.03125, 128.0, False), (0.0625, 80.0, False)],
  ids=["current-value-only", "both-values", "below-minimum", "exact-minimum"],
)
def test_legacy_retry_uses_current_value_minimum(legacy_partial_bot, remainder, rate, eligible):
  bot, trade, settle, clock = legacy_partial_bot
  original = trade.orders[-1]
  owner_amount = trade.amount - original.amount
  settle(original, original.amount - remainder, "canceled")
  clock.return_value += timedelta(minutes=5)
  bot.exchange.get_rates.return_value = (rate, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  if not eligible:
    bot.exchange.create_order.assert_not_called()
    assert trade.amount == pytest.approx(owner_amount + remainder, rel=0, abs=1e-8)
    return
  bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry is not original
  assert retry.ft_order_side == trade.exit_side
  assert retry.ft_order_tag == original.ft_order_tag
  assert abs(Decimal(str(retry.amount)) - Decimal(str(remainder))) <= Decimal("0.00000001")
  settle(retry, retry.amount, "closed")
  assert abs(Decimal(str(trade.amount)) - Decimal(str(owner_amount))) <= Decimal("0.00000001")
