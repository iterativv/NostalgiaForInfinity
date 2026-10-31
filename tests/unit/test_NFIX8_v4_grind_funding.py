from datetime import timedelta
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
from tests.unit.test_NFIX8_legacy_grind_funding import adjust
from tests.unit.test_NFIX8_legacy_grind_funding import fill
from tests.unit.test_NFIX8_legacy_grind_funding import NOW


@pytest.fixture(params=range(1, 6))
def level(request):
  return request.param


@pytest.fixture(params=[(False, 1.0), (False, 3.0), (True, 3.0)], ids=["spot", "long", "short"])
def v4_case(request, level):
  init_db("sqlite://")
  engine = Trade.session.get_bind()
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
  setattr(strategy, f"system_v4_grind_{level}_enable", True)
  setattr(strategy, f"system_v4_grind_{level}_use_derisk", True)
  for market in ("spot", "futures"):
    stakes = f"system_v4_grind_{level}_stakes_{market}"
    setattr(strategy, stakes, [0.15] * len(getattr(strategy, stakes)))
    setattr(strategy, f"system_v4_grind_{level}_derisk_{market}", -0.10)
  strategy.long_grind_entry_v4 = MagicMock(return_value=True)
  strategy.short_grind_entry_v4 = MagicMock(return_value=True)
  strategy.dp = DataProvider(strategy.config, None)
  strategy.dp.ticker = MagicMock(return_value={})
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
    fee_open=0.0,
    fee_close=0.0,
    amount_precision=8,
    price_precision=8,
    precision_mode=2,
    precision_mode_price=2,
    contract_size=1.0,
    enter_tag="501" if short else "1",
    liquidation_price=150.0 if short else 50.0,
  )
  Trade.session.add(trade)
  Trade.session.flush()
  trade.set_custom_data("system_version", "system_v4")
  fill(trade, trade.entry_side, 10.0, 100.0, "initial")
  fill(trade, trade.exit_side, 4.0, 100.0, "exit_normal")
  fill(trade, trade.entry_side, 1.0, 100.0, f"grind_{level}_entry")
  candle = {
    "close": 100.0,
    "RSI_3": 0.0,
    "RSI_3_15m": 0.0,
    "RSI_14": 50.0,
    "EMA_20": 100.0,
    "AROONU_14": 100.0,
    "AROOND_14": 100.0,
  }
  strategy.dp._set_cached_df(trade.pair, "5m", pd.DataFrame([candle, candle]), strategy.config["candle_type_def"])
  try:
    yield strategy, trade, 114.0 if short else 86.0
  finally:
    Trade.session.rollback()
    Trade.session.remove()
    engine.dispose()


@pytest.mark.parametrize("funding_ratio", [0.0, 0.999, 1.0, 1.25])
@pytest.mark.parametrize("entry_signal", [False, True])
def test_funded_add_keeps_priority_otherwise_existing_reduction_runs(v4_case, level, funding_ratio, entry_signal):
  strategy, trade, _ = v4_case
  strategy.long_grind_entry_v4 = MagicMock(return_value=entry_signal)
  strategy.short_grind_entry_v4 = MagicMock(return_value=entry_signal)
  proposal = 150.0 / trade.leverage

  result = adjust(v4_case, proposal * funding_ratio)

  if entry_signal and funding_ratio >= 1.0:
    assert result == (pytest.approx(proposal), f"grind_{level}_entry")
  else:
    assert result == (pytest.approx(-100.0 / trade.leverage), f"grind_{level}_derisk {trade.orders[-1].id}")


@pytest.mark.parametrize("funded", [False, True])
def test_affordability_includes_existing_minimum_uplift(v4_case, level, funded):
  _, trade, _ = v4_case
  minimum = 200.0 / trade.leverage
  proposal = minimum * 1.5
  budget = proposal if funded else 150.0 / trade.leverage

  result = adjust(v4_case, budget, min_stake=minimum)

  assert result == ((pytest.approx(proposal), f"grind_{level}_entry") if funded else None)


@pytest.mark.parametrize("level", [1])
def test_unfunded_add_allows_later_affordable_level(v4_case, level):
  strategy, trade, _ = v4_case
  strategy.system_v4_grind_1_use_derisk = False
  strategy.system_v4_grind_2_enable = True
  for market in ("spot", "futures"):
    name = f"system_v4_grind_2_stakes_{market}"
    setattr(strategy, name, [0.10] * len(getattr(strategy, name)))

  result = adjust(v4_case, 100.0 / trade.leverage)

  assert result == (pytest.approx(100.0 / trade.leverage), "grind_2_entry")


@pytest.mark.parametrize("level", [1])
def test_unfunded_add_with_no_later_action_returns_none(v4_case, level):
  strategy, _, _ = v4_case
  strategy.system_v4_grind_1_use_derisk = False

  result = adjust(v4_case, 0.0)

  assert result is None


