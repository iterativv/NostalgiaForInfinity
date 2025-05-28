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
    # # # First Test Periods
    # # # #
    # # # These are well known bad market situations
    # # # #
    Timerange("20240810", "20240825"),
    Timerange("20200511", "20200523"),
  ),
  ids=timerange_fmt,
)
def timerange(request):
  return request.param


@pytest.fixture(scope="session")
def deviations():
  return {
    "binance": {
      ("20240810", "20240825"): {"max_drawdown": 5, "winrate": 90},
      ("20200511", "20200523"): {"max_drawdown": 5, "winrate": 90},
    },
    "gateio": {
      ("20240810", "20240825"): {"max_drawdown": 5, "winrate": 90},
      ("20200511", "20200523"): {"max_drawdown": 5, "winrate": 90},
    },
    "okx": {
      ("20240810", "20240825"): {"max_drawdown": 5, "winrate": 90},
      ("20200511", "20200523"): {"max_drawdown": 5, "winrate": 90},
    },
    "kucoin": {
      ("20240810", "20240825"): {"max_drawdown": 5, "winrate": 90},
      ("20200511", "20200523"): {"max_drawdown": 5, "winrate": 90},
    },
  }


def test_expected_values(backtest, trading_mode, timerange, exchange, deviations):
  ret = backtest(
    start_date=timerange.start_date,
    end_date=timerange.end_date,
    exchange=exchange.name,
    trading_mode=trading_mode,
  )
  exchange_deviations = deviations[exchange.name]
  expected_winrate = (
    exchange_deviations.get((trading_mode, timerange.start_date, timerange.end_date), {}).get("winrate")
    or exchange.winrate
  )
  expected_max_drawdown = (
    exchange_deviations.get((trading_mode, timerange.start_date, timerange.end_date), {}).get("max_drawdown")
    or exchange.max_drawdown
  )
  assert ret.stats_pct.winrate >= expected_winrate or ret.stats_pct.trades == 0, "No trades were executed"
  assert ret.stats_pct.max_drawdown <= expected_max_drawdown
