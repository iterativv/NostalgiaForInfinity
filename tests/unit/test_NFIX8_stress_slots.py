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

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
PAIR = "NEW/USDT:USDT"


@pytest.fixture
def strategy(monkeypatch):
  engine = create_engine("sqlite://")
  ModelBase.metadata.create_all(engine)
  session = scoped_session(sessionmaker(bind=engine))
  with monkeypatch.context() as patch:
    for model in (Trade, Order, _CustomData):
      patch.setattr(model, "session", session, raising=False)
    patch.setattr(Trade, "use_db", True)
    patch.setattr(CustomDataWrapper, "use_db", True)
    patch.setattr(CustomDataWrapper, "custom_data", [])
    instance = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
    instance.config = {
      "stake_currency": "USDT",
      "runmode": RunMode.DRY_RUN,
      "timeframe": "5m",
      "candle_type_def": CandleType.FUTURES,
      "exchange": {"name": "binance"},
      "max_open_trades": 10,
    }
    instance.is_futures_mode = True
    instance.futures_max_open_trades_long = 0
    instance.futures_max_open_trades_short = 0
    instance.risk_long_slot_cap_enable = True
    instance.dp = DataProvider(instance.config, None)
    reading(instance)
    try:
      yield instance
    finally:
      session.rollback()
      session.remove()
      engine.dispose()


def reading(strategy, stress=46.0, absent=False, empty=False):
  frame = pd.DataFrame([{"date": NOW - timedelta(minutes=5), "close": 100.0}])
  if not absent:
    frame["MKT_STRESS_1d"] = stress
  if empty:
    frame = frame.iloc[:0]
  strategy.dp._set_cached_df(PAIR, "5m", frame, CandleType.FUTURES)


def admit(strategy, side="long", rate=100.0, tag="1", **kwargs):
  return strategy.confirm_trade_entry(PAIR, "limit", 1.0, rate, "GTC", NOW, tag, side, **kwargs)


def order(trade, executed=1.0, pending=False):
  stamp = NOW - timedelta(hours=1)
  entry = Order(
    order_id=f"{trade.id}-{len(trade.orders)}",
    ft_order_side=trade.entry_side,
    ft_pair=trade.pair,
    ft_is_open=pending,
    ft_amount=1.0,
    ft_price=100.0,
    status="open" if pending else "closed",
    side=trade.entry_side,
    order_type="limit",
    amount=1.0,
    filled=executed,
    remaining=1.0 - executed,
    price=100.0,
    average=100.0 if executed else None,
    cost=executed * 100.0,
    order_date=stamp,
    order_filled_date=stamp if executed else None,
  )
  trade.orders.append(entry)
  Trade.session.flush()
  if executed:
    trade.recalc_trade_from_orders()
  return entry


def slot(index, short=False, pending=False, opened=True, pair=None, filled=None):
  trade = Trade(
    pair=pair or f"SLOT{index}/USDT:USDT",
    exchange="binance",
    is_short=short,
    is_open=opened,
    leverage=3.0,
    trading_mode=TradingMode.FUTURES,
    amount=0.0,
    stake_amount=0.0,
    open_rate=100.0,
    open_date=NOW - timedelta(days=1),
    fee_open=0.0005,
    fee_close=0.0005,
    funding_fees=0.0,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag="1",
  )
  Trade.session.add(trade)
  Trade.session.flush()
  executed = (0.0 if pending else 1.0) if filled is None else filled
  order(trade, executed, pending)
  return trade


def ledger():
  return [
    (
      trade.id,
      trade.pair,
      trade.is_short,
      trade.is_open,
      trade.amount,
      trade.stake_amount,
      tuple(
        (item.id, item.status, item.ft_is_open, item.safe_amount, item.safe_filled, item.safe_remaining)
        for item in trade.orders
      ),
    )
    for trade in Trade.get_trades_proxy()
  ]


@pytest.mark.parametrize("count,allowed", [(0, True), (3, True), (4, False), (6, False)])
@pytest.mark.parametrize("pending", [False, True])
def test_four_open_or_pending_longs_block_only_new_fifth(strategy, count, allowed, pending):
  slots = [slot(index, pending=pending) for index in range(count)]
  if pending:
    assert all(item.orders[0].safe_filled == 0.0 and item.orders[0].ft_is_open for item in slots)
  before = ledger()
  assert admit(strategy) is allowed
  assert ledger() == before
  assert strategy.config["max_open_trades"] == 10


