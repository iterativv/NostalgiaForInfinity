from datetime import datetime
from datetime import timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


@pytest.fixture
def exit_strategy():
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  candle = {
    "RSI_14": 10.0,
    "close": 95.0,
    "EMA_200": 100.0,
    "EMA_50": 100.0,
    "RSI_14_1h": 15.0,
    "BBL_20_2.0": 96.0,
    "BBL_20_2.0_1h": 96.0,
    "BB_BELOW_COUNT": 5,
  }
  dataframe = pd.DataFrame([candle, candle])
  strategy.dp = SimpleNamespace(get_analyzed_dataframe=lambda pair, timeframe: (dataframe, None))
  strategy.filled_order_snapshot = MagicMock(return_value=(["entry", "exit"], ["entry"], ["exit"]))
  strategy.calc_total_profit = MagicMock(return_value=(2.0, 0.02, 0.025, 0.03))
  strategy.cache_backtest_profit_snapshot = MagicMock()
  strategy.target_profit_cache = SimpleNamespace(data={}, save=MagicMock())
  strategy.short_exit_normal = MagicMock(return_value=(False, None))
  strategy.short_exit_scalp = MagicMock(return_value=(False, None))
  strategy.long_exit_top_coins = MagicMock(return_value=(False, None))
  strategy.short_exit_top_coins = MagicMock(wraps=strategy.short_exit_top_coins)
  return strategy


def run_custom_exit(strategy, enter_tag, is_short=True):
  trade = SimpleNamespace(
    pair="BTC/USDT:USDT",
    is_short=is_short,
    enter_tag=enter_tag,
    get_custom_data=lambda key: "system_v4",
  )
  current_time = datetime(2026, 9, 7, tzinfo=timezone.utc)
  return strategy.custom_exit(trade.pair, trade, current_time, 95.0, 0.02)


@pytest.mark.parametrize("enter_tag", ["641", "642", "641 642", "501 641", "641 661"])
def test_short_top_coins_reaches_existing_exit_signal(exit_strategy, enter_tag):
  reason = run_custom_exit(exit_strategy, enter_tag)

  assert reason == f"exit_short_tc_1_1_1 ( {enter_tag})"
  exit_strategy.short_exit_top_coins.assert_called_once()
  args = exit_strategy.short_exit_top_coins.call_args.args
  assert args[:11] == (
    "BTC/USDT:USDT",
    95.0,
    2.0,
    0.02,
    0.025,
    0.03,
    0.0,
    0.0,
    ["entry", "exit"],
    ["entry"],
    ["exit"],
  )
  assert args[-1] == enter_tag.split()
  assert exit_strategy.target_profit_cache.data["BTC/USDT:USDT"]["sell_reason"] == "exit_short_tc_1_1_1"
  if "501" not in enter_tag.split():
    exit_strategy.short_exit_normal.assert_not_called()
  exit_strategy.short_exit_scalp.assert_not_called()
  exit_strategy.long_exit_top_coins.assert_not_called()


@pytest.mark.parametrize("enter_tag", ["641", "642", "641 642"])
def test_short_top_coins_without_exit_keeps_its_profit_target(exit_strategy, enter_tag):
  # Every sub-handler of the top coins path is mocked: this test is about routing, not about
  # the candle columns the handlers read.
  exit_strategy.short_exit_signals = MagicMock(return_value=(False, None))
  exit_strategy.short_exit_main = MagicMock(return_value=(False, None))
  exit_strategy.short_exit_williams_r = MagicMock(return_value=(False, None))
  exit_strategy.short_exit_dec = MagicMock(return_value=(False, None))
  exit_strategy.short_exit_stoploss = MagicMock(return_value=(False, None))
  exit_strategy.short_exit_normal.return_value = (True, "exit_short_normal_test")

  assert run_custom_exit(exit_strategy, enter_tag) is None
  exit_strategy.short_exit_top_coins.assert_called_once()
  exit_strategy.short_exit_normal.assert_not_called()
  assert exit_strategy.target_profit_cache.data["BTC/USDT:USDT"]["sell_reason"] == "exit_profit_short_tc_max"


@pytest.mark.parametrize(
  "enter_tag,is_short,handler",
  [("141", False, "long_exit_top_coins"), ("501", True, "short_exit_normal"), ("unknown", True, "short_exit_normal")],
)
def test_other_exit_routes_are_preserved(exit_strategy, enter_tag, is_short, handler):
  exit_handler = getattr(exit_strategy, handler)
  exit_handler.return_value = (True, "existing_exit")

  assert run_custom_exit(exit_strategy, enter_tag, is_short) == f"existing_exit ( {enter_tag})"
  exit_handler.assert_called_once()
  exit_strategy.short_exit_top_coins.assert_not_called()
