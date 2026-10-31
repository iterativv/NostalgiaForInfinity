"""Real ORM ledgers and public callbacks for the legacy reentry admission policy."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import CandleType, RunMode, TradingMode
from freqtrade.persistence import Order, Trade, init_db

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 25, 12, tzinfo=timezone.utc)
FEATURE = "legacy_grind_derisk_reentry_hold_enable"


def strategy_for(trade: Trade, target: int | None = 1) -> NostalgiaForInfinityX8:
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.config = {
    "stake_currency": "USDT",
    "runmode": RunMode.BACKTEST,
    "timeframe": "5m",
    "candle_type_def": CandleType.FUTURES if trade.leverage > 1 else CandleType.SPOT,
    "exchange": {"name": "binance"},
    "exit_pricing": {"price_side": "other"},
  }
  strategy.is_futures_mode = trade.leverage > 1
  strategy.position_adjustment_enable = True
  strategy.derisk_enable = False
  setattr(strategy, FEATURE, True)
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.send_msg = MagicMock()
  strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  strategy.short_grind_entry = MagicMock(return_value=True)
  strategy.long_grind_entry_v4 = MagicMock(return_value=True)
  if target is not None:
    for queue in range(1, target):
      for market in ("spot", "futures"):
        setattr(strategy, f"grind_{queue}_stakes_{market}", [0.1])
  return strategy


def fill(
  trade: Trade,
  side: str,
  amount: float,
  tag: str,
  price: float = 100.0,
  filled: float | None = None,
  time: datetime | None = None,
  order_id: int | None = None,
) -> Order:
  executed = amount if filled is None else filled
  stamp = time or (NOW - timedelta(days=3) + timedelta(minutes=len(trade.orders)))
  order = Order(
    id=order_id,
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


def trade_for(leverage: float, tag: str = "120", short: bool = False) -> Trade:
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="binance",
    is_short=short,
    leverage=leverage,
    trading_mode=TradingMode.FUTURES if leverage > 1 else TradingMode.SPOT,
    amount=0.0,
    stake_amount=0.0,
    open_rate=100.0,
    open_date=NOW - timedelta(days=4),
    fee_open=0.0005,
    fee_close=0.0005,
    funding_fees=0.0,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag=tag,
    liquidation_price=None,
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data("system_version", "system_v4")
  return trade


@dataclass(frozen=True, slots=True)
class Case:
  strategy: NostalgiaForInfinityX8
  trade: Trade
  old: Order
  stop: Order

  def run(self, rate: float = 100.0, time: datetime = NOW) -> tuple[float, str] | None:
    frame = pd.DataFrame([{"close": rate}, {"close": rate}])
    candle_type = self.strategy.config["candle_type_def"]
    self.strategy.dp._set_cached_df(self.trade.pair, "5m", frame, candle_type)
    self.strategy.dp._set_dataframe_max_index(self.trade.pair, 2)
    profit = self.trade.calc_profit_ratio(rate)
    return self.strategy.adjust_trade_position(
      self.trade, time, rate, profit, 5.0, 100000.0, rate, rate, profit, profit
    )


def make_case(
  leverage: float = 3.0,
  target: int = 1,
  stop_queue: int = 1,
  stop_fraction: float = 1.0,
  old_amount: float = 1.0,
  tag: str = "120",
  short: bool = False,
) -> Case:
  trade = trade_for(leverage, tag, short)
  fill(trade, trade.entry_side, 1.0, tag)
  fill(trade, trade.exit_side, 0.9, "gm0")
  old_queue = next(n for n in range(1, 7) if n not in (target, stop_queue))
  old = fill(trade, trade.entry_side, old_amount, f"gd{old_queue}")
  stopped = fill(trade, trade.entry_side, 1.0, f"gd{stop_queue}")
  stop = fill(trade, trade.exit_side, 1.0, f"dd{stop_queue} {stopped.id}", filled=stop_fraction)
  # Earlier queues are legitimately at their configured one-entry capacity.
  # Empty stake lists are invalid in the native minimum-stake scaler.
  for queue in range(1, target):
    if queue != old_queue:
      fill(trade, trade.entry_side, 0.1, f"gd{queue}")
  return Case(strategy_for(trade, target), trade, old, stop)


def captured_crv() -> Case:
  """Use observed fills; signal is pinned true, funding is not historically replayed."""
  event = json.loads((Path(__file__).parent / "fixtures" / "legacy_reentry_crv.json").read_text())
  trade = trade_for(3.0)
  trade.pair = event["pair"]
  trade.open_date = datetime.fromisoformat(event["open_date"])
  for row in event["orders"]:
    fill(
      trade,
      row["side"],
      float(row["amount"]),
      row["tag"],
      float(row["price"]),
      time=datetime.fromisoformat(row["time"]),
      order_id=row["id"],
    )
  old = next(o for o in trade.orders if o.id == 402)
  stop = next(o for o in trade.orders if (o.ft_order_tag or "").startswith("dd1 "))
  return Case(strategy_for(trade, None), trade, old, stop)


@pytest.fixture
def database():
  previous_use_db = Trade.use_db
  Trade.use_db = True
  init_db("sqlite://")
  engine = Trade.session.get_bind()
  try:
    yield
  finally:
    Trade.session.rollback()
    Trade.session.remove()
    engine.dispose()
    Trade.use_db = previous_use_db