@pytest.mark.parametrize("level", [1])
def test_open_order_prevents_another_action(v4_case, level):
  _, trade, _ = v4_case
  trade.orders.append(
    Order(
      order_id="pending",
      ft_order_side=trade.entry_side,
      ft_pair=trade.pair,
      ft_is_open=True,
      ft_amount=1.0,
      ft_price=100.0,
      ft_order_tag="grind_1_entry",
      status="open",
      side=trade.entry_side,
      order_type="limit",
      amount=1.0,
      filled=0.0,
      remaining=1.0,
      price=100.0,
      order_date=NOW,
    )
  )
  Trade.session.flush()

  result = adjust(v4_case, 0.0)

  assert result is None


@pytest.mark.parametrize("level", [1, 5])
def test_post_derisk_rebuy_handoff_reaches_existing_reduction(v4_case, level):
  _, trade, _ = v4_case
  trade.enter_tag = "561" if trade.is_short else "61"
  trade.orders[0].ft_order_tag = trade.enter_tag
  trade.orders[1].ft_order_tag = "derisk_level_3"

  result = adjust(v4_case, 0.0)

  assert result == (pytest.approx(-100.0 / trade.leverage), f"grind_{level}_derisk {trade.orders[-1].id}")


@pytest.mark.parametrize("level", [5])
@pytest.mark.parametrize("v4_case", [(False, 3.0), (True, 3.0)], indirect=True)
@pytest.mark.parametrize("funded", [False, True])
def test_liquidation_entry_keeps_funded_size_and_unfunded_fallthrough(v4_case, level, funded):
  strategy, trade, _ = v4_case
  strategy.long_grind_entry_v4 = MagicMock(return_value=False)
  strategy.short_grind_entry_v4 = MagicMock(return_value=False)
  trade.liquidation_price = 150.0 if trade.is_short else 70.0
  rate = 125.0 if trade.is_short else 75.0

  result = adjust((strategy, trade, rate), 1000.0 if funded else 0.0)

  assert result == (
    (pytest.approx(150.0 / trade.leverage), "grind_5_entry")
    if funded
    else (pytest.approx(-100.0 / trade.leverage), f"grind_5_derisk {trade.orders[-1].id}")
  )


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("v4_case", [(False, 3.0), (True, 3.0)], indirect=True)
def test_forced_derisk_keeps_priority_without_entry_funds(v4_case, level):
  strategy, trade, _ = v4_case
  strategy.derisk_enable = True
  strategy.system_v4_derisk_level_3_enable = True
  strategy.system_v4_derisk_level_3_liquidation_enable = True
  trade.liquidation_price = 104.0 if trade.is_short else 96.0
  rate = 102.0 if trade.is_short else 98.0

  result = adjust((strategy, trade, rate), 0.0)

  assert result == (pytest.approx(-500.0 / trade.leverage), "derisk_level_3")


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("funded", [False, True])
def test_pre_derisk_entry_preserves_funding_and_later_reduction(v4_case, level, funded):
  strategy, trade, _ = v4_case
  strategy.system_v4_grind_entry_before_derisk_enable = True
  strategy.long_grind_entry_v4 = MagicMock(return_value=False)
  strategy.short_grind_entry_v4 = MagicMock(return_value=False)
  strategy.system_v4_grind_2_use_derisk = True
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_2_derisk_{market}", -0.05)
  fill(trade, trade.entry_side, 1.0, 100.0, "grind_2_entry")
  rate = 109.0 if trade.is_short else 91.0
  proposal = 150.0 / trade.leverage

  result = adjust((strategy, trade, rate), proposal if funded else 0.0)

  if funded:
    assert result == (pytest.approx(proposal), "grind_1_entry")
  else:
    assert result == (pytest.approx(-100.0 / trade.leverage), f"grind_2_derisk {trade.orders[-1].id}")


@pytest.mark.parametrize("level", [1])
@pytest.mark.parametrize("entry_signal,funded", [(False, False), (True, False), (True, True)])
def test_unfunded_add_does_not_hide_profitable_grind_exit(v4_case, level, entry_signal, funded):
  strategy, trade, _ = v4_case
  strategy.system_v4_max_stake = 2.0
  strategy.dp.send_msg = MagicMock()
  strategy.long_grind_entry_v4 = MagicMock(return_value=entry_signal)
  strategy.short_grind_entry_v4 = MagicMock(return_value=entry_signal)
  fill(trade, trade.entry_side, 1.0, 50.0 if trade.is_short else 200.0, "grind_1_entry")
  rate = 70.0 if trade.is_short else 160.0
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(
    close=rate,
    RSI_3=0.0 if trade.is_short else 100.0,
    WILLR_14=-50.0,
    STOCHRSIk_14_14_3_3=50.0,
  )
  frame["BBU_20_2.0"] = rate * 2.0
  frame["BBL_20_2.0"] = rate / 2.0
  strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])
  proposal = 150.0 / trade.leverage

  result = adjust((strategy, trade, rate), proposal if funded else 0.0)

  if entry_signal and funded:
    assert result == (pytest.approx(proposal), "grind_1_entry")
  else:
    quantity_stake = (187.5 if trade.is_short else 225.0) / trade.leverage
    assert result == (pytest.approx(-quantity_stake), "grind_1_exit 4 3")
