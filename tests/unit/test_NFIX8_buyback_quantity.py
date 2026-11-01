"""Engine reductions must respect the inventory owned by active long buybacks."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.enums import MarginMode, State
from freqtrade.exchange import amount_to_contract_precision
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_liquidation_rescue as rescue
from tests.unit.test_NFIX8_v4_grind_quantity import settle_base_fee


rescue_case = rescue.rescue_case
SCOPES = [
  ("v2", level, reason, 110.0 if reason == "exit" else 70.0) for level in (1, 2, 3) for reason in ("exit", "derisk")
] + [("v3", 1, "derisk", 90.0), ("v4", 1, "derisk", 90.0)]


@pytest.fixture
def buyback_quantity_bot(rescue_case, mocker):
  strategy, trade = rescue_case
  strategy.derisk_enable = False
  strategy.hold_support_enabled = strategy.exit_profit_only = False
  strategy.dp.send_msg = MagicMock()
  # Model indicator decisions, not quantity accounting or adjustment routing.
  for version in ("v2", "v3", "v4"):
    for kind in ("grind", "buyback"):
      mocker.patch.object(strategy, f"long_{kind}_entry_{version}", return_value=False)
  for version in ("v3", "v4"):
    mocker.patch.object(strategy, f"long_rebuy_entry_{version}", return_value=False)
  strategy.config.update(
    dry_run=True, dry_run_wallet=10000.0, tradable_balance_ratio=1.0, trading_mode=trade.trading_mode
  )
  trade.funding_fees = trade.funding_fee_running = 0.0
  trade.liquidation_price = None
  candle = {
    "close": 100.0,
    "RSI_3": 100.0,
    "RSI_3_15m": 100.0,
    "RSI_3_1h": 100.0,
    "RSI_14": 50.0,
    "WILLR_14": -50.0,
    "STOCHRSIk_14_14_3_3": 50.0,
    "BBU_20_2.0": 200.0,
    "AROONU_14": 100.0,
    "AROONU_14_15m": 100.0,
    "protections_long_global": True,
    "enter_long": False,
  }
  strategy.dp._set_cached_df(
    trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
  )
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  clock.return_value = rescue.NOW
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config, bot.strategy, bot.trading_mode = strategy.config, strategy, trade.trading_mode
  bot.margin_mode = MarginMode.ISOLATED if strategy.is_futures_mode else MarginMode.NONE
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0 / trade.leverage
  bot.exchange.get_max_pair_stake_amount.return_value = 100000.0
  bot.exchange.get_funding_fees.return_value = 0.0
  bot.exchange.get_liquidation_price.return_value = None
  bot.exchange.check_order_canceled_empty.return_value = False
  bot.exchange.order_has_fee.return_value = True
  bot.exchange.extract_cost_curr_rate.side_effect = lambda fee, pair, cost, amount: (
    fee["cost"],
    fee["currency"],
    fee["rate"],
  )
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: amount_to_contract_precision(
    amount, trade.amount_precision, trade.precision_mode, trade.contract_size
  )
  bot.exchange.create_order.side_effect = lambda **kw: {
    "id": f"buyback-quantity-{len(trade.orders)}",
    "symbol": trade.pair,
    "type": "limit",
    "side": kw["side"],
    "status": "open",
    "price": kw["rate"],
    "amount": kw["amount"],
    "filled": 0.0,
    "remaining": kw["amount"],
    "cost": 0.0,
    "timestamp": int(clock.return_value.timestamp() * 1000),
  }
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_enter = MagicMock()
  bot._notify_exit = MagicMock()
  bot.execute_entry = MagicMock()
  return bot, trade, clock


def seed_buyback(bot, trade, version, level, fee):
  # These are modeled closed admissions, not claims that entry signals fired:
  # initial 10 ETH, unrelated reduction 5 ETH, then a gross 10 ETH buyback.
  trade.set_custom_data("system_version", f"system_{version}" if version != "v2" else None)
  rescue.add_order(trade, trade.exit_side, "exit_normal", 5.0)
  entry = rescue.add_order(trade, trade.entry_side, f"buyback_{level}_entry", 10.0)
  # Apply even the zero fee via the engine; never assign safe_amount_after_fee.
  settle_base_fee(bot, trade, entry, fee)
  assert entry.safe_filled == 10.0
  assert entry.safe_fee_base == fee
  assert trade.amount == pytest.approx(15.0 - fee, rel=0, abs=1e-10)
  return entry


def assert_exit_units(order, expected):
  # Eight-decimal precision may truncate one atom during stake -> coin conversion.
  # Allow that loss only, never rounding up into unrelated inventory.
  units = round(order.amount * 100000000)
  expected_units = round(expected * 100000000)
  assert expected_units - 1 <= units <= expected_units


def settle_exit(trade, order, filled, status="closed"):
  order.status = status
  order.ft_is_open = False
  order.filled = filled
  order.remaining = order.amount - filled
  order.average = order.price
  order.cost = filled * order.price
  order.order_filled_date = rescue.NOW
  trade.update_trade(order)


@pytest.mark.parametrize(
  "rescue_case,fee",
  [((False, 1), 0.0), ((False, 1), 0.01), ((False, 3), 0.0)],
  indirect=["rescue_case"],
  ids=["spot-no-base-fee", "spot-base-fee", "futures-no-base-fee"],
)
@pytest.mark.parametrize("version,level,reason,rate", SCOPES)
def test_buyback_exit_preserves_unrelated_inventory(buyback_quantity_bot, version, level, reason, rate, fee):
  bot, trade, _ = buyback_quantity_bot
  entry = seed_buyback(bot, trade, version, level, fee)
  bot.exchange.get_rates.return_value = (rate, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"buyback_{level}_{reason} {entry.id}"
  assert order.ft_order_side == trade.exit_side
  assert_exit_units(order, 10.0 - fee)
  settle_exit(trade, order, order.amount)
  remaining_units = round(trade.amount * 100000000)
  assert 500000000 <= remaining_units <= 500000001


@pytest.mark.parametrize("rescue_case", [(False, 1)], indirect=True)
def test_v4_partial_buyback_retries_only_its_net_remainder(buyback_quantity_bot):
  bot, trade, clock = buyback_quantity_bot
  entry = seed_buyback(bot, trade, "v4", 1, 0.01)
  bot.exchange.get_rates.return_value = (90.0, 90.0)
  bot.check_and_call_adjust_trade_position(trade)
  first = trade.orders[-1]
  assert first.ft_order_tag == f"buyback_1_derisk {entry.id}"
  settle_exit(trade, first, 4.0, "canceled")
  clock.return_value += timedelta(minutes=5)
  bot.exchange.get_rates.return_value = (91.0, 91.0)
  bot.exchange.create_order.reset_mock()

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry is not first
  assert retry.ft_order_tag == first.ft_order_tag
  assert_exit_units(retry, 5.99)
  settle_exit(trade, retry, retry.amount)
  assert 500000000 <= round(trade.amount * 100000000) <= 500000002


@pytest.mark.parametrize("rescue_case", [(False, 1)], indirect=True)
@pytest.mark.parametrize("version,rate", [("v2", 70.0), ("v3", 90.0), ("v4", 90.0)])
def test_buyback_keeps_existing_minimum_reserve(buyback_quantity_bot, version, rate):
  bot, trade, _ = buyback_quantity_bot
  entry = seed_buyback(bot, trade, version, 1, 0.01)
  bot.exchange.get_min_pair_stake_amount.return_value = 300.0
  bot.exchange.get_rates.return_value = (rate, rate)
  expected = trade.amount - 300.0 * 1.55 / rate

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"buyback_1_derisk {entry.id}"
  assert_exit_units(order, expected)
  assert order.amount < 9.99


@pytest.mark.parametrize("rescue_case", [(False, 1)], indirect=True)
def test_v2_buyback_keeps_raw_profit_price_boundary(buyback_quantity_bot):
  bot, trade, _ = buyback_quantity_bot
  entry = seed_buyback(bot, trade, "v2", 1, 0.01)
  threshold = bot.strategy.grinding_v2_buyback_1_profit_threshold_spot + trade.fee_open + trade.fee_close
  rate = 100.0 * (1.0 + threshold) + 0.000001
  bot.exchange.get_rates.return_value = (rate, rate)

  bot.check_and_call_adjust_trade_position(trade)

  bot.execute_entry.assert_not_called()
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"buyback_1_exit {entry.id}"
  assert_exit_units(order, 9.99)
