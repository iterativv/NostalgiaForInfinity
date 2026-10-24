from datetime import datetime
from datetime import timedelta
from datetime import timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import CandleType
from freqtrade.enums import RunMode
from freqtrade.enums import TradingMode
from freqtrade.persistence import init_db
from freqtrade.persistence import Order
from freqtrade.persistence import Trade

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def fill(trade, entry, amount, price):
  side = trade.entry_side if entry else trade.exit_side
  filled_at = trade.open_date_utc + timedelta(minutes=5 * len(trade.orders))
  trade.orders.append(
    Order(
      order_id=f"{trade.id}-{len(trade.orders) + 1}",
      ft_order_side=side,
      ft_pair=trade.pair,
      ft_is_open=False,
      ft_amount=amount,
      ft_price=price,
      ft_order_tag="fixture",
      status="closed",
      side=side,
      order_type="limit",
      amount=amount,
      filled=amount,
      remaining=0.0,
      price=price,
      average=price,
      cost=amount * price,
      order_date=filled_at,
      order_filled_date=filled_at,
    )
  )
  Trade.session.flush()
  trade.recalc_trade_from_orders()


@pytest.fixture(params=[(False, 1), (False, 3), (True, 3)], ids=["spot", "long", "short"])
def profit_case(request):
  init_db("sqlite://")
  short, leverage = request.param
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.config = {
    "stake_currency": "USDT",
    "runmode": RunMode.DRY_RUN,
    "timeframe": "5m",
    "candle_type_def": CandleType.FUTURES if leverage > 1 else CandleType.SPOT,
    "exchange": {"name": "binance"},
  }
  strategy.is_futures_mode = leverage > 1
  strategy.dp = DataProvider(strategy.config, None)
  # Normal quick exits are separate from the bad-trade eligibility under test.
  strategy.long_exit_quick = MagicMock(return_value=(False, None))
  strategy.short_exit_quick = MagicMock(return_value=(False, None))
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="binance",
    is_short=short,
    leverage=leverage,
    trading_mode=TradingMode.FUTURES if leverage > 1 else TradingMode.SPOT,
    amount=0.0,
    stake_amount=0.0,
    open_rate=100.0,
    open_date=NOW - timedelta(days=30),
    fee_open=0.0,
    fee_close=0.0,
    funding_fees=0.0,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag="543" if short else "43",
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data("system_version", "system_v4")
  candle = {"EMA_50_1d": 100.0, "EMA_200_1d": 100.0, "RANGE_PCT_14_1d": 5.0}
  strategy.dp._set_cached_df(
    trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
  )
  yield strategy, trade
  engine = Trade.session.get_bind()
  Trade.session.rollback()
  Trade.session.remove()
  engine.dispose()


def losing_history(trade):
  fill(trade, True, 10.0, 100.0)
  fill(trade, False, 9.0, 140.0 if trade.is_short else 60.0)
  fill(trade, True, 1.0, 180.0 if trade.is_short else 20.0)
  return 130.0 if trade.is_short else 70.0


def custom_exit(case, rate):
  strategy, trade = case
  return strategy.custom_exit(trade.pair, trade, NOW, rate, trade.calc_profit_ratio(rate))


@pytest.mark.parametrize("reason", ["stale", "structure"])
def test_realized_loss_remains_eligible_when_residual_position_gains(profit_case, reason):
  strategy, trade = profit_case
  rate = losing_history(trade)
  if reason == "structure":
    candle = {"EMA_50_1d": 150.0 if trade.is_short else 50.0, "EMA_200_1d": 100.0}
    strategy.dp._set_cached_df(
      trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
    )
  assert trade.calc_profit_ratio(rate) > 0.0
  _, entries, exits = strategy.filled_order_snapshot(trade)
  assert strategy.calc_total_profit(trade, entries, exits, rate)[0] == pytest.approx(-340.0)

  result = custom_exit(profit_case, rate)

  expected = "exit_bad_trade_abandon_30d" if reason == "stale" else "exit_bad_trade_broken_30pct"
  assert result == f"{expected} ( {trade.enter_tag})"


def test_realized_gain_prevents_bad_trade_exit_on_losing_residual(profit_case):
  strategy, trade = profit_case
  fill(trade, True, 10.0, 100.0)
  fill(trade, False, 9.0, 70.0 if trade.is_short else 130.0)
  rate = 120.0 if trade.is_short else 80.0
  assert trade.calc_profit_ratio(rate) < 0.0
  _, entries, exits = strategy.filled_order_snapshot(trade)
  assert strategy.calc_total_profit(trade, entries, exits, rate)[0] == pytest.approx(250.0)

  assert custom_exit(profit_case, rate) is None


def test_zero_whole_trade_profit_is_not_a_loss(profit_case):
  strategy, trade = profit_case
  fill(trade, True, 10.0, 100.0)
  fill(trade, False, 9.0, 90.0 if trade.is_short else 110.0)
  rate = 190.0 if trade.is_short else 10.0
  _, entries, exits = strategy.filled_order_snapshot(trade)
  assert strategy.calc_total_profit(trade, entries, exits, rate)[0] == 0.0

  assert custom_exit(profit_case, rate) is None


def test_unreduced_losing_trade_still_exits(profit_case):
  _, trade = profit_case
  fill(trade, True, 10.0, 100.0)

  assert custom_exit(profit_case, 120.0 if trade.is_short else 80.0) == (
    f"exit_bad_trade_abandon_30d ( {trade.enter_tag})"
  )


@pytest.mark.parametrize("system", ["system_v4", "system_v3_2", "system_v2", None])
@pytest.mark.parametrize("enabled", [False, True])
def test_stored_system_uses_its_existing_enable_flag(profit_case, system, enabled):
  strategy, trade = profit_case
  rate = losing_history(trade)
  trade.set_custom_data("system_version", system)
  strategy.system_v4_bad_trade_exit_enable = enabled if system == "system_v4" else not enabled
  strategy.legacy_system_bad_trade_exit_enable = not enabled if system == "system_v4" else enabled

  result = custom_exit(profit_case, rate)

  assert result == (f"exit_bad_trade_abandon_30d ( {trade.enter_tag})" if enabled else None)


@pytest.mark.parametrize("blocked_by", ["age", "range", "missing_range"])
def test_stale_conditions_still_apply(profit_case, blocked_by):
  strategy, trade = profit_case
  rate = losing_history(trade)
  if blocked_by == "age":
    trade.open_date = NOW - timedelta(days=13)
  else:
    candle = {"EMA_50_1d": 100.0, "EMA_200_1d": 100.0}
    if blocked_by == "range":
      candle["RANGE_PCT_14_1d"] = 7.0
    strategy.dp._set_cached_df(
      trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
    )

  assert custom_exit(profit_case, rate) is None


@pytest.mark.parametrize("net_profit", [-0.1, 0.1])
def test_gate_uses_net_profit_after_fees_and_funding(profit_case, net_profit):
  strategy, trade = profit_case
  trade.fee_open = trade.fee_close = 0.001
  rate = losing_history(trade)
  fee_cost = 2.7 if trade.is_short else 1.7
  trade.funding_fees = 340.0 + fee_cost + net_profit
  expected_profit = net_profit if strategy.is_futures_mode else -340.0 - fee_cost
  _, entries, exits = strategy.filled_order_snapshot(trade)
  assert strategy.calc_total_profit(trade, entries, exits, rate)[0] == pytest.approx(expected_profit)

  result = custom_exit(profit_case, rate)

  assert result == (f"exit_bad_trade_abandon_30d ( {trade.enter_tag})" if expected_profit < 0.0 else None)
