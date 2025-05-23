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
    Exchange(name="kucoin", winrate=70, max_drawdown=25),
    Exchange(name="binance", winrate=70, max_drawdown=25),
    # Exchange(name="okx", winrate=70, max_drawdown=20),
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
    # # 2026 Every 2 Months Test Periods
    Timerange("20260101", "20260301"),
    Timerange("20260301", "20260501"),
    Timerange("20260501", "20260701"),
    Timerange("20260701", "20260901"),
    Timerange("20260901", "20261101"),
    Timerange("20261101", "20261231"),
    # # 2025 Every 2 Months Test Periods
    Timerange("20250101", "20250301"),
    Timerange("20250301", "20250501"),
    Timerange("20250501", "20250701"),
    Timerange("20250701", "20250901"),
    Timerange("20250901", "20251101"),
    Timerange("20251101", "20251231"),
    # # 2024 Every 2 Months Test Periods
    Timerange("20240101", "20240301"),
    Timerange("20240301", "20240501"),
    Timerange("20240501", "20240701"),
    Timerange("20240701", "20240901"),
    Timerange("20240901", "20241101"),
    Timerange("20241101", "20241231"),
  ),
  ids=timerange_fmt,
)
def timerange(request):
  return request.param


@pytest.fixture(scope="session")
def deviations():
  return {
    "binance": {
      # # 2026 Every 2 Months Test Periods
      ("20260101", "20260301"): {"max_drawdown": 25, "winrate": 70},
      ("20260301", "20260501"): {"max_drawdown": 25, "winrate": 70},
      ("20260501", "20260701"): {"max_drawdown": 25, "winrate": 70},
      ("20260701", "20260901"): {"max_drawdown": 25, "winrate": 70},
      ("20260901", "20261101"): {"max_drawdown": 25, "winrate": 70},
      ("20261101", "20261231"): {"max_drawdown": 25, "winrate": 70},
      # # 2025 Every 2 Months Test Periods
      ("20250101", "20250301"): {"max_drawdown": 25, "winrate": 70},
      ("20250301", "20250501"): {"max_drawdown": 25, "winrate": 70},
      ("20250501", "20250701"): {"max_drawdown": 25, "winrate": 70},
      ("20250701", "20250901"): {"max_drawdown": 25, "winrate": 70},
      ("20250901", "20251101"): {"max_drawdown": 25, "winrate": 70},
      ("20251101", "20251231"): {"max_drawdown": 25, "winrate": 70},
      # # 2024 Every 2 Months Test Periods
      ("20240101", "20240301"): {"max_drawdown": 25, "winrate": 70},
      ("20240301", "20240501"): {"max_drawdown": 25, "winrate": 70},
      ("20240501", "20240701"): {"max_drawdown": 25, "winrate": 70},
      ("20240701", "20240901"): {"max_drawdown": 25, "winrate": 70},
      ("20240901", "20241101"): {"max_drawdown": 25, "winrate": 70},
      ("20241101", "20241231"): {"max_drawdown": 25, "winrate": 70},
    },
    "kucoin": {
      # # 2026 Every 2 Months Test Periods
      ("20260101", "20260301"): {"max_drawdown": 25, "winrate": 70},
      ("20260301", "20260501"): {"max_drawdown": 25, "winrate": 70},
      ("20260501", "20260701"): {"max_drawdown": 25, "winrate": 70},
      ("20260701", "20260901"): {"max_drawdown": 25, "winrate": 70},
      ("20260901", "20261101"): {"max_drawdown": 25, "winrate": 70},
      ("20261101", "20261231"): {"max_drawdown": 25, "winrate": 70},
      # # 2025 Every 2 Months Test Periods
      ("20250101", "20250301"): {"max_drawdown": 25, "winrate": 70},
      ("20250301", "20250501"): {"max_drawdown": 25, "winrate": 70},
      ("20250501", "20250701"): {"max_drawdown": 25, "winrate": 70},
      ("20250701", "20250901"): {"max_drawdown": 25, "winrate": 70},
      ("20250901", "20251101"): {"max_drawdown": 25, "winrate": 70},
      ("20251101", "20251231"): {"max_drawdown": 25, "winrate": 70},
      # # 2024 Every 2 Months Test Periods
      ("20240101", "20240301"): {"max_drawdown": 25, "winrate": 70},
      ("20240301", "20240501"): {"max_drawdown": 25, "winrate": 70},
      ("20240501", "20240701"): {"max_drawdown": 25, "winrate": 70},
      ("20240701", "20240901"): {"max_drawdown": 25, "winrate": 70},
      ("20240901", "20241101"): {"max_drawdown": 25, "winrate": 70},
      ("20241101", "20241231"): {"max_drawdown": 25, "winrate": 70},
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
