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
        Exchange(name="binance", winrate=70, max_drawdown=20),
        Exchange(name="kucoin", winrate=70, max_drawdown=20),
    ),
    ids=exchange_fmt,
)
def exchange(request):
    return request.param


@pytest.fixture(scope="session", autouse=True)
def check_exchange_data_presen(exchange):
    exchange_data_dir = REPO_ROOT / "user_data" / "data" / exchange.name
    if not exchange_data_dir.is_dir():
        pytest.fail(
            f"There's no exchange data for {exchange.name}. Make sure the repository submodule "
            "is init/update. Check the repository README.md for more information."
        )
    if not list(exchange_data_dir.rglob("*.json.gz")):
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
        Timerange("20210101", "20210201"),
        Timerange("20210201", "20210301"),
        Timerange("20210301", "20210401"),
        Timerange("20210401", "20210501"),
        Timerange("20210501", "20210601"),
        Timerange("20210601", "20210701"),
        Timerange("20210701", "20210801"),
        Timerange("20210801", "20210901"),
        Timerange("20210901", "20211001"),
        Timerange("20211001", "20211101"),
        Timerange("20211101", "20211201"),
        Timerange("20211201", "20220101"),
        Timerange("20220101", "20220201"),
        Timerange("20220201", "20220301"),
        Timerange("20220301", "20220401"),
        Timerange("20220401", "20220501"),
        Timerange("20220501", "20220601"),
        Timerange("20220601", "20220701"),
        Timerange("20220701", "20220801"),
        Timerange("20220801", "20220901"),
        Timerange("20220901", "20221001"),
        Timerange("20221001", "20221101"),
        Timerange("20221101", "20221201"),
        Timerange("20221201", "20230101"),
        Timerange("20230101", "20230201"),
        Timerange("20230201", "20230301"),
        Timerange("20230301", "20230401"),
        Timerange("20230401", "20230501"),
    ),
    ids=timerange_fmt,
)
def timerange(request):
    return request.param


@pytest.fixture(scope="session")
def deviations():
    return {
        "binance": {
            ("20210101", "20210201"): {"max_drawdown": 20, "winrate": 70},
            ("20210201", "20210301"): {"max_drawdown": 35, "winrate": 70},
            ("20210301", "20210401"): {"max_drawdown": 20, "winrate": 70},
            ("20210401", "20210501"): {"max_drawdown": 20, "winrate": 70},
            ("20210501", "20210601"): {"max_drawdown": 35, "winrate": 70},
            ("20210601", "20210701"): {"max_drawdown": 20, "winrate": 70},
            ("20210701", "20210801"): {"max_drawdown": 20, "winrate": 70},
            ("20210801", "20210901"): {"max_drawdown": 20, "winrate": 70},
            ("20210901", "20211001"): {"max_drawdown": 20, "winrate": 70},
            ("20211001", "20211101"): {"max_drawdown": 20, "winrate": 70},
            ("20211201", "20220101"): {"max_drawdown": 20, "winrate": 70},
            ("20220301", "20220401"): {"max_drawdown": 20, "winrate": 70},
        },
        "kucoin": {
            ("20210201", "20210301"): {"max_drawdown": 20, "winrate": 70},
            ("20210301", "20210401"): {"max_drawdown": 20, "winrate": 70},
            ("20210401", "20210501"): {"max_drawdown": 30, "winrate": 70},
            ("20210501", "20210601"): {"max_drawdown": 30, "winrate": 70},
            ("20210601", "20210701"): {"max_drawdown": 20, "winrate": 70},
            ("20210701", "20210801"): {"max_drawdown": 20, "winrate": 70},
            ("20210801", "20210901"): {"max_drawdown": 20, "winrate": 70},
            ("20210901", "20211001"): {"max_drawdown": 20, "winrate": 70},
            ("20211001", "20211101"): {"max_drawdown": 20, "winrate": 70},
            ("20220101", "20220201"): {"max_drawdown": 20, "winrate": 70},
            ("20220401", "20220501"): {"max_drawdown": 20, "winrate": 70},
            ("20220601", "20220701"): {"max_drawdown": 20, "winrate": 70},
            ("20211201", "20220101"): {"max_drawdown": 20, "winrate": 70},
            ("20211101", "20211201"): {"max_drawdown": 20, "winrate": 70},
        },
    }


def test_expected_values(backtest, timerange, exchange, deviations):
    ret = backtest(
        start_date=timerange.start_date, end_date=timerange.end_date, exchange=exchange.name
    )
    exchange_deviations = deviations[exchange.name]
    expected_winrate = (
        exchange_deviations.get((timerange.start_date, timerange.end_date), {}).get("winrate")
        or exchange.winrate
    )
    expected_max_drawdown = (
        exchange_deviations.get((timerange.start_date, timerange.end_date), {}).get("max_drawdown")
        or exchange.max_drawdown
    )
    assert ret.stats_pct.winrate >= expected_winrate
    assert ret.stats_pct.max_drawdown <= expected_max_drawdown
