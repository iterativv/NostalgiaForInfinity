import pytest
from unittest.mock import MagicMock
from datetime import datetime
from NostalgiaForInfinityX7 import NostalgiaForInfinityX7


@pytest.fixture
def mock_config(tmp_path):
  class RunModeMock:
    def __init__(self, value):
      self.value = value

  return {
    "exchange": {
      "name": "bybit",
      "ccxt_config": {
        "apiKey": "dummy_key",
        "secret": "dummy_secret",
        "password": None,
      },
      "pair_whitelist": ["BTC/USDT:USDT", "ETH/USDT:USDT", "ADA/USDT:USDT"],
      "pair_blacklist": [],
    },
    "stake_currency": "USDT",
    "stake_amount": 10,
    "dry_run": True,
    "trading_mode": "futures",
    "timeframe": "5m",
    "max_open_trades": 10,
    "user_data_dir": tmp_path,  # Use pytest's temporary directory
    "runmode": RunModeMock("dry_run"),  # Simulate the execution mode
  }


def test_region_blacklist_adds_unavailable_pair(mock_config, mocker):
  """Issue #1026: pairs that are not returned by the exchange (region-restricted)
  should be auto-added to the exchange blacklist."""
  strategy = NostalgiaForInfinityX7(mock_config)
  # DataProvider / exchange are injected by freqtrade at runtime; mock them for the unit test
  strategy.dp = MagicMock()
  strategy.exchange = MagicMock()

  # Whitelist has 3 pairs; simulate exchange returning only 2 of them
  mocker.patch.object(
    strategy.dp, "current_whitelist",
    return_value=["BTC/USDT:USDT", "ETH/USDT:USDT", "ADA/USDT:USDT"],
  )
  markets = {
    "BTC/USDT:USDT": {"info": {"status": "open"}},
    "ETH/USDT:USDT": {"info": {"status": "open"}},
    # ADA is intentionally missing -> region-unavailable
  }
  mocker.patch.object(strategy.exchange, "get_markets", return_value=markets)

  strategy._last_region_blacklist_check = 0  # force a refresh
  strategy._refresh_region_blacklist(datetime(2026, 1, 1, 12, 0, 0))

  blacklist = strategy.config["exchange"]["pair_blacklist"]
  assert "ADA/USDT:USDT" in blacklist, f"ADA should be blacklisted, got {blacklist}"


def test_region_blacklist_skips_closed_status(mock_config, mocker):
  """Issue #1026: pairs with non-open status should also be blacklisted."""
  strategy = NostalgiaForInfinityX7(mock_config)
  strategy.dp = MagicMock()
  strategy.exchange = MagicMock()

  mocker.patch.object(
    strategy.dp, "current_whitelist",
    return_value=["BTC/USDT:USDT", "ETH/USDT:USDT"],
  )
  markets = {
    "BTC/USDT:USDT": {"info": {"status": "open"}},
    "ETH/USDT:USDT": {"info": {"status": "closed"}},  # region/halt -> not tradable
  }
  mocker.patch.object(strategy.exchange, "get_markets", return_value=markets)

  strategy._last_region_blacklist_check = 0
  strategy._refresh_region_blacklist(datetime(2026, 1, 1, 12, 0, 0))

  blacklist = strategy.config["exchange"]["pair_blacklist"]
  assert "ETH/USDT:USDT" in blacklist, f"ETH (closed) should be blacklisted, got {blacklist}"


def test_region_blacklist_keeps_available_pairs(mock_config, mocker):
  """Issue #1026: tradable pairs must NOT be blacklisted."""
  strategy = NostalgiaForInfinityX7(mock_config)
  strategy.dp = MagicMock()
  strategy.exchange = MagicMock()

  mocker.patch.object(
    strategy.dp, "current_whitelist",
    return_value=["BTC/USDT:USDT", "ETH/USDT:USDT"],
  )
  markets = {
    "BTC/USDT:USDT": {"info": {"status": "open"}},
    "ETH/USDT:USDT": {"info": {"status": "open"}},
  }
  mocker.patch.object(strategy.exchange, "get_markets", return_value=markets)

  strategy._last_region_blacklist_check = 0
  strategy._refresh_region_blacklist(datetime(2026, 1, 1, 12, 0, 0))

  blacklist = strategy.config["exchange"]["pair_blacklist"]
  assert blacklist == [], f"No pairs should be blacklisted, got {blacklist}"


def test_region_blacklist_throttled(mock_config, mocker):
  """Issue #1026: refresh should be throttled to once per hour."""
  strategy = NostalgiaForInfinityX7(mock_config)
  strategy.dp = MagicMock()
  strategy.exchange = MagicMock()

  mocker.patch.object(
    strategy.dp, "current_whitelist",
    return_value=["ADA/USDT:USDT"],  # would be blacklisted if run
  )
  markets = {}  # ADA missing -> normally blacklisted
  mocker.patch.object(strategy.exchange, "get_markets", return_value=markets)

  # Set last check to "now" -> within throttle window, should skip
  strategy._last_region_blacklist_check = datetime(2026, 1, 1, 12, 0, 0).timestamp()
  strategy._refresh_region_blacklist(datetime(2026, 1, 1, 12, 0, 30))  # 30s later

  blacklist = strategy.config["exchange"]["pair_blacklist"]
  assert blacklist == [], f"Throttled refresh must not modify blacklist, got {blacklist}"
