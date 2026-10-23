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


NOW = datetime(2026, 10, 21, 12, tzinfo=timezone.utc)


def add_order(trade, side, tag, amount, filled=None, status="closed"):
  filled = amount if filled is None else filled
  order = Order(
    order_id=str(len(trade.orders) + 1),
    ft_order_side=side,
    ft_pair=trade.pair,
    ft_is_open=status == "open",
    ft_amount=amount,
    ft_price=100.0,
    ft_order_tag=tag,
    status=status,
    side=side,
    order_type="limit",
    amount=amount,
    filled=filled,
    remaining=amount - filled,
    price=100.0,
    average=100.0,
    cost=filled * 100.0,
    order_date=NOW - timedelta(hours=8),
    order_filled_date=NOW - timedelta(hours=7),
  )
  trade.orders.append(order)
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  return order


@pytest.fixture(params=[(False, 1), (False, 3), (True, 3), (False, 4), (True, 4), (False, 5), (True, 5)])
def rescue_case(request):
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
  strategy.derisk_enable = False
  for name in dir(strategy):
    if name.startswith("system_v4_") and name.endswith("_enable"):
      setattr(strategy, name, False)
  strategy.system_v4_grind_5_liquidation_rescue_enable = True
  strategy.system_v4_grind_5_liquidation_rescue_threshold = 0.05
  strategy.system_v4_grind_5_liquidation_rescue_max_stake = 0.50
  strategy.system_v4_derisk_level_3_liquidation_enable = True
  strategy.system_v4_derisk_level_3_liquidation_distance = 0.05
  for level in range(1, 6):
    for mode in ("spot", "futures"):
      setattr(strategy, f"system_v4_grind_{level}_profit_threshold_{mode}", 10.0)
  strategy.long_grind_entry_v4 = MagicMock(return_value=False)
  strategy.short_grind_entry_v4 = MagicMock(return_value=False)
  strategy._bad_trade_controller_capitulation = MagicMock(return_value=False)
  strategy._bad_trade_controller_derisk_hold = MagicMock(return_value=True)
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.ticker = MagicMock(return_value={})
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="binance",
    is_short=short,
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
    enter_tag="501" if short else "1",
    liquidation_price=110.0 if short else 90.0,
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data("system_version", "system_v4")
  add_order(trade, trade.entry_side, "initial", 10.0)
  candle = {"close": 100.0, "RSI_3": 0.0, "RSI_3_15m": 0.0, "RSI_14": 50.0, "EMA_20": 100.0, "AROONU_14": 100.0}
  strategy.dp._set_cached_df(
    trade.pair, strategy.timeframe, pd.DataFrame([candle, candle]), strategy.config["candle_type_def"]
  )
  yield strategy, trade
  Trade.session.rollback()
  Trade.session.remove()


@pytest.fixture
def grind_case(rescue_case):
  strategy, trade = rescue_case
  strategy.system_v4_grind_5_enable = True
  add_order(trade, trade.exit_side, "exit_normal", 8.0)
  return strategy, trade


def adjust(case, move=0.06, min_stake=5.0, max_stake=10000.0):
  strategy, trade = case
  rate = 100.0 * (1 + move if trade.is_short else 1 - move)
  return strategy.adjust_trade_position(
    trade,
    NOW,
    rate,
    trade.calc_profit_ratio(rate),
    min_stake,
    max_stake,
    rate,
    rate,
    trade.calc_profit_ratio(rate),
    trade.calc_profit_ratio(rate),
  )


@pytest.mark.parametrize(
  "tag,count", [("grind_1_entry", 0), ("grind_1_entry", 1), ("rebuy_entry", 1), ("buyback_1_entry", 1)]
)
def test_rescue_adds_only_small_margin_with_at_most_one_subgrind(grind_case, tag, count):
  strategy, trade = grind_case
  entry_tag = "rebuy_entry" if trade.is_short and tag == "buyback_1_entry" else tag
  for _ in range(count):
    add_order(trade, trade.entry_side, entry_tag, 0.1)
  result = adjust(grind_case)
  if strategy.is_futures_mode:
    assert result == (pytest.approx(50.0 / trade.leverage), "grind_5_entry")
    assert strategy._grind_entry_tag == "g5_liq2"
  else:
    assert result is None


