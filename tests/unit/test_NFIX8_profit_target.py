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

from NostalgiaForInfinityX8 import Cache
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 9, 12, tzinfo=timezone.utc)


@pytest.fixture(
  params=[(False, 1.0, "144"), (False, 3.0, "144"), (False, 3.0, "163"), (True, 3.0, "641"), (True, 3.0, "661")],
  ids=["spot-tc", "long-tc", "long-scalp", "short-tc", "short-scalp"],
)
def profit_target_case(request, tmp_path):
  init_db("sqlite://")
  is_short, leverage, tag = request.param
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.config = {
    "stake_currency": "USDT",
    "runmode": RunMode.DRY_RUN,
    "timeframe": "5m",
    "candle_type_def": CandleType.FUTURES if leverage > 1 else CandleType.SPOT,
    "exchange": {"name": "bybit"},
    "exit_pricing": {"price_side": "other"},
  }
  strategy.is_futures_mode = leverage > 1
  strategy.hold_support_enabled = False
  strategy.derisk_enable = False
  strategy.system_v4_stops_enable = True
  strategy.target_profit_cache = Cache(tmp_path / "profit-target.json")
  # Isolate the target-based exit from unrelated indicator exit generators.
  for direction in ("long", "short"):
    for name in ("signals", "main", "williams_r", "dec", "stoploss"):
      setattr(strategy, f"{direction}_exit_{name}", MagicMock(return_value=(False, None)))
  strategy.dp = DataProvider(strategy.config, None)
  candle = {
    "RSI_14": 50.0,
    "CMF_20": 0.0,
    "CMF_20_1h": 0.0,
    "CMF_20_4h": 0.0,
    "ROC_9_4h": 0.0,
  }
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="bybit",
    is_short=is_short,
    leverage=leverage,
    trading_mode=TradingMode.FUTURES if leverage > 1 else TradingMode.SPOT,
    amount=10.0,
    stake_amount=1000.0 / leverage,
    open_rate=100.0,
    open_date=NOW - timedelta(days=1),
    fee_open=0.001,
    fee_close=0.001,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag=tag,
  )
  Trade.session.add(trade)
  Trade.session.flush()
  strategy.dp._set_cached_df(
    trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
  )
  add_order(trade, trade.entry_side, 10.0, 10.0, 100.0)
  strategy.order_filled(trade.pair, trade, trade.orders[-1], NOW)
  # Build the target through the actual custom-exit route at a profitable peak.
  assert evaluate_exit(strategy, trade, 96.0 if is_short else 104.0) is None
  assert strategy.target_profit_cache.data[trade.pair]["profit"] > 0.03
  yield strategy, trade
  Trade.session.rollback()
  Trade.session.remove()


def add_order(trade, side, amount, filled, price, status="closed", tag=None):
  order = Order(
    order_id=str(len(trade.orders) + 1),
    ft_order_side=side,
    ft_pair=trade.pair,
    ft_is_open=status == "open",
    ft_amount=amount,
    ft_price=price,
    ft_order_tag=tag,
    status=status,
    side=side,
    order_type="limit",
    amount=amount,
    filled=filled,
    remaining=amount - filled,
    price=price,
    average=price,
    cost=filled * price,
    order_date=NOW - timedelta(minutes=3),
    order_filled_date=NOW - timedelta(minutes=1) if filled else None,
  )
  trade.orders.append(order)
  Trade.session.flush()
  trade.update_trade(order)
  return order


def evaluate_exit(strategy, trade, rate=None):
  if rate is None:
    rate = 99.5 if trade.is_short else 100.5
  return strategy.custom_exit(trade.pair, trade, NOW, rate, trade.calc_profit_ratio(rate))


def approve_exit(strategy, trade, reason):
  return strategy.confirm_trade_exit(
    trade.pair, trade, "limit", trade.amount, 99.5 if trade.is_short else 100.5, "GTC", reason, NOW
  )


def test_profit_target_survives_exit_approval(profit_target_case):
  strategy, trade = profit_target_case
  target = strategy.target_profit_cache.data[trade.pair].copy()
  reason = evaluate_exit(strategy, trade)
  assert "_t_0_1" in reason

  assert approve_exit(strategy, trade, reason)

  assert strategy.target_profit_cache.data[trade.pair] == target
  assert Cache(strategy.target_profit_cache.path).data[trade.pair] == target


@pytest.mark.parametrize("filled", [0.0, 0.14, 0.35])
def test_profit_exit_repeats_after_canceled_order(profit_target_case, filled):
  strategy, trade = profit_target_case
  reason = evaluate_exit(strategy, trade)
  assert "_t_0_1" in reason
  assert approve_exit(strategy, trade, reason)
  order = add_order(
    trade, trade.exit_side, trade.amount, filled, 99.5 if trade.is_short else 100.5, "canceled", reason
  )
  if filled:
    strategy.order_filled(trade.pair, trade, order, NOW)
  assert trade.is_open
  assert trade.amount == pytest.approx(10.0 - filled)
  strategy.target_profit_cache = Cache(strategy.target_profit_cache.path)

  retry_reason = evaluate_exit(strategy, trade)

  assert retry_reason == reason


@pytest.mark.parametrize("reason", [None, "force_exit", "exit_profit_long_tc_t_0_1"])
def test_profit_target_clears_when_trade_closes(profit_target_case, reason):
  strategy, trade = profit_target_case
  order = add_order(trade, trade.exit_side, 10.0, 10.0, 100.0, tag=reason)
  assert not trade.is_open

  strategy.order_filled(trade.pair, trade, order, NOW)

  assert trade.pair not in strategy.target_profit_cache.data
  assert trade.pair not in Cache(strategy.target_profit_cache.path).data


def test_filled_partial_exit_keeps_open_trade_target(profit_target_case):
  strategy, trade = profit_target_case
  target = strategy.target_profit_cache.data[trade.pair].copy()
  order = add_order(trade, trade.exit_side, 2.0, 2.0, 100.5, tag="derisk_level_1")
  assert trade.is_open

  strategy.order_filled(trade.pair, trade, order, NOW)

  assert strategy.target_profit_cache.data[trade.pair] == target
  assert trade.get_custom_data("derisk_level_1") is True


def test_additional_entry_keeps_profit_target(profit_target_case):
  strategy, trade = profit_target_case
  target = strategy.target_profit_cache.data[trade.pair].copy()
  order = add_order(trade, trade.entry_side, 2.0, 2.0, 100.0, tag="grind_1_entry")

  strategy.order_filled(trade.pair, trade, order, NOW)

  assert strategy.target_profit_cache.data[trade.pair] == target


def test_rejected_exit_keeps_profit_target(profit_target_case):
  strategy, trade = profit_target_case
  target = strategy.target_profit_cache.data[trade.pair].copy()

  assert not approve_exit(strategy, trade, "stop_loss")

  assert strategy.target_profit_cache.data[trade.pair] == target


@pytest.mark.parametrize("amount", [2.0, 10.0])
def test_backtest_fill_clears_only_full_position_target(profit_target_case, amount):
  strategy, trade = profit_target_case
  strategy.config["runmode"] = RunMode.BACKTEST
  order = add_order(trade, trade.exit_side, amount, 0.0, 100.5, "open")
  # Backtesting calls order_filled before closing or resizing the LocalTrade.
  order.close_bt_order(NOW, trade)
  assert trade.is_open

  strategy.order_filled(trade.pair, trade, order, NOW)

  assert (trade.pair in strategy.target_profit_cache.data) == (amount < 10.0)
