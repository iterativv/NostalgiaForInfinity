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
from freqtrade.persistence import Order
from freqtrade.persistence import Trade
from freqtrade.persistence.base import ModelBase
from freqtrade.persistence.custom_data import CustomDataWrapper
from freqtrade.persistence.custom_data import _CustomData
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session
from sqlalchemy.orm import sessionmaker

from NostalgiaForInfinityX8 import Cache
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
TARGET = "exit_profit_long_scalp_max"
REASON = "exit_g2_first_profit_long_scalp_max"
KEY = "mh_g2_first_target"


@pytest.fixture
def case(tmp_path, monkeypatch):
  engine = create_engine("sqlite://")
  ModelBase.metadata.create_all(engine)
  session = scoped_session(sessionmaker(bind=engine))
  with monkeypatch.context() as patch:
    for model in (Trade, Order, _CustomData):
      patch.setattr(model, "session", session, raising=False)
    patch.setattr(Trade, "use_db", True)
    patch.setattr(CustomDataWrapper, "use_db", True)
    patch.setattr(CustomDataWrapper, "custom_data", [])
    strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
    strategy.config = {
      "stake_currency": "USDT",
      "runmode": RunMode.DRY_RUN,
      "timeframe": "5m",
      "candle_type_def": CandleType.FUTURES,
      "exchange": {"name": "binance"},
    }
    strategy.is_futures_mode = True
    strategy.risk_market_relief_exit_enable = True
    strategy.target_profit_cache = Cache(tmp_path / "profit.json")
    strategy.dp = DataProvider(strategy.config, None)
    strategy._g2_native_custom_exit = MagicMock(return_value=None)
    trade = Trade(
      pair="ETH/USDT:USDT",
      exchange="binance",
      is_short=False,
      leverage=3.0,
      trading_mode=TradingMode.FUTURES,
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
    )
    session.add(trade)
    session.flush()
    trade.set_custom_data(key="system_version", value=strategy.system_v4_name)
    fill(trade, trade.entry_side, 10.0, 100.0, 12.0)
    reading(strategy, trade)
    try:
      yield strategy, trade
    finally:
      session.rollback()
      session.remove()
      engine.dispose()


def fill(trade, side, quantity, price, requested, pending=False):
  stamp = NOW - timedelta(days=1) + timedelta(minutes=len(trade.orders))
  order = Order(
    order_id=f"{trade.id}-{len(trade.orders)}",
    ft_order_side=side,
    ft_pair=trade.pair,
    ft_is_open=pending,
    ft_amount=requested,
    ft_price=price,
    status="open" if pending else "canceled",
    side=side,
    order_type="limit",
    amount=requested,
    filled=quantity,
    remaining=requested - quantity,
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


def reading(strategy, trade, stress=46.0, relief=80.0):
  frame = pd.DataFrame(
    {
      "date": [NOW - timedelta(minutes=10), NOW - timedelta(minutes=5)],
      "MKT_STRESS_1d": [99.0, stress],
      "MKT_RELIEF_1d": [100.0, relief],
    }
  )
  strategy.dp._set_cached_df(trade.pair, "5m", frame, CandleType.FUTURES)


def emit(strategy, trade, stamp=NOW, reason=TARGET, profit=0.02):
  def native(*args, **kwargs):
    strategy._set_profit_target(trade.pair, reason, 110.0, profit, stamp)
    return None

  strategy._g2_native_custom_exit.side_effect = native


def evaluate(strategy, trade, rate=110.0, stamp=NOW, **kwargs):
  return strategy.custom_exit(trade.pair, trade, stamp, rate, trade.calc_profit_ratio(rate), **kwargs)


def cash(strategy, trade, rate):
  _, entries, exits = strategy.filled_order_snapshot(trade)
  return strategy.calc_total_profit(trade, entries, exits, rate)[0]