@pytest.mark.parametrize("score", [45.0, 44.9999, None, float("nan"), float("inf"), -float("inf")])
def test_equality_or_unknown_stress_preserves_native_approval(strategy, score):
  for index in range(4):
    slot(index)
  reading(strategy, score)
  assert admit(strategy) is True


@pytest.mark.parametrize("absent,empty", [(True, False), (False, True)])
def test_unavailable_market_reading_does_not_block(strategy, absent, empty):
  for index in range(4):
    slot(index)
  reading(strategy, absent=absent, empty=empty)
  assert admit(strategy) is True


def test_partial_initial_fill_counts_one_trade_not_orders_or_short_positions(strategy):
  for index in range(3):
    slot(index)
  partial = slot(3, pending=True, filled=0.25)
  order(partial, 0.0, True)
  order(partial, 0.2, True)
  slot(4, short=True, pair=PAIR)
  slot(5, opened=False)
  assert partial.orders[0].safe_filled == 0.25
  assert partial.orders[0].safe_remaining == 0.75
  before = ledger()
  assert admit(strategy) is False
  assert admit(strategy, side="short", tag="501") is True
  assert ledger() == before


def test_short_and_closed_records_do_not_consume_long_slots(strategy):
  for index in range(3):
    slot(index)
  for index in range(3, 8):
    slot(index, short=True, pending=True)
  slot(8, opened=False)
  assert admit(strategy) is True


@pytest.mark.parametrize("pending", [False, True])
def test_existing_long_pair_is_not_new_admission(strategy, pending):
  for index in range(4):
    slot(index)
  slot(4, pair=PAIR, pending=pending)
  before = ledger()
  assert admit(strategy) is True
  assert ledger() == before


def test_same_pair_short_does_not_exempt_new_long(strategy):
  for index in range(4):
    slot(index)
  slot(4, pair=PAIR, short=True)
  assert admit(strategy) is False


def test_native_slippage_rejection_precedes_market_work(strategy, monkeypatch):
  for index in range(4):
    slot(index)
  read = MagicMock(wraps=strategy.dp.get_analyzed_dataframe)
  monkeypatch.setattr(strategy.dp, "get_analyzed_dataframe", read)
  assert admit(strategy, rate=200.0) is False
  read.assert_called_once_with(PAIR, "5m")


def test_native_mode_rejection_precedes_market_work(strategy, monkeypatch):
  strategy.grind_mode_coins = []
  monkeypatch.setattr(strategy.dp, "get_analyzed_dataframe", MagicMock(side_effect=AssertionError))
  assert admit(strategy, tag=strategy.long_grind_mode_tags[0]) is False


@pytest.mark.parametrize("mode", ["grind", "top_coins", "scalp", "force_entry"])
def test_native_approved_early_return_still_obeys_new_long_cap(strategy, mode):
  for index in range(4):
    slot(index)
  strategy.grind_mode_coins = ["NEW"]
  strategy.grind_mode_max_slots = 10
  strategy.top_coins_mode_coins = ["NEW"]
  strategy.min_free_slots_scalp_mode = 0
  tags = {
    "grind": strategy.long_grind_mode_tags[0],
    "top_coins": strategy.long_top_coins_mode_tags[0],
    "scalp": strategy.long_scalp_mode_tags[0],
    "force_entry": "force_entry",
  }
  tag = tags[mode]
  assert strategy._b_native_confirm_trade_entry(PAIR, "limit", 1.0, 100.0, "GTC", NOW, tag, "long")
  before = ledger()
  assert admit(strategy, tag=tag) is False
  assert ledger() == before


@pytest.mark.parametrize("enabled,side", [(False, "long"), (False, "short"), (True, "short")])
def test_off_or_short_adds_no_market_read_or_trade_query(strategy, monkeypatch, enabled, side):
  strategy.risk_long_slot_cap_enable = enabled
  native = MagicMock(return_value=True)
  monkeypatch.setattr(strategy, "_b_native_confirm_trade_entry", native)
  monkeypatch.setattr(strategy.dp, "get_analyzed_dataframe", MagicMock(side_effect=AssertionError))
  monkeypatch.setattr(Trade, "get_trades_proxy", MagicMock(side_effect=AssertionError))
  assert admit(strategy, side=side, future_framework_value=17) is True
  native.assert_called_once_with(
    PAIR,
    "limit",
    1.0,
    100.0,
    "GTC",
    NOW,
    "1",
    side,
    future_framework_value=17,
  )