@pytest.mark.parametrize("tag", ["grind_1_entry", "rebuy_entry", "buyback_1_entry"])
def test_rescue_rejects_two_open_subgrinds(grind_case, tag):
  strategy, trade = grind_case
  entry_tag = "rebuy_entry" if trade.is_short and tag == "buyback_1_entry" else tag
  for _ in range(2):
    add_order(trade, trade.entry_side, entry_tag, 0.1)
  assert adjust(grind_case) is None


@pytest.mark.parametrize("move,threshold", [(0.05, 0.05), (0.04, 0.04), (0.049, 0.05)])
def test_rescue_adverse_threshold_is_strict(grind_case, move, threshold):
  strategy, trade = grind_case
  strategy.system_v4_grind_5_liquidation_rescue_threshold = threshold
  assert adjust(grind_case, move) is None


def test_four_percent_comparison_is_configurable(grind_case):
  strategy, trade = grind_case
  strategy.system_v4_grind_5_liquidation_rescue_threshold = 0.04
  result = adjust(grind_case, 0.045)
  assert result == ((pytest.approx(50.0 / trade.leverage), "grind_5_entry") if strategy.is_futures_mode else None)


@pytest.mark.parametrize("remaining,min_stake,allowed", [(4.5, 5.0, True), (4.6, 5.0, False), (4.45, 40.0, False)])
def test_rescue_caps_cost_basis_plus_minimum_uplift(rescue_case, remaining, min_stake, allowed):
  strategy, trade = rescue_case
  strategy.system_v4_grind_5_enable = True
  add_order(trade, trade.exit_side, "exit_normal", 10.0 - remaining)
  result = adjust(rescue_case, min_stake=min_stake / trade.leverage)
  assert result == (
    (pytest.approx(50.0 / trade.leverage), "grind_5_entry") if allowed and strategy.is_futures_mode else None
  )


@pytest.mark.parametrize("gate", ["switch", "timing", "wallet", "stake", "subgrinds", "open_order"])
def test_rescue_keeps_shared_entry_gates(grind_case, gate):
  strategy, trade = grind_case
  maximum = 10000.0
  if gate == "switch":
    strategy.system_v4_grind_5_liquidation_rescue_enable = False
  elif gate == "timing":
    trade.orders[0].order_filled_date = NOW - timedelta(minutes=4)
  elif gate == "wallet":
    maximum = 1.0
  elif gate == "stake":
    strategy.system_v4_max_stake = 0.1
  elif gate == "subgrinds":
    strategy.system_v4_grind_5_stakes_futures = [0.05]
    strategy.system_v4_grind_5_stakes_spot = [0.05]
    add_order(trade, trade.entry_side, "grind_5_entry", 0.1)
  else:
    add_order(trade, trade.entry_side, "grind_1_entry", 0.1, 0.0, "open")
  assert adjust(grind_case, max_stake=maximum) is None


@pytest.mark.parametrize("liquidation", [None, 0.0, -1.0, 50.0, 150.0])
def test_rescue_rejects_invalid_far_or_crossed_liquidation(grind_case, liquidation):
  strategy, trade = grind_case
  trade.liquidation_price = liquidation
  assert adjust(grind_case) is None


def test_normal_signal_precedes_rescue(grind_case):
  strategy, trade = grind_case

  def normal_signal(*args):
    strategy._grind_entry_tag = "normal"
    return True

  strategy.long_grind_entry_v4.side_effect = normal_signal
  strategy.short_grind_entry_v4.side_effect = normal_signal
  assert adjust(grind_case) == (pytest.approx(50.0 / trade.leverage), "grind_5_entry")
  assert strategy._grind_entry_tag == "normal"


