"""Deterministic real Trade/Order ledgers for demand remainder callbacks."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import CandleType, RunMode, TradingMode
from freqtrade.persistence import Order, Trade, init_db

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
FEATURE = "legacy_grind_demand_exit_enable"
KEY = "legacy_grind_demand_exit"
EXIT = "exit_long_grind_demand_gm0"
DEMAND = NOW
DUE = NOW + timedelta(minutes=5)


def fill(trade, side, amount, tag, price=100.0, filled=None, time=None):
  executed = amount if filled is None else filled
  stamp = time or (NOW - timedelta(days=3) + timedelta(minutes=len(trade.orders)))
  order = Order(
    order_id=f"{trade.id}-{len(trade.orders) + 1}",
    ft_order_side=side,
    ft_pair=trade.pair,
    ft_is_open=False,
    ft_amount=amount,
    ft_price=price,
    ft_order_tag=tag,
    status="closed" if executed == amount else "canceled",
    side=side,
    order_type="limit",
    amount=amount,
    filled=executed,
    remaining=amount - executed,
    price=price,
    average=price,
    cost=executed * price,
    order_date=stamp,
    order_filled_date=stamp,
  )
  trade.orders.append(order)
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  return order


def configure(trade, enabled=None):
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.config = {
    "stake_currency": "USDT",
    "runmode": RunMode.BACKTEST,
    "timeframe": "5m",
    "candle_type_def": CandleType.FUTURES if trade.leverage > 1 else CandleType.SPOT,
    "exchange": {"name": "binance"},
    "exit_pricing": {"price_side": "other"},
    "max_open_trades": 6,
  }
  strategy.is_futures_mode = trade.leverage > 1
  strategy.position_adjustment_enable = True
  strategy.derisk_enable = False
  if enabled is not None:
    setattr(strategy, FEATURE, enabled)
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.send_msg = MagicMock()
  strategy.long_grind_entry_v3 = MagicMock(return_value=False)
  strategy.long_grind_entry_v4 = MagicMock(return_value=False)
  strategy.grind_mode_coins = ["ETH", "INJ", "ADA", "LINK"]
  strategy.grind_mode_max_slots = 1
  strategy._remove_profit_target = MagicMock()
  return strategy


@dataclass(frozen=True, slots=True)
class D1Case:
  strategy: NostalgiaForInfinityX8
  trade: Trade
  entry: Order
  gm0: Order | None

  def frame(self, rate):
    frame = pd.DataFrame([{"close": rate}, {"close": rate}])
    self.strategy.dp._set_cached_df(self.trade.pair, "5m", frame, self.strategy.config["candle_type_def"])
    self.strategy.dp._set_dataframe_max_index(self.trade.pair, 2)

  def demand(self, time=DEMAND, pair="INJ/USDT:USDT"):
    return self.strategy.confirm_trade_entry(pair, "limit", 1.0, 11.0, "GTC", time, "120", "long")

  def adjust(self, time=DUE, rate=11.0, minimum=5.0):
    self.frame(rate)
    profit = self.trade.calc_profit_ratio(rate)
    return self.strategy.adjust_trade_position(
      self.trade, time, rate, profit, minimum, 100000.0, rate, rate, profit, profit
    )

  def exit(self, time=DUE, rate=11.0):
    self.frame(rate)
    return self.strategy.custom_exit(self.trade.pair, self.trade, time, rate, self.trade.calc_profit_ratio(rate))

  def restart(self, enabled=None):
    return D1Case(configure(self.trade, enabled), self.trade, self.entry, self.gm0)


def make_d1(enabled=None, initial_only=False, leverage=3.0, base_fee=0.0, fees=0.0005):
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="binance",
    is_short=False,
    leverage=leverage,
    trading_mode=TradingMode.FUTURES if leverage > 1 else TradingMode.SPOT,
    amount=0.0,
    stake_amount=0.0,
    open_rate=100.0,
    open_date=NOW - timedelta(days=4),
    fee_open=fees,
    fee_close=fees,
    funding_fees=0.0,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag="120",
    liquidation_price=None,
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data("system_version", "system_v4")
  entry = fill(trade, "buy", 100.0, "120", 10.0, time=NOW - timedelta(days=3))
  if base_fee:
    entry.ft_fee_base = base_fee
    trade.recalc_trade_from_orders()
  gm0 = None
  if not initial_only:
    gm0 = fill(trade, "sell", trade.amount - 0.1, "gm0", 11.0, time=NOW - timedelta(days=2))
  return D1Case(configure(trade, enabled), trade, entry, gm0)


@pytest.fixture
def database():
  init_db("sqlite://")
  engine = Trade.session.get_bind()
  try:
    yield
  finally:
    Trade.session.rollback()
    Trade.session.remove()
    engine.dispose()


@pytest.fixture
def case(database):
  return make_d1()
