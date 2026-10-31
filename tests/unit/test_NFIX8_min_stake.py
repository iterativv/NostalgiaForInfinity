import pytest

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


@pytest.mark.parametrize(
  "futures,exchange,leverage,minimum,expected",
  [
    (False, "binance", 1.0, None, 0.0),
    (False, "okx", 1.0, None, 0.0),
    (True, "okx", 3.0, None, 0.0),
    (True, "binance", 2.0, None, 2.5),
    (True, "bybit", 5.0, None, 1.0),
    (True, "krakenfutures", None, None, 1.25),
    (False, "bybit", 1.0, 8.0, 8.0),
    (True, "binance", 2.0, 0.0, 2.5),
    (True, "bybit", 5.0, 0.25, 1.0),
    (True, "krakenfutures", 4.0, 1.25, 1.25),
    (True, "binance", 2.0, 10.0, 10.0),
    (True, "okx", 3.0, 0.0, 0.0),
    (True, "okx", 3.0, 2.5, 2.5),
    (False, "binance", None, 0.0, 0.0),
  ],
)
def test_optional_minimum_preserves_supplied_limits_and_futures_floors(futures, exchange, leverage, minimum, expected):
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.is_futures_mode = futures
  strategy.config = {"exchange": {"name": exchange}}
  strategy.futures_mode_leverage = 4.0

  result = strategy.correct_min_stake(minimum, leverage)

  assert result == expected
