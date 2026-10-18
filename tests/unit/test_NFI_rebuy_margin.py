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

from NostalgiaForInfinityX7 import NostalgiaForInfinityX7
from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
SYSTEMS = [
  (NostalgiaForInfinityX7, "legacy"),
  (NostalgiaForInfinityX7, "system_v3"),
  (NostalgiaForInfinityX8, "legacy"),
  (NostalgiaForInfinityX8, "system_v3"),
  (NostalgiaForInfinityX8, "system_v4"),
]


@pytest.fixture(params=SYSTEMS, ids=["x7-legacy", "x7-v3", "x8-legacy", "x8-v3", "x8-v4"])
def rebuy_system(request):
  return request.param


@pytest.fixture(params=[(False, 1.0), (False, 3.0), (True, 3.0)], ids=["spot", "long", "short"])
def rebuy_case(request, rebuy_system):
  init_db("sqlite://")
  strategy_type, system = rebuy_system
  is_short, leverage = request.param
  strategy = strategy_type.__new__(strategy_type)
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
  strategy.derisk_enable = True
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.ticker = MagicMock(return_value={})
  strategy.dp.send_msg = MagicMock()
  rate = 150.0 if is_short else 60.0
  candle = {
    "close": rate,
    "EMA_26": rate * (0.9 if is_short and system == "legacy" else 1.1),
    "RSI_3": 50.0,
    "RSI_3_15m": 50.0,
    "RSI_14": 70.0 if is_short else 30.0,
    "ROC_2": -1.0 if is_short else 1.0,
    "AROONU_14": 10.0,
    "AROONU_14_15m": 10.0,
    "AROOND_14": 10.0,
    "AROOND_14_15m": 10.0,
    "protections_long_global": True,
    "protections_short_global": True,
  }
  trade = Trade(
    pair="ETH/USDT:USDT" if leverage > 1 else "ETH/USDT",
    exchange="binance",
    is_short=is_short,
    leverage=leverage,
    trading_mode=TradingMode.FUTURES if leverage > 1 else TradingMode.SPOT,
    amount=12.0,
    stake_amount=1200.0 / leverage,
    open_rate=100.0,
    open_date=NOW - timedelta(days=1),
    fee_open=0.0,
    fee_close=0.0,
    funding_fees=0.0,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag="561" if is_short else "61",
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data("system_version", system)
  for price, tag in ((100.0, "initial"), (110.0 if is_short else 90.0, "r")):
    trade.orders.append(
      Order(
        order_id=str(len(trade.orders) + 1),
        ft_order_side=trade.entry_side,
        ft_pair=trade.pair,
        ft_is_open=False,
        ft_amount=12.0,
        ft_price=price,
        ft_order_tag=tag,
        status="closed",
        side=trade.entry_side,
        order_type="limit",
        amount=12.0,
        filled=12.0,
        remaining=0.0,
        price=price,
        average=price,
        cost=12.0 * price,
        order_date=NOW - timedelta(hours=2 - len(trade.orders)),
        order_filled_date=NOW - timedelta(hours=2 - len(trade.orders)),
      )
    )
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  dataframe = pd.DataFrame([candle, candle])
  strategy.dp._set_cached_df(trade.pair, "5m", dataframe, strategy.config["candle_type_def"])
  yield strategy, trade, rate, dataframe
  Trade.session.rollback()
  Trade.session.remove()


def run_adjust(strategy, trade, rate, max_stake, min_stake=5.0):
  return strategy.adjust_trade_position(trade, NOW, rate, 0.0, min_stake, max_stake, rate, rate, 0.0, 0.0)


def assert_derisk(result, trade, rate, min_stake=5.0):
  sell_margin = trade.amount * rate / trade.leverage - min_stake * 1.55
  expected = -sell_margin * trade.leverage * (trade.stake_amount / trade.amount) / rate
  assert result is not None
  assert result[1] == "derisk_level_3"
  assert result[0] == pytest.approx(expected)


@pytest.mark.parametrize("max_stake_fraction", [0.0, 0.5, 0.999, 1.0, 2.0])
def test_rebuy_uses_margin_limit_and_preserves_unfunded_hold(rebuy_case, max_stake_fraction):
  strategy, trade, rate, _ = rebuy_case
  strategy.derisk_enable = False
  rebuy_margin = 1200.0 / trade.leverage

  result = run_adjust(strategy, trade, rate, rebuy_margin * max_stake_fraction)

  if max_stake_fraction < 1.0:
    assert result is None
    strategy.dp.send_msg.assert_not_called()
  else:
    assert result == (rebuy_margin, "r")
    strategy.dp.send_msg.assert_called_once()


def test_rebuy_false_indicator_already_allows_derisk(rebuy_case):
  strategy, trade, rate, dataframe = rebuy_case
  dataframe["RSI_3"] = 100.0 if trade.is_short else 0.0

  result = run_adjust(strategy, trade, rate, 0.0)

  assert_derisk(result, trade, rate)


def test_unaffordable_rebuy_respects_disabled_derisk(rebuy_case):
  strategy, trade, rate, _ = rebuy_case
  strategy.derisk_enable = False

  result = run_adjust(strategy, trade, rate, 0.0)

  assert result is None
  strategy.dp.send_msg.assert_not_called()


def test_unaffordable_rebuy_respects_loss_threshold(rebuy_case):
  strategy, trade, _, _ = rebuy_case
  rate = 124.0 if trade.is_short else 78.0

  result = run_adjust(strategy, trade, rate, 0.0)

  assert result is None
  strategy.dp.send_msg.assert_not_called()


@pytest.mark.parametrize("max_stake", [6.25, 7.5, 8.75])
def test_rebuy_affordability_includes_minimum_order_uplift(rebuy_case, rebuy_system, max_stake):
  strategy, trade, rate, _ = rebuy_case
  strategy.derisk_enable = False
  _, system = rebuy_system
  prefix = "" if system == "legacy" else f"{system}_"
  market = "futures" if strategy.is_futures_mode else "spot"
  stakes_name = f"{prefix}rebuy_mode_stakes_{market}"
  stakes = list(getattr(strategy, stakes_name))
  stakes[1] = 0.001
  setattr(strategy, stakes_name, stakes)

  result = run_adjust(strategy, trade, rate, max_stake)

  if max_stake < 7.5:
    assert result is None
    strategy.dp.send_msg.assert_not_called()
  else:
    assert result == (7.5, "r")
    strategy.dp.send_msg.assert_called_once()


def test_open_order_still_prevents_rebuy_and_derisk(rebuy_case):
  strategy, trade, rate, _ = rebuy_case
  trade.orders[-1].ft_is_open = True
  trade.orders[-1].status = "open"

  result = run_adjust(strategy, trade, rate, 0.0)

  assert result is None
  strategy.dp.send_msg.assert_not_called()


def test_completed_derisk_preserves_existing_grind_handoff(rebuy_case, rebuy_system, mocker):
  strategy, trade, rate, _ = rebuy_case
  _, system = rebuy_system
  entry = trade.orders[-1]
  trade.orders.append(
    Order(
      order_id="derisk-filled",
      ft_order_side=trade.exit_side,
      ft_pair=trade.pair,
      ft_is_open=False,
      ft_amount=1.0,
      ft_price=rate,
      ft_order_tag="derisk_level_3",
      status="closed",
      side=trade.exit_side,
      order_type="limit",
      amount=1.0,
      filled=1.0,
      remaining=0.0,
      price=rate,
      average=rate,
      cost=rate,
      order_date=entry.order_filled_date + timedelta(minutes=5),
      order_filled_date=entry.order_filled_date + timedelta(minutes=5),
    )
  )
  Trade.session.flush()
  trade.recalc_trade_from_orders()
  direction = "short" if trade.is_short else "long"
  version = "v2" if system == "legacy" else system.removeprefix("system_")
  grind = mocker.patch.object(strategy, f"{direction}_grind_adjust_trade_position_{version}", return_value=None)

  result = run_adjust(strategy, trade, rate, 500.0)

  assert result is None
  grind.assert_called_once_with(
    trade, trade.enter_tag.split(), NOW, rate, 0.0, 5.0, 500.0 / trade.leverage, rate, rate, 0.0, 0.0
  )
