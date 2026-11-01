from datetime import datetime
from datetime import timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.enums import State
from freqtrade.exchange import amount_to_contract_precision
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import Order
from freqtrade.persistence import Trade
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_liquidation_rescue as rescue


rescue_case = rescue.rescue_case
pytestmark = pytest.mark.parametrize("rescue_case", [(False, 1), (False, 3)], indirect=True, ids=["spot", "futures"])


@pytest.fixture
def buyback_case(rescue_case, mocker):
  strategy, trade = rescue_case
  strategy.derisk_enable = strategy.system_v4_derisk_level_4_enable = True
  strategy.system_v4_buyback_1_enable = True
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  trade.fee_open = trade.fee_close = 0.0
  trade.funding_fees = trade.funding_fee_running = 0.0
  initial = trade.orders[0]
  initial.price = initial.average = initial.ft_price = 150.0
  initial.cost = 1500.0
  trade.liquidation_price = 105.0 if strategy.is_futures_mode else None
  trade.recalc_trade_from_orders()
  candle = {"close": 150.0, "protections_long_global": True, "enter_long": True}
  strategy.dp._set_cached_df(
    trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
  )
  strategy.config.update(
    dry_run=True, dry_run_wallet=10000.0, tradable_balance_ratio=1.0, trading_mode=trade.trading_mode
  )
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  clock.return_value = rescue.NOW
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config, bot.strategy, bot.trading_mode = strategy.config, strategy, trade.trading_mode
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_min_pair_stake_amount.return_value = 10.0 / trade.leverage
  bot.exchange.get_max_pair_stake_amount.return_value = 10000.0
  bot.exchange.get_funding_fees.return_value = 0.0
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )

  def create_order(**kwargs):
    return {
      "id": f"buyback-order-{len(trade.orders)}",
      "symbol": trade.pair,
      "type": "limit",
      "side": kwargs["side"],
      "status": "open",
      "price": kwargs["rate"],
      "amount": kwargs["amount"],
      "filled": 0.0,
      "remaining": kwargs["amount"],
      "cost": 0.0,
      "timestamp": int(clock.return_value.timestamp() * 1000),
    }

  def settle(order, filled, status="closed"):
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

  bot.exchange.create_order.side_effect = create_order
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_exit = MagicMock()
  # Admission is observed, then its returned request is filled through real Trade/Order.
  bot.execute_entry = MagicMock()
  bot.exchange.get_rates.return_value = (128.0, 128.0)
  bot.check_and_call_adjust_trade_position(trade)
  first_exit = trade.orders[-1]
  assert first_exit.ft_order_tag == "derisk_level_4"
  assert first_exit.amount == 9.87890625
  settle(first_exit, first_exit.amount)

  clock.return_value += timedelta(minutes=5)
  bot.exchange.get_rates.return_value = (150.0, 150.0)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_called_once()
  assert bot.execute_entry.call_args.args[1] == 1500.0 / trade.leverage
  assert bot.execute_entry.call_args.kwargs["enter_tag"] == "buyback_1_entry"
  entry_payload = create_order(side=trade.entry_side, rate=150.0, amount=10.0)
  entry = Order.parse_from_ccxt_object(entry_payload, trade.pair, trade.entry_side)
  entry.ft_order_tag = bot.execute_entry.call_args.kwargs["enter_tag"]
  trade.orders.append(entry)
  Trade.session.flush()
  settle(entry, 10.0)

  clock.return_value += timedelta(minutes=5)
  bot.execute_entry.reset_mock()
  bot.exchange.get_rates.return_value = (135.0, 135.0)
  bot.check_and_call_adjust_trade_position(trade)
  bot.execute_entry.assert_not_called()
  original = trade.orders[-1]
  assert original.ft_order_tag == f"buyback_1_derisk {entry.id}"
  assert original.amount == 10.0
  bot.exchange.create_order.reset_mock()
  return bot, trade, settle, clock


