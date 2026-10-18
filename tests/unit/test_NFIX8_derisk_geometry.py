"""Unit tests for the size-aware de-risk ladder geometry (fix-x8-derisk-escalation).

The de-risk levels are price distances measured on the position notional. Before the
fix the notional was frozen at the first entry (slice_amount), so every level moved
whenever the position changed size: it fired early after grinds (and could become
unreachable, i.e. beyond the liquidation price, after a partial de-risk cut).
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import CandleType, RunMode, TradingMode
from freqtrade.persistence import Order, Trade, init_db

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
ENTRY_AMOUNT = 10.0
GRIND_AMOUNT = 4.0
OPEN_RATE = 100.0


def add_order(trade, side, tag, amount):
  order = Order(
    order_id=str(len(trade.orders) + 1),
    ft_order_side=side,
    ft_pair=trade.pair,
    ft_is_open=False,
    ft_amount=amount,
    ft_price=OPEN_RATE,
    ft_order_tag=tag,
    status="closed",
    side=side,
    order_type="limit",
    amount=amount,
    filled=amount,
    remaining=0.0,
    price=OPEN_RATE,
    average=OPEN_RATE,
    cost=amount * OPEN_RATE,
    order_date=NOW - timedelta(minutes=10),
    order_filled_date=NOW - timedelta(minutes=9),
  )
  trade.orders.append(order)
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  return order


@pytest.fixture(params=[False, True], ids=["long", "short"])
def derisk_case(request):
  init_db("sqlite://")
  is_short = request.param
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.config = {
    "stake_currency": "USDT",
    "runmode": RunMode.DRY_RUN,
    "timeframe": "5m",
    "candle_type_def": CandleType.FUTURES,
    "exchange": {"name": "binance"},
    "exit_pricing": {"price_side": "other"},
  }
  strategy.is_futures_mode = True
  strategy.position_adjustment_enable = True
  strategy.derisk_enable = True
  for name in dir(strategy):
    if name.startswith("system_v4_") and name.endswith("_enable"):
      setattr(strategy, name, False)
  strategy.system_v4_derisk_level_1_enable = True
  for level in range(1, 6):
    setattr(strategy, f"system_v4_grind_{level}_profit_threshold_spot", 10.0)
    setattr(strategy, f"system_v4_grind_{level}_profit_threshold_futures", 10.0)

  dataframe = pd.DataFrame([{"close": OPEN_RATE}, {"close": OPEN_RATE}])
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.ticker = MagicMock(return_value={})
  trade = Trade(
    pair="ETH/USDT:USDT",
    exchange="binance",
    is_short=is_short,
    leverage=3.0,
    trading_mode=TradingMode.FUTURES,
    amount=ENTRY_AMOUNT,
    stake_amount=ENTRY_AMOUNT * OPEN_RATE / 3.0,
    open_rate=OPEN_RATE,
    open_date=NOW - timedelta(days=1),
    fee_open=0.0005,
    fee_close=0.0005,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    # an unknown short tag routes the position through short_grind_adjust_trade_position_v4
    enter_tag="700" if is_short else "1",
  )
  Trade.session.add(trade)
  Trade.session.flush()
  strategy.dp._set_cached_df(trade.pair, strategy.timeframe, dataframe, strategy.config["candle_type_def"])
  trade.set_custom_data("system_version", "system_v4")
  # first entry (slice_amount = 1000 USDT) plus one grind: the position is now 1.4x the slice
  add_order(trade, trade.entry_side, "initial", ENTRY_AMOUNT)
  add_order(trade, trade.entry_side, "grind_1_entry", GRIND_AMOUNT)
  yield strategy, trade
  Trade.session.rollback()
  Trade.session.remove()


def run_adjust(strategy, trade, rate):
  return strategy.adjust_trade_position(trade, NOW, rate, 0.0, 5.0, 10000.0, rate, rate, 0.0, 0.0)


def test_size_aware_flag_defaults_on():
  # the fix ships enabled: the legacy geometry is opt-in per instance
  assert NostalgiaForInfinityX8.derisk_size_aware_long is True
  assert NostalgiaForInfinityX8.derisk_size_aware_short is True


def test_legacy_geometry_fires_before_the_intended_distance(derisk_case):
  # position 14 units @100 (slice 10 units); a 10% move is -140 USDT,
  # above the intended -11.67% price distance but below the legacy one
  # (1000 * -0.35 / 3 = -116.67 USDT) measured on the frozen slice.
  strategy, trade = derisk_case
  strategy.derisk_size_aware_long = False
  strategy.derisk_size_aware_short = False

  # a long loses when the price falls, a short when it rises: same -10% move
  rate = 110.0 if trade.is_short else 90.0
  result = run_adjust(strategy, trade, rate)

  assert result is not None
  assert result[1] == "derisk_level_1"


def test_size_aware_geometry_waits_for_the_intended_distance(derisk_case):
  strategy, trade = derisk_case
  strategy.derisk_size_aware_long = True
  strategy.derisk_size_aware_short = True

  rate = 110.0 if trade.is_short else 90.0
  result = run_adjust(strategy, trade, rate)

  # same price, same trade: with the size-aware geometry level 1 is not reached yet
  assert result is None or result[1] != "derisk_level_1"


def test_size_aware_geometry_fires_at_the_intended_distance(derisk_case):
  # 15% move = -210 USDT < (14 * 100) * -0.35 / 3 = -163.33 USDT
  strategy, trade = derisk_case
  strategy.derisk_size_aware_long = True
  strategy.derisk_size_aware_short = True

  rate = 115.0 if trade.is_short else 85.0
  result = run_adjust(strategy, trade, rate)

  assert result is not None
  assert result[1] == "derisk_level_1"
