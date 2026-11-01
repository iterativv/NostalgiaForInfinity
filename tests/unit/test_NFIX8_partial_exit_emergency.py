from datetime import datetime
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import State
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.wallets import Wallets

from tests.unit import test_NFIX8_liquidation_rescue as rescue


rescue_case = rescue.rescue_case
pytestmark = pytest.mark.parametrize(
  "rescue_case", [(False, 1), (False, 3), (True, 3)], indirect=True, ids=["spot", "long", "short"]
)


@pytest.fixture
def emergency_bot(rescue_case, mocker):
  strategy, trade = rescue_case
  strategy.derisk_enable = strategy.system_v4_derisk_level_3_enable = True
  strategy.system_v4_grind_1_enable = True
  strategy.long_grind_entry_v4.return_value = True
  strategy.short_grind_entry_v4.return_value = True
  rescue.add_order(trade, trade.entry_side, "grind_1_entry", 4.0)
  trade.liquidation_price = 130.0 if trade.is_short else 70.0
  rate = 128.0 if trade.is_short else 72.0
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
  bot.exchange.get_rates.return_value = (rate, rate)
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0 / trade.leverage
  bot.exchange.get_max_pair_stake_amount.return_value = 10000.0
  bot.exchange.amount_to_contract_precision.side_effect = lambda pair, amount: round(amount, 8)
  bot.exchange.get_funding_fees.return_value = 0.0

  def create_order(**kwargs):
    return {
      "id": "emergency-reduction",
      "symbol": trade.pair,
      "type": "limit",
      "side": kwargs["side"],
      "status": "open",
      "price": kwargs["rate"],
      "amount": kwargs["amount"],
      "filled": 0.0,
      "remaining": kwargs["amount"],
      "cost": 0.0,
      "timestamp": int(rescue.NOW.timestamp() * 1000),
    }

  bot.exchange.create_order.side_effect = create_order
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot._notify_exit = MagicMock()
  bot.execute_entry = MagicMock()
  mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now.return_value = rescue.NOW
  return bot


@pytest.mark.parametrize("status", ["canceled", "expired", "closed"])
def test_untradeable_remainder_keeps_emergency_derisk_reachable(emergency_bot, rescue_case, status):
  strategy, trade = rescue_case
  tag = f"grind_1_exit {trade.orders[1].id}"
  rescue.add_order(trade, trade.exit_side, tag, 4.0, 3.99, status)

  emergency_bot.check_and_call_adjust_trade_position(trade)

  emergency_bot.execute_entry.assert_not_called()
  if not strategy.is_futures_mode:
    emergency_bot.exchange.create_order.assert_not_called()
    return
  emergency_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == "derisk_level_3"
  assert order.ft_order_side == trade.exit_side
  assert order.amount == pytest.approx(5.0)
  rate = emergency_bot.exchange.get_rates.return_value[1]
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
      "timestamp": int(rescue.NOW.timestamp() * 1000),
      "lastTradeTimestamp": int(rescue.NOW.timestamp() * 1000),
    }
  )
  trade.update_trade(order)
  assert trade.amount == pytest.approx(5.01)


@pytest.mark.parametrize(
  "gate",
  [
    "global",
    "level",
    "emergency",
    "filled",
    "profit",
    "missing",
    "invalid",
    "far",
    "crossed",
    "minimum",
    "open_order",
    "equality",
    "reserve",
  ],
)
def test_blocked_remainder_preserves_emergency_exclusions_and_no_new_entry(emergency_bot, rescue_case, gate):
  strategy, trade = rescue_case
  filled = 3.99
  if gate == "global":
    strategy.derisk_enable = False
  elif gate == "level":
    strategy.system_v4_derisk_level_3_enable = False
  elif gate == "emergency":
    strategy.system_v4_derisk_level_3_liquidation_enable = False
  elif gate == "filled":
    rescue.add_order(trade, trade.exit_side, "derisk_level_3", 5.0)
  elif gate == "profit":
    rate = 98.0 if trade.is_short else 102.0
    trade.liquidation_price = rate * (1.02 if trade.is_short else 0.98)
    emergency_bot.exchange.get_rates.return_value = (rate, rate)
  elif gate == "missing":
    trade.liquidation_price = None
  elif gate == "invalid":
    trade.liquidation_price = 0.0
  elif gate == "far":
    trade.liquidation_price = 180.0 if trade.is_short else 40.0
  elif gate == "crossed":
    trade.liquidation_price = 120.0 if trade.is_short else 80.0
  elif gate == "minimum":
    emergency_bot.exchange.get_min_pair_stake_amount.return_value = 1000.0 / trade.leverage
  elif gate == "equality":
    filled = 3.875
    rate = emergency_bot.exchange.get_rates.return_value[1]
    emergency_bot.exchange.get_min_pair_stake_amount.return_value = 0.125 * rate / trade.leverage
  elif gate == "reserve":
    rescue.add_order(trade, trade.exit_side, "exit_normal", 9.9)
    filled = 1.0
    emergency_bot.exchange.get_min_pair_stake_amount.return_value = 10.0 / trade.leverage
  tag = f"grind_1_exit {trade.orders[1].id}"
  rescue.add_order(trade, trade.exit_side, tag, 4.0, filled, "canceled")
  if gate == "open_order":
    rescue.add_order(trade, trade.entry_side, "grind_2_entry", 1.0, 0.0, "open")

  emergency_bot.check_and_call_adjust_trade_position(trade)

  emergency_bot.execute_entry.assert_not_called()
  emergency_bot.exchange.create_order.assert_not_called()


