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
    Exchange(name="binance", winrate=90, max_drawdown=5),
    Exchange(name="kucoin", winrate=90, max_drawdown=5),
    # Exchange(name="gateio", winrate=90, max_drawdown=5),
    # Exchange(name="okx", winrate=90, max_drawdown=5),
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
    # "spot",  # For SPOT Markets Trading tests
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
    # # Quarterly Test Periods
    # # # ADD NEW QUARTER PERIODS HERE
    # # 2025 Quarterly Test Periods
    # # #
    Timerange("20251001", "20260101"),
    Timerange("20250701", "20251001"),
    Timerange("20250401", "20250701"),
    Timerange("20250101", "20250401"),
    # # 2024 Quarterly Test Periods
    # # #
    Timerange("20241001", "20250101"),
    Timerange("20240701", "20241001"),
    Timerange("20240401", "20240701"),
    Timerange("20240101", "20240401"),
    # # #
    # # 2023 Quarterly Test Periods
    # # #
    Timerange("20231001", "20240101"),
    Timerange("20230701", "20231001"),
    Timerange("20230401", "20230701"),
    Timerange("20230101", "20230401"),
    # # #
    # # 2022 Quarterly Test Periods
    # # #
    Timerange("20221001", "20230101"),
    Timerange("20220701", "20221001"),
    Timerange("20220401", "20220701"),
    Timerange("20220101", "20220401"),
    # # #
    # # 2021 Quarterly Test Periods
    # # #
    Timerange("20211001", "20220101"),
    Timerange("20210701", "20211001"),
    Timerange("20210401", "20210701"),
    Timerange("20210101", "20220401"),
    # # #
    # # 2020 Quarterly Test Periods
    # # #
    Timerange("20201001", "20210101"),
    Timerange("20200701", "20201001"),
    Timerange("20200401", "20200701"),
    Timerange("20200101", "20200401"),
    # # #
  ),
  ids=timerange_fmt,
)
def timerange(request):
  return request.param


@pytest.fixture(scope="session")
def deviations():
  return {
    "binance": {
      # ("20221001", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20211001"): {"max_drawdown": 5, "winrate": 90},
    },
    "gateio": {
      # ("20221001", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20211001"): {"max_drawdown": 5, "winrate": 90},
    },
    "okx": {
      # ("20221001", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20211001"): {"max_drawdown": 5, "winrate": 90},
    },
    "kucoin": {
      # ("20221001", "20210401"): {"max_drawdown": 5, "winrate": 90},
      # ("20210701", "20211001"): {"max_drawdown": 5, "winrate": 90},
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
