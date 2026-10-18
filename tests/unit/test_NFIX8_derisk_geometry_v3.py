"""Unit tests for the size-aware de-risk ladder in the v3.2 engine functions.

The same frozen-anchor bug lived in long_grind_adjust_trade_position_v3 and
short_grind_adjust_trade_position_v3 (family system_v3_* / system_v3_2_*), so the fix is
asserted there too: the ladder is a price distance and must be measured on the current
position size. system_v3_2_derisk_level_1_futures = [-0.18, -0.35], the same numbers the
v4 and v2 engines use, so the expected rates are the ones of the other test modules.
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
# the ladder fires at the second element of system_v3_2_derisk_level_1_* (-0.35 of the
# notional): at 3x leverage that is a -11.67% price move. The first element (-0.18) only
# arms the level; it needs to stay armed for 96h before it fires on its own.

CANDLE_COLUMNS = (
  "AROOND_14", "AROOND_14_15m", "AROOND_14_1h", "AROOND_14_4h",
  "AROONU_14", "AROONU_14_15m", "AROONU_14_1d", "AROONU_14_1h",
  "AROONU_14_4h", "BBB_20_2.0_1h", "BBL_20_2.0", "BBL_20_2.0_1h",
  "BBU_20_2.0", "BBU_20_2.0_1h", "BB_ABOVE_COUNT", "BB_BELOW_COUNT",
  "BTC_RSI_14_4h", "CMF_20", "CMF_20_1h", "CMF_20_4h",
  "EMA_100", "EMA_100_4h", "EMA_12", "EMA_12_4h",
  "EMA_16", "EMA_20", "EMA_200", "EMA_200_4h",
  "EMA_26", "EMA_50", "EMA_50_4h", "EMA_9",
  "KST_10_15_20_30_10_10_10_15", "KSTs_9", "MFI_14", "ROC_2",
  "ROC_2_1d", "ROC_2_1h", "ROC_2_4h", "ROC_9",
  "ROC_9_15m", "ROC_9_1d", "ROC_9_1h", "ROC_9_4h",
  "RSI_14", "RSI_14_1h", "RSI_14_4h", "RSI_20",
  "RSI_3", "RSI_3_15m", "RSI_3_1d", "RSI_3_1h",
  "RSI_3_4h", "RSI_4", "SMA_16", "SMA_200_dec_12_1h",
  "SMA_200_dec_24", "SMA_200_dec_6_4h", "SMA_200_inc_12_1h", "SMA_200_inc_24",
  "SMA_200_inc_6_4h", "SMA_21", "SMA_30", "SMA_9",
  "STOCHRSIk_14_14_3_3", "STOCHRSIk_14_14_3_3_15m", "STOCHRSIk_14_14_3_3_1d", "STOCHRSIk_14_14_3_3_1h",
  "STOCHRSIk_14_14_3_3_4h", "WILLR_14", "WILLR_480", "WILLR_84_1h",
  "btc_pct_close_max_24_5m", "btc_pct_close_max_72_5m", "close", "close_max_12",
  "close_max_24", "close_max_48", "close_min_12", "close_min_48",
  "crossed_above_EMA_12_26", "crossed_below_EMA_12_26", "enter_long", "enter_short",
  "global_protections_long_dump", "global_protections_long_pump", "global_protections_short_dump", "global_protections_short_pump",
  "high_max_12_1h", "high_max_12_4h", "high_max_24_1h", "high_max_24_4h",
  "high_max_48_1h", "high_max_6_1h", "low_min_12_1h", "low_min_12_4h",
  "low_min_24_1h", "low_min_24_4h", "low_min_6_1h", "open",
  "protections_long_global", "protections_long_rebuy", "protections_short_global", "protections_short_rebuy",
)


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
def derisk_v3_case(request):
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
    if name.startswith("system_v"):
      if name.endswith("_enable"):
        setattr(strategy, name, False)
    if name.startswith("grinding_v2_") and name.endswith("_enable"):
      setattr(strategy, name, False)
  strategy.system_v3_2_derisk_level_1_enable = True
  for level in range(1, 6):
    setattr(strategy, f"system_v3_2_grind_{level}_profit_threshold_spot", 10.0)
    setattr(strategy, f"system_v3_2_grind_{level}_profit_threshold_futures", 10.0)

  # the v2 engine also reads the buyback indicators from the candle: neutral values keep
  # the buyback branches out of the way so the de-risk ladder is the code under test
  candle = dict.fromkeys(CANDLE_COLUMNS, 0.0)
  candle["open"] = OPEN_RATE
  candle["close"] = OPEN_RATE
  dataframe = pd.DataFrame([candle, candle])
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
    enter_tag="1",
  )
  Trade.session.add(trade)
  Trade.session.flush()
  strategy.dp._set_cached_df(trade.pair, strategy.timeframe, dataframe, strategy.config["candle_type_def"])
  # keep this position in the v3 engine functions (system_v3_2 family) instead of the v4 ones
  trade.set_custom_data("system_version", "system_v3_2")
  add_order(trade, trade.entry_side, "initial", ENTRY_AMOUNT)
  add_order(trade, trade.entry_side, "grind_1_entry", GRIND_AMOUNT)
  yield strategy, trade
  Trade.session.rollback()
  Trade.session.remove()


def loss_rate_for(trade, pct):
  """Rate that moves the position pct against it (long: down, short: up)."""
  return OPEN_RATE * (1.0 - pct) if not trade.is_short else OPEN_RATE * (1.0 + pct)


def run_adjust(strategy, trade, rate):
  return strategy.adjust_trade_position(trade, NOW, rate, 0.0, 5.0, 10000.0, rate, rate, 0.0, 0.0)


def test_v3_2_legacy_geometry_fires_before_the_intended_distance(derisk_v3_case):
  strategy, trade = derisk_v3_case
  strategy.derisk_size_aware_long = False
  strategy.derisk_size_aware_short = False

  # -10% move on the 1.4x position: -140 USDT, past the frozen -116.67 USDT level
  result = run_adjust(strategy, trade, loss_rate_for(trade, 0.10))

  assert result is not None
  assert result[1] == "derisk_level_1"


def test_v3_2_size_aware_geometry_waits_for_the_intended_distance(derisk_v3_case):
  strategy, trade = derisk_v3_case
  strategy.derisk_size_aware_long = True
  strategy.derisk_size_aware_short = True

  # same -10% move but the level now needs -11.67% on the current notional (-163.33 USDT)
  result = run_adjust(strategy, trade, loss_rate_for(trade, 0.10))

  assert result is None or result[1] != "derisk_level_1"


def test_v3_2_size_aware_geometry_fires_at_the_intended_distance(derisk_v3_case):
  strategy, trade = derisk_v3_case
  strategy.derisk_size_aware_long = True
  strategy.derisk_size_aware_short = True

  # -14% move = -196 USDT, past the intended -163.33 USDT level
  result = run_adjust(strategy, trade, loss_rate_for(trade, 0.14))

  assert result is not None
  assert result[1] == "derisk_level_1"
