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


NOW = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)


def fill(trade, side, amount, price, tag, filled=None):
  filled_at = trade.open_date_utc + timedelta(hours=12 * len(trade.orders))
  filled = amount if filled is None else filled
  trade.orders.append(
    Order(
      order_id=f"{trade.id}-{len(trade.orders) + 1}",
      ft_order_side=side,
      ft_pair=trade.pair,
      ft_is_open=False,
      ft_amount=amount,
      ft_price=price,
      ft_order_tag=tag,
      status="closed" if filled == amount else "canceled",
      side=side,
      order_type="limit",
      amount=amount,
      filled=filled,
      remaining=amount - filled,
      price=price,
      average=price,
      cost=filled * price,
      order_date=filled_at,
      order_filled_date=filled_at,
    )
  )
  Trade.session.flush()
  trade.recalc_trade_from_orders()


def adjust(case, max_stake, min_stake=5.0, current_time=NOW):
  strategy, trade, rate = case
  profit = trade.calc_profit_ratio(rate)
  return strategy.adjust_trade_position(
    trade, current_time, rate, profit, min_stake, max_stake, rate, rate, profit, profit
  )


def set_signal(strategy, value):
  strategy.long_grind_entry_v3 = MagicMock(return_value=value)
  strategy.short_grind_entry = MagicMock(return_value=value)


def expected_stop(trade, rate, min_stake=5.0):
  entries = [o for o in trade.orders if o.ft_order_side == trade.entry_side and o.ft_order_tag == "gd1"]
  quantity = min(sum(o.safe_filled for o in entries), trade.amount - min_stake * 1.55 * trade.leverage / rate)
  stake = quantity * trade.stake_amount / trade.amount
  tag = "dd1 " + " ".join(str(o.id) for o in reversed(entries))
  return -stake, tag


@pytest.fixture(params=[(False, 1), (False, 3), (True, 3)], ids=["spot", "long", "short"])
def legacy_grind_case(request):
  init_db("sqlite://")
  short, leverage = request.param
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
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.ticker = MagicMock(return_value={})
  strategy.dp.send_msg = MagicMock()
  set_signal(strategy, True)
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="binance",
    is_short=short,
    leverage=leverage,
    trading_mode=TradingMode.FUTURES if leverage > 1 else TradingMode.SPOT,
    amount=0.0,
    stake_amount=0.0,
    open_rate=100.0,
    open_date=NOW - timedelta(days=2),
    fee_open=0.0,
    fee_close=0.0,
    funding_fees=0.0,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag="620" if short else "120",
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data("system_version", "system_v4")
  fill(trade, trade.entry_side, 1.0, 100.0, trade.enter_tag)
  thresholds = strategy.grind_1_sub_thresholds_futures if leverage > 1 else strategy.grind_1_sub_thresholds_spot
  profit_move = strategy.grind_mode_first_entry_profit_threshold_spot + 0.01
  first_exit_rate = 100.0 * (1 - profit_move if short else 1 + profit_move)
  first_price = 110.0 if short else 90.0
  second_price = first_price * (1 - thresholds[1] + 0.01 if short else 1 + thresholds[1] - 0.01)
  # Seed the ledger using the strategy's own funded requests, not invented fills.
  for rate, tag in ((first_exit_rate, "gm0"), (first_price, "gd1"), (second_price, "gd1")):
    frame = pd.DataFrame([{"close": rate}, {"close": rate}])
    strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
    filled_at = trade.open_date_utc + timedelta(hours=12 * len(trade.orders))
    request = adjust((strategy, trade, rate), 1000.0, current_time=filled_at)
    assert isinstance(request, tuple) and request[1].split()[0] == tag
    amount = request[0] * leverage / rate if request[0] > 0 else -request[0] * trade.amount / trade.stake_amount
    fill(trade, trade.entry_side if request[0] > 0 else trade.exit_side, amount, rate, request[1])
  rate = second_price * (1 - thresholds[2] + 0.00125 if short else 1 + thresholds[2] - 0.00125)
  frame = pd.DataFrame([{"close": rate}, {"close": rate}])
  strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
  yield strategy, trade, rate
  engine = Trade.session.get_bind()
  Trade.session.rollback()
  Trade.session.remove()
  engine.dispose()


