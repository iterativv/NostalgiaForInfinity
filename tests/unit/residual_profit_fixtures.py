"""Real SQLite ledger and Native cache fixtures for the R callback."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import CandleType, RunMode, TradingMode
from freqtrade.persistence import Order, Trade, init_db
from freqtrade.persistence.custom_data import CustomDataWrapper

import NostalgiaForInfinityX8 as MODULE
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8 as Strategy

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
KEY = "mh_r_first_target"
TARGET = "exit_profit_long_scalp_max"
REASON = "exit_r_first_profit_long_scalp_max"


@pytest.fixture
def database() -> Iterator[None]:
  with patch.object(CustomDataWrapper, "use_db", True):
    init_db("sqlite://")
    engine = Trade.session.get_bind()
    try:
      yield
    finally:
      Trade.session.rollback()
      Trade.session.remove()
      engine.dispose()


def fill(
  trade: Trade,
  side: str,
  quantity: float,
  price: float,
  requested: float | None = None,
  pending: bool = False,
) -> Order:
  amount = quantity if requested is None else requested
  stamp = NOW - timedelta(days=1) + timedelta(minutes=len(trade.orders))
  order = Order(
    order_id=f"{trade.id}-{len(trade.orders) + 1}",
    ft_order_side=side,
    ft_pair=trade.pair,
    ft_is_open=pending,
    ft_amount=amount,
    ft_price=price,
    ft_order_tag="r_fixture",
    status="open" if pending else ("closed" if amount == quantity else "canceled"),
    side=side,
    order_type="limit",
    amount=amount,
    filled=quantity,
    remaining=amount - quantity,
    price=price,
    average=price,
    cost=quantity * price,
    order_date=stamp,
    order_filled_date=None if pending else stamp,
  )
  trade.orders.append(order)
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  return order


@dataclass
class Case:
  strategy: Strategy
  trade: Trade
  native: MagicMock

  def analyzed(self, alarm=True, available=NOW, date=None) -> None:
    if date is None:
      date = NOW - timedelta(minutes=5)
    self.cache(
      pd.DataFrame(
        {
          "date": [date],
          "R_AVAILABLE_AT": [available],
          "R_UP_ALARM": [alarm],
        }
      )
    )

  def cache(self, frame) -> None:
    self.strategy.dp._set_cached_df(self.trade.pair, "5m", frame, self.strategy.config["candle_type_def"])
    if self.strategy.dp.runmode == RunMode.BACKTEST:
      self.strategy.dp._set_dataframe_max_index(self.trade.pair, len(frame))

  def target(
    self,
    reason: str = TARGET,
    stamp: datetime = NOW,
    profit: float = 0.02,
  ) -> None:
    self.strategy._set_profit_target(self.trade.pair, reason, 110.0, profit, stamp)

  def emit(self, reason: str = TARGET, stamp: datetime = NOW, profit: float = 0.02) -> None:
    def boundary(*args, **kwargs):
      self.target(reason, stamp, profit)
      return None

    self.native.side_effect = boundary

  def call(self, seconds: int = 0, rate: float = 110.0, **kwargs):
    return self.strategy.custom_exit(
      self.trade.pair,
      self.trade,
      NOW + timedelta(seconds=seconds),
      rate,
      self.trade.calc_profit_ratio(rate),
      **kwargs,
    )

  def marker(self):
    return self.trade.get_custom_data(key=KEY)

  def ledger(self, rate: float = 110.0) -> tuple[float, float, float, float]:
    _, entries, exits = self.strategy.filled_order_snapshot(self.trade)
    return self.strategy.calc_total_profit(self.trade, entries, exits, rate)


def make_case(tmp_path: Path, enabled: bool = True, short: bool = False, futures: bool = True) -> Case:
  strategy = Strategy.__new__(Strategy)
  strategy.is_futures_mode = futures
  strategy.risk_residual_first_target_exit_enable = enabled
  strategy.target_profit_cache = MODULE.Cache(tmp_path / "profit.json")
  strategy.config = {
    "runmode": RunMode.DRY_RUN,
    "timeframe": "5m",
    "stake_currency": "USDT",
    "candle_type_def": CandleType.FUTURES if futures else CandleType.SPOT,
    "trading_mode": "futures" if futures else "spot",
    "exchange": {"name": "binance"},
    "exit_pricing": {"price_side": "other"},
  }
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.get_analyzed_dataframe = MagicMock(wraps=strategy.dp.get_analyzed_dataframe)
  native = MagicMock(return_value=None)
  strategy._r_native_custom_exit = native
  trade = Trade(
    pair="ETH/USDT:USDT" if futures else "ETH/USDT",
    exchange="binance",
    is_short=short,
    leverage=3.0 if futures else 1.0,
    trading_mode=TradingMode.FUTURES if futures else TradingMode.SPOT,
    amount=0.0,
    stake_amount=0.0,
    open_rate=100.0,
    open_date=NOW - timedelta(days=2),
    fee_open=0.0005,
    fee_close=0.0005,
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
  trade.set_custom_data(key="system_version", value=strategy.system_v4_name)
  fill(trade, trade.entry_side, 10.0, 100.0, requested=12.0)
  case = Case(strategy, trade, native)
  case.analyzed()
  return case


def use_actual_scalp_tracker(case: Case) -> None:
  """Control unrelated indicators only; keep accounting and target writes real."""
  for name in ("long_exit_signals", "long_exit_main", "long_exit_williams_r", "long_exit_dec"):
    setattr(case.strategy, name, MagicMock(return_value=(False, None)))

  def boundary(pair, trade, current_time, current_rate, current_profit, **kwargs):
    _, entries, exits = case.strategy.filled_order_snapshot(trade)
    profits = case.strategy.calc_total_profit(trade, entries, exits, current_rate)
    candle = pd.Series({"close": current_rate})
    sell, reason = case.strategy.long_exit_scalp(
      pair,
      current_rate,
      *profits,
      0.0,
      0.0,
      entries,
      exits,
      candle,
      candle,
      trade,
      current_time,
      ["120"],
    )
    return reason if sell else None

  case.native.side_effect = boundary