@pytest.mark.parametrize("status", ["canceled", "expired", "closed"])
@pytest.mark.parametrize("rate", [135.0, 150.0])
@pytest.mark.parametrize("enabled", [False, True], ids=["admissions-off", "admissions-on"])
def test_active_buyback_derisk_finishes_its_remaining_quantity(buyback_case, status, rate, enabled):
  bot, trade, settle, clock = buyback_case
  original = trade.orders[-1]
  tag = original.ft_order_tag
  settle(original, 1.0, status)
  clock.return_value += timedelta(minutes=5)
  bot.strategy.system_v4_buyback_1_enable = enabled
  bot.exchange.get_rates.return_value = (rate, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry.ft_order_side == trade.exit_side
  assert retry.ft_order_tag == tag
  assert retry.amount == 9.0
  settle(retry, retry.amount)
  assert trade.amount == 0.12109375
  clock.return_value += timedelta(minutes=5)
  bot.exchange.create_order.reset_mock()
  bot.check_and_call_adjust_trade_position(trade)
  bot.exchange.create_order.assert_not_called()
  bot.execute_entry.assert_not_called()


@pytest.mark.parametrize("filled,rate", [(1.0, 112.0), (9.99, 150.0)], ids=["reserve", "below-minimum"])
def test_untradeable_buyback_remainder_does_not_open_another_buyback(buyback_case, filled, rate):
  bot, trade, settle, clock = buyback_case
  settle(trade.orders[-1], filled, "canceled")
  clock.return_value += timedelta(minutes=5)
  bot.exchange.get_rates.return_value = (rate, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("filled", [0.0, 10.0], ids=["zero-fill", "complete"])
def test_buyback_zero_and_complete_fills_keep_existing_behavior(buyback_case, filled):
  bot, trade, settle, clock = buyback_case
  original = trade.orders[-1]
  tag = original.ft_order_tag
  settle(original, filled, "canceled" if filled == 0.0 else "closed")
  clock.return_value += timedelta(minutes=5)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  if filled == 0.0:
    bot.exchange.create_order.assert_called_once()
    assert trade.orders[-1].ft_order_tag == tag
    assert trade.orders[-1].amount == 10.0
  else:
    bot.exchange.create_order.assert_not_called()


def test_open_buyback_exit_is_not_duplicated(buyback_case):
  bot, trade, _, clock = buyback_case
  clock.return_value += timedelta(minutes=5)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_not_called()


def test_buyback_dust_preserves_existing_emergency(rescue_case):
  strategy, trade = rescue_case
  strategy.derisk_enable = strategy.system_v4_derisk_level_3_enable = True
  strategy.system_v4_derisk_level_4_enable = True
  strategy.system_v4_derisk_level_4_stake_spot = strategy.system_v4_derisk_level_4_stake_futures = 0.5
  strategy.system_v4_buyback_1_enable = True
  trade.fee_open = trade.fee_close = 0.0
  trade.liquidation_price = 70.0
  trade.recalc_trade_from_orders()
  candle = {"close": 100.0, "protections_long_global": True, "enter_long": True}
  strategy.dp._set_cached_df(
    trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
  )

  def adjust(rate):
    now = rescue.NOW + timedelta(minutes=5 * len(trade.orders))
    return strategy.adjust_trade_position(
      trade,
      now,
      rate,
      trade.calc_profit_ratio(rate),
      5.0 / trade.leverage,
      10000.0,
      rate,
      rate,
      trade.calc_profit_ratio(rate),
      trade.calc_profit_ratio(rate),
    )

  assert adjust(90.0) == (pytest.approx(-500.0 / trade.leverage), "derisk_level_4")
  first = rescue.add_order(trade, trade.exit_side, "derisk_level_4", 5.0)
  first.price = first.average = first.ft_price = 90.0
  first.cost = 450.0
  trade.recalc_trade_from_orders()
  assert adjust(100.0) == (pytest.approx(1000.0 / trade.leverage), "buyback_1_entry")
  entry = rescue.add_order(trade, trade.entry_side, "buyback_1_entry", 10.0)
  tag = f"buyback_1_derisk {entry.id}"
  assert adjust(90.0) == (pytest.approx(-1000.0 / trade.leverage), tag)
  partial = rescue.add_order(trade, trade.exit_side, tag, 10.0, 9.99, "canceled")
  partial.price = partial.average = partial.ft_price = 90.0
  partial.cost = 899.1
  trade.recalc_trade_from_orders()
  assert trade.amount == 5.01

  result = adjust(72.0)

  if strategy.is_futures_mode:
    assert result == (pytest.approx(-(5.01 - 7.75 / 72.0) * 100.0 / trade.leverage), "derisk_level_3")
  else:
    assert result is None
