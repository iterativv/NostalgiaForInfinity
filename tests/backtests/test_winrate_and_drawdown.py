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
    Exchange(name="binance", winrate=70, max_drawdown=25),
    Exchange(name="kucoin", winrate=70, max_drawdown=25),
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
    # # Monthly Test Periods
    # # # ADD NEW MONTHS HERE
    # # # #
    # # # 2025 Monthly Test Periods
    # # # #
    # Timerange("20251201", "20260101"),
    # Timerange("20251101", "20251201"),
    # Timerange("20251001", "20251101"),
    # Timerange("20250901", "20251001"),
    # Timerange("20250801", "20250901"),
    # Timerange("20250701", "20250801"),
    # Timerange("20250601", "20250701"),
    # Timerange("20250501", "20250601"),
    # Timerange("20250401", "20250501"),
    # Timerange("20250301", "20250401"),
    # Timerange("20250201", "20250301"),
    # Timerange("20250101", "20250201"),
    # # #
    # # 2024 Monthly Test Periods
    # # #
    # Timerange("20241201", "20250101"),
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
    # # #
    # # 2023 Monthly Test Periods
    # # #
    Timerange("20231201", "20240101"),
    Timerange("20231101", "20231201"),
    Timerange("20231001", "20231101"),
    Timerange("20230901", "20231001"),
    Timerange("20230801", "20230901"),
    Timerange("20230701", "20230801"),
    Timerange("20230601", "20230701"),
    Timerange("20230501", "20230601"),
    Timerange("20230401", "20230501"),
    Timerange("20230301", "20230401"),
    Timerange("20230201", "20230301"),
    Timerange("20230101", "20230201"),
    # # #
    # # 2022 Monthly Test Periods
    # # #
    Timerange("20221201", "20230101"),
    Timerange("20221101", "20221201"),
    Timerange("20221001", "20221101"),
    Timerange("20220901", "20221001"),
    Timerange("20220801", "20220901"),
    Timerange("20220701", "20220801"),
    Timerange("20220601", "20220701"),
    Timerange("20220501", "20220601"),
    Timerange("20220401", "20220501"),
    Timerange("20220301", "20220401"),
    Timerange("20220201", "20220301"),
    Timerange("20220101", "20220201"),
    # # #
    # # 2021 Monthly Test Periods
    # # #
    Timerange("20211201", "20220101"),
    Timerange("20211101", "20211201"),
    Timerange("20211001", "20211101"),
    Timerange("20210901", "20211001"),
    Timerange("20210801", "20210901"),
    Timerange("20210701", "20210801"),
    Timerange("20210601", "20210701"),
    Timerange("20210501", "20210601"),
    Timerange("20210401", "20210501"),
    Timerange("20210301", "20210401"),
    Timerange("20210201", "20210301"),
    Timerange("20210101", "20210201"),
    # # #
    # # 2020 Monthly Test Periods
    # # #
    Timerange("20201201", "20210101"),
    Timerange("20201101", "20201201"),
    Timerange("20201001", "20201101"),
    Timerange("20200901", "20201001"),
    Timerange("20200801", "20200901"),
    Timerange("20200701", "20200801"),
    Timerange("20200601", "20200701"),
    Timerange("20200501", "20200601"),
    Timerange("20200401", "20200501"),
    Timerange("20200301", "20200401"),
    Timerange("20200201", "20200301"),
    Timerange("20200101", "20200201"),
    # # # #
    # # # 2019 Monthly Test Periods
    # # # #
    # Timerange("20191201", "20200101"),
    # Timerange("20191101", "20191201"),
    # Timerange("20191001", "20191101"),
    # Timerange("20190901", "20191001"),
    # Timerange("20190801", "20190901"),
    # Timerange("20190701", "20190801"),
    # Timerange("20190601", "20190701"),
    # Timerange("20190501", "20190601"),
    # Timerange("20190401", "20190501"),
    # Timerange("20190301", "20190401"),
    # Timerange("20190201", "20190301"),
    # Timerange("20190101", "20190201"),
    # # # #
    # # # 2018 Monthly Test Periods
    # # # #
    # Timerange("20181201", "20190101"),
    # Timerange("20181101", "20181201"),
    # Timerange("20181001", "20181101"),
    # Timerange("20180901", "20181001"),
    # Timerange("20180801", "20180901"),
    # Timerange("20180701", "20180801"),
    # Timerange("20180601", "20180701"),
    # Timerange("20180501", "20180601"),
    # Timerange("20180401", "20180501"),
    # Timerange("20180301", "20180401"),
    # Timerange("20180201", "20180301"),
    # Timerange("20180101", "20180201"),
    # # # #
    # # # 2017 Monthly Test Periods
    # # # #
    # Timerange("20171201", "20180101"),
    # Timerange("20171101", "20171201"),
    # Timerange("20171001", "20171101"),
    # Timerange("20170901", "20171001"),
    # Timerange("20170801", "20170901"),
    # Timerange("20170701", "20170801"),
    # Timerange("20170601", "20170701"),
    # Timerange("20170501", "20170601"),
    # Timerange("20170401", "20170501"),
    # Timerange("20170301", "20170401"),
    # Timerange("20170201", "20170301"),
    # Timerange("20170101", "20170201"),
  ),
  ids=timerange_fmt,
)
def timerange(request):
  return request.param


