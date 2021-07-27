import pytest

from tests.backtests.helpers import Backtest


@pytest.fixture
def backtest(request):
    return Backtest(request, "binance")
