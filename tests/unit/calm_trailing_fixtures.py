"""Real SQLite ledger and Native cache fixtures for the M callback."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from freqtrade.enums import RunMode, TradingMode
from freqtrade.persistence import Order, Trade, init_db
from freqtrade.persistence.custom_data import CustomDataWrapper

import NostalgiaForInfinityX8 as MODULE
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8 as Strategy

NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)
KEY = "mh_m_calm_trail"
TARGET = "exit_profit_long_scalp_max"
REASON = "exit_m_calm_price_trail"


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
    ft_order_tag="m_fixture",
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


@dataclass(slots=True)
class Case:
  """Mutable callback fixture: reload tests replace its current Trade handle."""

  strategy: Strategy
  trade: Trade
  native: MagicMock

  def analyzed(self, stress: float | None = 19.0, relief: float = 80.0) -> None:
    self.strategy.dp.get_analyzed_dataframe.return_value = (
      pd.DataFrame(
        {
          "date": [NOW - timedelta(minutes=10), NOW - timedelta(minutes=5)],
          "MKT_STRESS_1d": [99.0, stress],
          "MKT_RELIEF_1d": [100.0, relief],
        }
      ),
      None,
    )

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

  def call(self, seconds: int = 0, rate: float = 110.0, current_profit: float | None = None, **kwargs):
    return self.strategy.custom_exit(
      self.trade.pair,
      self.trade,
      NOW + timedelta(seconds=seconds),
      rate,
      self.trade.calc_profit_ratio(rate) if current_profit is None else current_profit,
      **kwargs,
    )

  def marker(self):
    return self.trade.get_custom_data(key=KEY)

  def ledger(self, rate: float = 110.0) -> tuple[float, float, float, float]:
    _, entries, exits = self.strategy.filled_order_snapshot(self.trade)
    return self.strategy.calc_total_profit(self.trade, entries, exits, rate)


def make_case(tmp_path: Path, enabled: bool = True, short: bool = False, futures: bool = True) -> Case:
  tmp_path.mkdir(parents=True, exist_ok=True)
  strategy = Strategy.__new__(Strategy)
  strategy.is_futures_mode = futures
  strategy.risk_calm_trail_enable = enabled
  strategy.target_profit_cache = MODULE.Cache(tmp_path / "profit.json")
  strategy.dp = MagicMock()
  strategy.dp.runmode = RunMode.BACKTEST
  native = MagicMock(return_value=None)
  strategy._m_native_custom_exit = native
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
    enter_tag="161",
    liquidation_price=None,
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data(key="system_version", value=strategy.system_v4_name)
  fill(trade, trade.entry_side, 10.0, 100.0, requested=12.0)
  case = Case(strategy, trade, native)
  case.analyzed()
  return case


def target_call(case: Case, rate: float = 109.0, reason: str = TARGET):
  """Drive the real shared evaluator with the current cache's Native inputs."""
  target = case.strategy.target_profit_cache.data[case.trade.pair]
  _, entries, exits = case.strategy.filled_order_snapshot(case.trade)
  profits = case.strategy.calc_total_profit(case.trade, entries, exits, rate)
  candle = pd.Series({"RSI_14": 55.0, "CMF_20": 0.0, "CMF_20_1h": 0.0, "CMF_20_4h": 0.0, "ROC_9_4h": 0.0})
  return case.strategy.exit_profit_target(
    "long_scalp",
    case.trade.pair,
    case.trade,
    NOW,
    rate,
    *profits,
    candle,
    candle,
    target["rate"],
    target["profit"],
    reason,
    datetime.fromisoformat(target["time_profit_reached"]),
    ["161"],
  )


def actual_native(case: Case) -> None:
  """Keep full Native dispatch, accounting, cache and target evaluator real."""
  for name in ("long_exit_signals", "long_exit_main", "long_exit_williams_r", "long_exit_dec"):
    setattr(case.strategy, name, MagicMock(return_value=(False, None)))
  case.strategy.system_v4_bad_trade_exit_enable = False
  case.strategy.system_v4_stops_enable = False
  case.trade.enter_tag = "161"
  frame, _ = case.strategy.dp.get_analyzed_dataframe.return_value
  for name, value in {"RSI_14": 55.0, "CMF_20": 0.0, "CMF_20_1h": 0.0, "CMF_20_4h": 0.0, "ROC_9_4h": 0.0}.items():
    frame[name] = value
  case.native.side_effect = lambda *args, **kwargs: Strategy._m_native_custom_exit(case.strategy, *args, **kwargs)


def order_ledger(case: Case) -> tuple[tuple[tuple[str, object], ...], ...]:
  """Compare every persisted Order column, not a reconstructed fill estimate."""
  return tuple(
    tuple((column.name, getattr(order, column.name)) for column in Order.__table__.columns)
    for order in case.trade.orders
  )