@pytest.fixture(scope="session")
def deviations():
  return {
    "binance": {
      # ("20210101", "20210201"): {"max_drawdown": 25, "winrate": 70},
      # ("20210201", "20210301"): {"max_drawdown": 35, "winrate": 70},
      # ("20210301", "20210401"): {"max_drawdown": 25, "winrate": 70},
      # ("20210401", "20210501"): {"max_drawdown": 25, "winrate": 70},
      # ("20210501", "20210601"): {"max_drawdown": 35, "winrate": 70},
      # ("20210601", "20210701"): {"max_drawdown": 25, "winrate": 70},
      # ("20210701", "20210801"): {"max_drawdown": 25, "winrate": 70},
      # ("20210801", "20210901"): {"max_drawdown": 25, "winrate": 70},
      # ("20210901", "20211001"): {"max_drawdown": 25, "winrate": 70},
      # ("20211001", "20211101"): {"max_drawdown": 30, "winrate": 70},
      # ("20211201", "20220101"): {"max_drawdown": 25, "winrate": 70},
      # ("20220301", "20220401"): {"max_drawdown": 25, "winrate": 70},
      ("20221101", "20221201"): {"max_drawdown": 30, "winrate": 70},
    },
    "kucoin": {
      # ("20210201", "20210301"): {"max_drawdown": 25, "winrate": 70},
      # ("20210301", "20210401"): {"max_drawdown": 25, "winrate": 70},
      # ("20210401", "20210501"): {"max_drawdown": 30, "winrate": 70},
      ("20210501", "20210601"): {"max_drawdown": 40, "winrate": 70},
      # ("20210601", "20210701"): {"max_drawdown": 25, "winrate": 70},
      # ("20210701", "20210801"): {"max_drawdown": 25, "winrate": 70},
      # ("20210801", "20210901"): {"max_drawdown": 25, "winrate": 70},
      # ("20210901", "20211001"): {"max_drawdown": 25, "winrate": 70},
      # ("20211001", "20211101"): {"max_drawdown": 25, "winrate": 70},
      # ("20220101", "20220201"): {"max_drawdown": 25, "winrate": 70},
      # ("20220401", "20220501"): {"max_drawdown": 25, "winrate": 70},
      # ("20220601", "20220701"): {"max_drawdown": 25, "winrate": 70},
      # ("20211201", "20220101"): {"max_drawdown": 25, "winrate": 70},
      # ("20211101", "20211201"): {"max_drawdown": 25, "winrate": 70},
      ("20230901", "20231001"): {"max_drawdown": 25, "winrate": 0},
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