@pytest.mark.parametrize("funding_ratio", [0.0, 0.999, 1.0, 1.25])
@pytest.mark.parametrize("entry_signal", [False, True])
def test_funded_add_keeps_priority_otherwise_stop_runs(legacy_grind_case, funding_ratio, entry_signal):
  strategy, trade, rate = legacy_grind_case
  set_signal(strategy, entry_signal)
  entry_stake = 140.0 / trade.leverage

  result = adjust(legacy_grind_case, entry_stake * funding_ratio)

  if entry_signal and funding_ratio >= 1.0:
    assert result == (entry_stake, "gd1")
  else:
    stake, tag = expected_stop(trade, rate)
    assert result == (pytest.approx(stake), tag)


@pytest.mark.parametrize("funding_ratio", [0.0, 1.0])
def test_emergency_add_also_falls_through_when_unfunded(legacy_grind_case, funding_ratio):
  strategy, trade, _ = legacy_grind_case
  set_signal(strategy, False)
  rate = trade.orders[-1].safe_price * (1.30 if trade.is_short else 0.70)
  entry_stake = 140.0 / trade.leverage

  result = adjust((strategy, trade, rate), entry_stake * funding_ratio)

  if strategy.is_futures_mode and funding_ratio >= 1.0:
    assert result == (entry_stake, "gd1")
  else:
    stake, tag = expected_stop(trade, rate)
    assert result == (pytest.approx(stake), tag)


@pytest.mark.parametrize("funding_ratio", [0.999, 1.0])
def test_minimum_stake_uplift_is_included_in_budget(legacy_grind_case, funding_ratio):
  _, trade, _ = legacy_grind_case
  minimum = 140.0 / trade.leverage
  proposed = minimum * 1.5

  result = adjust(legacy_grind_case, proposed * funding_ratio, min_stake=minimum)

  assert result == ((proposed, "gd1") if funding_ratio >= 1.0 else None)


@pytest.mark.parametrize("version", ["system_v4", "system_v3_2", None])
def test_stored_system_keeps_legacy_grind_fallback(legacy_grind_case, version):
  _, trade, rate = legacy_grind_case
  trade.set_custom_data("system_version", version)

  result = adjust(legacy_grind_case, 0.0)

  stake, tag = expected_stop(trade, rate)
  assert result == (pytest.approx(stake), tag)


def test_disabled_grind_stops_do_not_create_an_exit(legacy_grind_case):
  strategy, _, _ = legacy_grind_case
  strategy.derisk_use_grind_stops = False

  assert adjust(legacy_grind_case, 0.0) is None


def test_open_order_blocks_additions_and_reductions(legacy_grind_case):
  _, trade, _ = legacy_grind_case
  trade.orders[-1].ft_is_open = True
  trade.orders[-1].status = "open"

  assert adjust(legacy_grind_case, 0.0) is None


@pytest.mark.parametrize("max_stake", [0.0, 1000.0])
def test_unfunded_rescue_does_not_consume_its_one_shot_flag(legacy_grind_case, max_stake):
  strategy, trade, rate = legacy_grind_case
  set_signal(strategy, False)
  strategy.derisk_use_grind_stops = False
  trade.liquidation_price = rate * (1.01 if trade.is_short else 0.99)

  result = adjust(legacy_grind_case, max_stake)

  if strategy.is_futures_mode and max_stake > 0.0:
    assert result is not None and result[0] > 0.0 and result[1] == "gd5"
    assert trade.get_custom_data("gd5_liquidation_rescue_used") is True
  else:
    assert result is None
    assert trade.get_custom_data("gd5_liquidation_rescue_used") is None


def test_partial_exit_recovery_precedes_entry_budget(legacy_grind_case):
  strategy, trade, rate = legacy_grind_case
  set_signal(strategy, False)
  requested = adjust(legacy_grind_case, 0.0)
  assert requested is not None and requested[0] < 0.0
  quantity = -requested[0] * trade.amount / trade.stake_amount
  fill(trade, trade.exit_side, quantity, rate, requested[1], filled=quantity / 2)

  retry = adjust(legacy_grind_case, 0.0)

  assert retry is not None and retry[1] == requested[1]
  assert -retry[0] * trade.amount / trade.stake_amount == pytest.approx(quantity / 2)
