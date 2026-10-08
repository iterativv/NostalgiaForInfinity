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


NOW = datetime(2026, 10, 8, 12, tzinfo=timezone.utc)
EXIT_TAGS = (
  [f"derisk_level_{level}" for level in range(1, 5)]
  + ["derisk_global"]
  + [f"grind_{level}_{kind} 2" for level in range(1, 6) for kind in ("exit", "derisk")]
)


@pytest.fixture(params=[(False, 1.0), (False, 3.0), (True, 3.0)], ids=["spot", "long", "short"])
def partial_exit_case(request):
  init_db("sqlite://")
  is_short, leverage = request.param
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.config = {
    "stake_currency": "USDT",
    "runmode": RunMode.DRY_RUN,
    "timeframe": "5m",
    "candle_type_def": CandleType.FUTURES if leverage > 1 else CandleType.SPOT,
    "exchange": {"name": "binance"},
    "exit_pricing": {"price_side": "other"},
  }
  strategy.is_futures_mode = leverage > 1
  strategy.position_adjustment_enable = True
  strategy.derisk_enable = False
  for name in dir(strategy):
    if name.startswith("system_v4_") and name.endswith("_enable"):
      setattr(strategy, name, False)
  for level in range(1, 6):
    setattr(strategy, f"system_v4_grind_{level}_profit_threshold_spot", 10.0)
    setattr(strategy, f"system_v4_grind_{level}_profit_threshold_futures", 10.0)
  dataframe = pd.DataFrame([{"close": 100.0}, {"close": 100.0}])
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.ticker = MagicMock(return_value={})
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="binance",
    is_short=is_short,
    leverage=leverage,
    trading_mode=TradingMode.FUTURES if leverage > 1 else TradingMode.SPOT,
    amount=14.0,
    stake_amount=1400.0 / leverage,
    open_rate=100.0,
    open_date=NOW - timedelta(days=1),
    fee_open=0.001,
    fee_close=0.001,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag="501" if is_short else "1",
  )
  Trade.session.add(trade)
  Trade.session.flush()
  strategy.dp._set_cached_df(trade.pair, strategy.timeframe, dataframe, strategy.config["candle_type_def"])
  trade.set_custom_data("system_version", "system_v4")
  add_order(trade, trade.entry_side, "initial", 10.0, 10.0)
  add_order(trade, trade.entry_side, "grind_1_entry", 4.0, 4.0)
  yield strategy, trade
  Trade.session.rollback()
  Trade.session.remove()


def add_order(trade, side, tag, amount, filled, status="closed", price=100.0):
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
    order_date=NOW - timedelta(minutes=10),
    order_filled_date=NOW - timedelta(minutes=9),
  )
  trade.orders.append(order)
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  return order


def run_adjust(strategy, trade, rate=100.0, min_stake: float | None = 5.0):
  return strategy.adjust_trade_position(trade, NOW, rate, 0.0, min_stake, 10000.0, rate, rate, 0.0, 0.0)


@pytest.mark.parametrize("tag", EXIT_TAGS)
def test_partial_exit_retries_eligible_remainder(partial_exit_case, tag):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, tag, 4.0, 1.0, "canceled")

  result = run_adjust(strategy, trade)

  assert result == (-300.0 / trade.leverage, tag)


@pytest.mark.parametrize(
  "tag",
  [
    None,
    "",
    "exit_long_normal_1",
    "exit_short_normal_1",
    "force_exit",
    "partial_exit",
    "buyback_1_exit 2",
    "rebuy_exit 2",
    "grind_6_exit 2",
    "grind_1_exit_other 2",
  ],
)
def test_partial_exit_does_not_recover_normal_or_unrelated_exits(partial_exit_case, tag):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, tag, 4.0, 1.0, "canceled")

  result = run_adjust(strategy, trade)

  assert result is None


@pytest.mark.parametrize("filled,status", [(0.0, "canceled"), (4.0, "closed"), (1.0, "open")])
def test_partial_exit_does_not_retry_zero_full_or_open_order(partial_exit_case, filled, status):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, filled, status)

  result = run_adjust(strategy, trade)

  assert result is None


@pytest.mark.parametrize("rate", [80.0, 120.0])
def test_partial_exit_preserves_coin_amount_when_price_changes(partial_exit_case, rate):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")

  result = run_adjust(strategy, trade, rate)

  assert result[0] == pytest.approx(-300.0 / trade.leverage)
  assert -result[0] * trade.amount / trade.stake_amount == pytest.approx(3.0)


def test_partial_exit_retries_only_latest_remainder(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")
  add_order(trade, trade.exit_side, "grind_1_exit 2", 3.0, 1.0, "canceled")

  result = run_adjust(strategy, trade)

  assert result == (-200.0 / trade.leverage, "grind_1_exit 2")


def test_partial_exit_stops_after_remainder_fills(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")
  add_order(trade, trade.exit_side, "grind_1_exit 2", 3.0, 3.0)

  result = run_adjust(strategy, trade)

  assert result is None
  assert trade.amount == 10.0


def test_partial_exit_ignores_older_partial_after_normal_exit(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")
  add_order(trade, trade.exit_side, "exit_normal", 13.0, 1.0, "canceled")

  result = run_adjust(strategy, trade)

  assert result is None


def test_partial_exit_zero_fill_retry_keeps_original_remainder(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")
  add_order(trade, trade.exit_side, "grind_1_exit 2", 3.0, 0.0, "canceled")

  result = run_adjust(strategy, trade)

  assert result == (-300.0 / trade.leverage, "grind_1_exit 2")


def test_partial_exit_precedes_new_grind_entry(partial_exit_case):
  strategy, trade = partial_exit_case
  strategy.system_v4_grind_1_enable = True
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")
  trade.orders[-1].order_filled_date = NOW - timedelta(hours=7)
  strategy.long_grind_entry_v4 = MagicMock(return_value=True)
  strategy.short_grind_entry_v4 = MagicMock(return_value=True)

  result = run_adjust(strategy, trade)

  assert result == (-300.0 / trade.leverage, "grind_1_exit 2")


def test_partial_exit_below_minimum_is_not_enlarged(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 3.99, "canceled")

  result = run_adjust(strategy, trade)

  assert result is None


@pytest.mark.parametrize("status", ["canceled", "expired", "closed"])
def test_partial_exit_handles_terminal_states_and_missing_remaining(partial_exit_case, status):
  strategy, trade = partial_exit_case
  order = add_order(trade, trade.exit_side, "grind_1_derisk 2 17", 4.0, 1.0, status)
  order.remaining = None

  result = run_adjust(strategy, trade)

  assert result == (-300.0 / trade.leverage, "grind_1_derisk 2 17")


def test_partial_exit_can_finish_entire_remaining_trade(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "derisk_global", 14.0, 1.0, "canceled")

  result = run_adjust(strategy, trade)

  assert result == (-trade.stake_amount, "derisk_global")


def test_partial_exit_does_not_clip_recovery_and_lose_attribution(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 13.99, 1.0, "canceled")

  result = run_adjust(strategy, trade)

  assert result is None


def test_partial_exit_waits_for_other_open_order(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")
  add_order(trade, trade.entry_side, "grind_2_entry", 2.0, 0.0, "open")

  result = run_adjust(strategy, trade)

  assert result is None


def test_partial_exit_without_exchange_minimum(partial_exit_case):
  strategy, trade = partial_exit_case
  add_order(trade, trade.exit_side, "grind_1_exit 2", 4.0, 1.0, "canceled")

  result = run_adjust(strategy, trade, min_stake=None)

  assert result == (-300.0 / trade.leverage, "grind_1_exit 2")