@pytest.mark.parametrize("move,expected", [(0.15, "g5_liq2"), (0.151, "g5_liq1")])
def test_original_fifteen_percent_liquidation_entry_keeps_priority(grind_case, move, expected):
  strategy, trade = grind_case
  trade.liquidation_price = 120.0 if trade.is_short else 80.0
  result = adjust(grind_case, move)
  if strategy.is_futures_mode:
    assert result == (pytest.approx(50.0 / trade.leverage), "grind_5_entry")
    assert strategy._grind_entry_tag == expected
  else:
    assert result is None


@pytest.mark.parametrize("distance,expected", [(0.049, True), (0.05, True), (0.051, False)])
def test_emergency_derisk3_bypasses_hold_near_liquidation(rescue_case, distance, expected):
  strategy, trade = rescue_case
  strategy.derisk_enable = strategy.system_v4_derisk_level_3_enable = True
  rate = 106.0 if trade.is_short else 94.0
  trade.liquidation_price = rate / (1 - distance if trade.is_short else 1 + distance)
  result = adjust(rescue_case)
  assert result == (
    (pytest.approx(-500.0 / trade.leverage), "derisk_level_3") if expected and strategy.is_futures_mode else None
  )


@pytest.mark.parametrize("level", [1, 2])
def test_emergency_derisk3_precedes_ordinary_levels(rescue_case, level):
  strategy, trade = rescue_case
  strategy.derisk_enable = strategy.system_v4_derisk_level_3_enable = True
  setattr(strategy, f"system_v4_derisk_level_{level}_enable", True)
  setattr(strategy, f"system_v4_derisk_level_{level}_futures", [-0.01, -0.02])
  strategy._bad_trade_controller_derisk_hold.return_value = False
  trade.liquidation_price = 104.0 if trade.is_short else 96.0
  result = adjust(rescue_case, 0.02)
  if strategy.is_futures_mode:
    assert result == (pytest.approx(-500.0 / trade.leverage), "derisk_level_3")
  else:
    assert result is None


@pytest.mark.parametrize(
  "gate", ["global", "level", "emergency", "filled", "profit", "invalid", "missing", "far", "crossed", "rebuy"]
)
def test_emergency_derisk3_honors_exclusions(rescue_case, gate):
  strategy, trade = rescue_case
  strategy.derisk_enable = strategy.system_v4_derisk_level_3_enable = True
  move = 0.06
  if gate == "global":
    strategy.derisk_enable = False
  elif gate == "level":
    strategy.system_v4_derisk_level_3_enable = False
  elif gate == "emergency":
    strategy.system_v4_derisk_level_3_liquidation_enable = False
  elif gate == "filled":
    add_order(trade, trade.exit_side, "derisk_level_3", 5.0)
  elif gate == "profit":
    move = -0.01
    trade.liquidation_price = 100.0
  elif gate == "missing":
    trade.liquidation_price = None
  elif gate == "far":
    trade.liquidation_price = 150.0 if trade.is_short else 50.0
  elif gate == "crossed":
    trade.liquidation_price = 104.0 if trade.is_short else 96.0
  elif gate == "rebuy":
    trade.enter_tag = (strategy.short_rebuy_mode_tags if trade.is_short else strategy.long_rebuy_mode_tags)[0]
  else:
    trade.liquidation_price = 0.0
  assert adjust(rescue_case, move) is None


def test_emergency_derisk3_recovers_partial_fill_before_new_action(rescue_case):
  strategy, trade = rescue_case
  strategy.derisk_enable = strategy.system_v4_derisk_level_3_enable = True
  add_order(trade, trade.exit_side, "derisk_level_3", 5.0, 1.0, "canceled")
  assert adjust(rescue_case) == (pytest.approx(-400.0 / trade.leverage), "derisk_level_3")
