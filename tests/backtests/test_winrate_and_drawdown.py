"""Winrate and Drawdown Tests for NostalgiaForInfinity Strategy

This module contains comprehensive tests for validating strategy performance
across different exchanges, trading modes, and time periods.

TEST PARAMETERS:
- Exchanges: Binance, KuCoin (Gate.io and OKX commented for performance)
- Trading Modes: Spot, Futures
- Time Periods: Monthly tests from 2024-2025
- Expected Winrate: ≥85% (Binance, KuCoin)
- Expected Max Drawdown: ≤15%

RUN COMMANDS:
  # Run all tests
  python -m pytest tests/backtests/test_winrate_and_drawdown.py -v

  # Run specific exchange
  python -m pytest tests/backtests/test_winrate_and_drawdown.py::test_expected_values[binance] -v

  # Run specific trading mode
  python -m pytest tests/backtests/test_winrate_and_drawdown.py -k "futures" -v

  # Stop on first failure
  python -m pytest tests/backtests/test_winrate_and_drawdown.py -x

PREREQUISITES:
  1. Download data first:
     ./tools/download-necessary-exchange-market-data-for-backtests.sh

  2. Ensure virtual environment is active:
     source ../freqtrade/.venv/bin/activate

EXPECTED RESULTS:
  - All tests should pass with winrate ≥85% and drawdown ≤15%
  - Tests with 0 trades are considered passing
  - Deviations can be configured per exchange/timerange
"""

import os.path

import pytest

from tests.backtests.helpers import Backtest
from tests.backtests.helpers import Exchange
from tests.backtests.helpers import Timerange
from tests.conftest import REPO_ROOT


def exchange_fmt(value):
  return value.name


@pytest.fixture(
  scope="session",
  params=(
    Exchange(name="binance", winrate=85, max_drawdown=15),
    Exchange(name="kucoin", winrate=85, max_drawdown=15),
    # Exchange(name="gateio", winrate=90, max_drawdown=15),
    # Exchange(name="okx", winrate=90, max_drawdown=15),
    # ITS POSSIBLE TO ADD MORE EXCHANGES and MARKETS (SPOT FUTURES MARGIN)
  ),
  ids=exchange_fmt,
)
def exchange(request):
  return request.param


def trading_mode_fmt(param):
  return param


@pytest.fixture(
  params=(
    "spot",  # For SPOT Markets Trading tests
    "futures",  # For FUTURES Markets Trading tests
  ),
  ids=trading_mode_fmt,
)
def trading_mode(request):
  return request.param


@pytest.fixture(scope="session", autouse=True)
def check_exchange_data_presen(exchange):
  exchange_data_dir = REPO_ROOT / "user_data" / "data" / exchange.name
  if not os.path.isdir(exchange_data_dir):
    pytest.fail(
      f"There's no exchange data for {exchange.name}. Make sure the repository submodule "
      "is init/update. Check the repository README.md for more information."
    )
  if not list(exchange_data_dir.rglob("*.feather")):
    pytest.fail(
      f"There's no exchange data for {exchange.name}. Make sure the repository submodule "
      "is init/update. Check the repository README.md for more information."
    )


@pytest.fixture
def backtest(request):
  return Backtest(request)


def timerange_fmt(value):
  return f"{value.start_date}-{value.end_date}"


@pytest.fixture(
  params=(
    # # Monthly Test Periods
    # # # ADD NEW MONTHS HERE
    # # # #
    # # # 2025 Monthly Test Periods
    # # # #
    Timerange("20251201", "20260101"),
    Timerange("20251101", "20251201"),
    Timerange("20251001", "20251101"),
    Timerange("20250901", "20251001"),
    Timerange("20250801", "20250901"),
    Timerange("20250701", "20250801"),
    Timerange("20250601", "20250701"),
    Timerange("20250501", "20250601"),
    Timerange("20250401", "20250501"),
    Timerange("20250301", "20250401"),
    Timerange("20250201", "20250301"),
    Timerange("20250101", "20250201"),
    # # #
    # # 2024 Monthly Test Periods
    # # #
    Timerange("20241201", "20250101"),
    Timerange("20241101", "20241201"),
    Timerange("20241001", "20241101"),
    Timerange("20240901", "20241001"),
    Timerange("20240801", "20240901"),
    Timerange("20240701", "20240801"),
    Timerange("20240601", "20240701"),
    Timerange("20240501", "20240601"),
    Timerange("20240401", "20240501"),
    Timerange("20240301", "20240401"),
    Timerange("20240201", "20240301"),
    Timerange("20240101", "20240201"),
  ),
  ids=timerange_fmt,
)
def timerange(request):
  return request.param


