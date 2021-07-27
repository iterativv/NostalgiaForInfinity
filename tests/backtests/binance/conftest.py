import functools

import pytest

from tests.backtests.helpers import exchange_backtest


@pytest.fixture
def backtest(tmp_path):
    return functools.partial(exchange_backtest, "binance", tmp_path)