def test_valid_partial_retry_keeps_priority_over_emergency(emergency_bot, rescue_case):
  _, trade = rescue_case
  tag = f"grind_1_exit {trade.orders[1].id}"
  rescue.add_order(trade, trade.exit_side, tag, 4.0, 3.8, "canceled")

  emergency_bot.check_and_call_adjust_trade_position(trade)

  emergency_bot.execute_entry.assert_not_called()
  emergency_bot.exchange.create_order.assert_called_once()
  assert trade.orders[-1].ft_order_tag == tag
  assert trade.orders[-1].amount == pytest.approx(0.2)


def test_same_emergency_runs_without_blocked_remainder(emergency_bot, rescue_case):
  strategy, trade = rescue_case
  strategy.system_v4_grind_1_enable = False
  rescue.add_order(trade, trade.exit_side, f"grind_1_exit {trade.orders[1].id}", 4.0)

  emergency_bot.check_and_call_adjust_trade_position(trade)

  emergency_bot.execute_entry.assert_not_called()
  if strategy.is_futures_mode:
    emergency_bot.exchange.create_order.assert_called_once()
    assert trade.orders[-1].ft_order_tag == "derisk_level_3"
    assert trade.orders[-1].amount == pytest.approx(5.0)
  else:
    emergency_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("state", ["disabled", "sizing", "unblocked"])
@pytest.mark.parametrize("level", range(1, 6))
def test_blocked_remainder_preserves_other_queue_profit_peaks(emergency_bot, rescue_case, state, level):
  strategy, trade = rescue_case
  strategy.system_v4_grind_1_enable = False
  strategy.system_v4_derisk_level_3_liquidation_enable = state == "sizing"
  if state == "unblocked":
    strategy.derisk_enable = False
  pending_level = 2 if level == 1 else 1
  trade.orders[1].ft_order_tag = f"grind_{pending_level}_entry"
  other = rescue.add_order(trade, trade.entry_side, f"grind_{level}_entry", 1.0)
  other.price = other.average = other.ft_price = 150.0 if trade.is_short else 50.0
  other.cost = other.price
  trade.recalc_trade_from_orders()
  rescue.add_order(
    trade,
    trade.exit_side,
    f"grind_{pending_level}_exit {trade.orders[1].id}",
    4.0,
    4.0 if state == "unblocked" else 3.99,
    "canceled",
  )
  if state == "sizing":
    emergency_bot.exchange.get_min_pair_stake_amount.return_value = 1000.0 / trade.leverage

  emergency_bot.check_and_call_adjust_trade_position(trade)

  emergency_bot.execute_entry.assert_not_called()
  emergency_bot.exchange.create_order.assert_not_called()
  stake_peak = trade.get_custom_data(f"grind_{level}_cluster_max_profit_stake")
  rate_peak = trade.get_custom_data(f"grind_{level}_cluster_max_profit_rate")
  if state == "unblocked":
    assert stake_peak == pytest.approx(22.128 if trade.is_short else 21.928)
    assert rate_peak == pytest.approx(-22.0 / 150.0 if trade.is_short else 0.44)
  else:
    assert (stake_peak, rate_peak) == (None, None)