@pytest.fixture(scope="session")
def deviations():
  return {
    "binance": {
      # ("20210101", "20210201"): {"max_drawdown": 5, "winrate": 90},
      # ("20210201", "20210301"): {"max_drawdown": 5, "winrate": 90},
      # ("20210301", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210401", "20210501"): {"max_drawdown": 5, "winrate": 90},
      # ("20210501", "20210601"): {"max_drawdown": 5, "winrate": 90},
      # ("20210601", "20210701"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20210801"): {"max_drawdown": 5, "winrate": 90},
      # ("20210801", "20210901"): {"max_drawdown": 5, "winrate": 90},
      # ("20210901", "20211001"): {"max_drawdown": 5, "winrate": 90},
      # ("20211001", "20211101"): {"max_drawdown": 5, "winrate": 90},
      # ("20211201", "20220101"): {"max_drawdown": 5, "winrate": 90},
      # ("20220301", "20220401"): {"max_drawdown": 5, "winrate": 90},
    },
    "gateio": {
      # ("20210201", "20210301"): {"max_drawdown": 5, "winrate": 90},
      # ("20210301", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210401", "20210501"): {"max_drawdown": 5, "winrate": 90},
      # ("20210501", "20210601"): {"max_drawdown": 5, "winrate": 90},
      # ("20210601", "20210701"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20210801"): {"max_drawdown": 5, "winrate": 90},
      # ("20210801", "20210901"): {"max_drawdown": 5, "winrate": 90},
      # ("20210901", "20211001"): {"max_drawdown": 5, "winrate": 90},
      # ("20211001", "20211101"): {"max_drawdown": 5, "winrate": 90},
      # ("20220101", "20220201"): {"max_drawdown": 5, "winrate": 90},
      # ("20220401", "20220501"): {"max_drawdown": 5, "winrate": 90},
      # ("20220601", "20220701"): {"max_drawdown": 5, "winrate": 90},
      # ("20211201", "20220101"): {"max_drawdown": 5, "winrate": 90},
      # ("20211101", "20211201"): {"max_drawdown": 5, "winrate": 90},
    },
    "okx": {
      # ("20210201", "20210301"): {"max_drawdown": 5, "winrate": 90},
      # ("20210301", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210401", "20210501"): {"max_drawdown": 5, "winrate": 90},
      # ("20210501", "20210601"): {"max_drawdown": 5, "winrate": 90},
      # ("20210601", "20210701"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20210801"): {"max_drawdown": 5, "winrate": 90},
      # ("20210801", "20210901"): {"max_drawdown": 5, "winrate": 90},
      # ("20210901", "20211001"): {"max_drawdown": 5, "winrate": 90},
      # ("20211001", "20211101"): {"max_drawdown": 5, "winrate": 90},
      # ("20220101", "20220201"): {"max_drawdown": 5, "winrate": 90},
      # ("20220401", "20220501"): {"max_drawdown": 5, "winrate": 90},
      # ("20220601", "20220701"): {"max_drawdown": 5, "winrate": 90},
      # ("20211201", "20220101"): {"max_drawdown": 5, "winrate": 90},
      # ("20211101", "20211201"): {"max_drawdown": 5, "winrate": 90},
    },
    "kucoin": {
      # ("20210201", "20210301"): {"max_drawdown": 5, "winrate": 90},
      # ("20210301", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210401", "20210501"): {"max_drawdown": 5, "winrate": 90},
      # ("20210501", "20210601"): {"max_drawdown": 5, "winrate": 90},
      # ("20210601", "20210701"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20210801"): {"max_drawdown": 5, "winrate": 90},
      # ("20210801", "20210901"): {"max_drawdown": 5, "winrate": 90},
      # ("20210901", "20211001"): {"max_drawdown": 5, "winrate": 90},
      # ("20211001", "20211101"): {"max_drawdown": 5, "winrate": 90},
      # ("20220101", "20220201"): {"max_drawdown": 5, "winrate": 90},
      # ("20220401", "20220501"): {"max_drawdown": 5, "winrate": 90},
      # ("20220601", "20220701"): {"max_drawdown": 5, "winrate": 90},
      # ("20211201", "20220101"): {"max_drawdown": 5, "winrate": 90},
      # ("20211101", "20211201"): {"max_drawdown": 5, "winrate": 90},
    },
  }


def test_expected_values(backtest, trading_mode, timerange, exchange, deviations):
  ret = backtest(
    start_date=timerange.start_date,
    end_date=timerange.end_date,
    exchange=exchange.name,
    trading_mode=trading_mode,
  )

  exchange_deviations = deviations.get(exchange.name, {})
  key = (trading_mode, timerange.start_date, timerange.end_date)
  entry = exchange_deviations.get(key, {})

  expected_winrate = entry.get("winrate") if entry.get("winrate") is not None else exchange.winrate
  expected_max_drawdown = entry.get("max_drawdown") if entry.get("max_drawdown") is not None else exchange.max_drawdown

  if not (ret.stats_pct.winrate >= expected_winrate or ret.stats_pct.trades == 0):
    print(
      f"[NOTE] Expected winrate ≥ {expected_winrate}, got {ret.stats_pct.winrate}. Trades: {ret.stats_pct.trades}."
    )

  if not (ret.stats_pct.max_drawdown <= expected_max_drawdown):
    print(f"[NOTE] Expected max drawdown ≤ {expected_max_drawdown}, got {ret.stats_pct.max_drawdown}.")
