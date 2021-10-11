import random
import shutil
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import PropertyMock

import pytest
from freqtrade.enums import SellType
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import init_db
from freqtrade.persistence import Trade

REPO_ROOT = Path(__file__).parent.parent.parent

# Most of these fixture we taken from freqtrade


def get_markets():
    return {
        "ETH/BTC": {
            "id": "ethbtc",
            "symbol": "ETH/BTC",
            "base": "ETH",
            "quote": "BTC",
            "active": True,
            "precision": {
                "price": 8,
                "amount": 8,
                "cost": 8,
            },
            "lot": 0.00000001,
            "limits": {
                "amount": {
                    "min": 0.01,
                    "max": 1000,
                },
                "price": 500000,
                "cost": {
                    "min": 0.0001,
                    "max": 500000,
                },
            },
            "info": {},
        },
        "TKN/BTC": {
            "id": "tknbtc",
            "symbol": "TKN/BTC",
            "base": "TKN",
            "quote": "BTC",
            # According to ccxt, markets without active item set are also active
            # 'active': True,
            "precision": {
                "price": 8,
                "amount": 8,
                "cost": 8,
            },
            "lot": 0.00000001,
            "limits": {
                "amount": {
                    "min": 0.01,
                    "max": 1000,
                },
                "price": 500000,
                "cost": {
                    "min": 0.0001,
                    "max": 500000,
                },
            },
            "info": {},
        },
        "BLK/BTC": {
            "id": "blkbtc",
            "symbol": "BLK/BTC",
            "base": "BLK",
            "quote": "BTC",
            "active": True,
            "precision": {
                "price": 8,
                "amount": 8,
                "cost": 8,
            },
            "lot": 0.00000001,
            "limits": {
                "amount": {
                    "min": 0.01,
                    "max": 1000,
                },
                "price": 500000,
                "cost": {
                    "min": 0.0001,
                    "max": 500000,
                },
            },
            "info": {},
        },
        "LTC/BTC": {
            "id": "ltcbtc",
            "symbol": "LTC/BTC",
            "base": "LTC",
            "quote": "BTC",
            "active": True,
            "precision": {
                "price": 8,
                "amount": 8,
                "cost": 8,
            },
            "lot": 0.00000001,
            "limits": {
                "amount": {
                    "min": 0.01,
                    "max": 1000,
                },
                "price": 500000,
                "cost": {
                    "min": 0.0001,
                    "max": 500000,
                },
            },
            "info": {},
        },
        "XRP/BTC": {
            "id": "xrpbtc",
            "symbol": "XRP/BTC",
            "base": "XRP",
            "quote": "BTC",
            "active": True,
            "precision": {
                "price": 8,
                "amount": 8,
                "cost": 8,
            },
            "lot": 0.00000001,
            "limits": {
                "amount": {
                    "min": 0.01,
                    "max": 1000,
                },
                "price": 500000,
                "cost": {
                    "min": 0.0001,
                    "max": 500000,
                },
            },
            "info": {},
        },
        "NEO/BTC": {
            "id": "neobtc",
            "symbol": "NEO/BTC",
            "base": "NEO",
            "quote": "BTC",
            "active": True,
            "precision": {
                "price": 8,
                "amount": 8,
                "cost": 8,
            },
            "lot": 0.00000001,
            "limits": {
                "amount": {
                    "min": 0.01,
                    "max": 1000,
                },
                "price": 500000,
                "cost": {
                    "min": 0.0001,
                    "max": 500000,
                },
            },
            "info": {},
        },
        "BTT/BTC": {
            "id": "BTTBTC",
            "symbol": "BTT/BTC",
            "base": "BTT",
            "quote": "BTC",
            "active": False,
            "precision": {"base": 8, "quote": 8, "amount": 0, "price": 8},
            "limits": {
                "amount": {"min": 1.0, "max": 90000000.0},
                "price": {"min": None, "max": None},
                "cost": {"min": 0.0001, "max": None},
            },
            "info": {},
        },
        "ETH/USDT": {
            "id": "USDT-ETH",
            "symbol": "ETH/USDT",
            "base": "ETH",
            "quote": "USDT",
            "precision": {"amount": 8, "price": 8},
            "limits": {
                "amount": {"min": 0.02214286, "max": None},
                "price": {"min": 1e-08, "max": None},
            },
            "active": True,
            "info": {},
        },
        "LTC/USDT": {
            "id": "USDT-LTC",
            "symbol": "LTC/USDT",
            "base": "LTC",
            "quote": "USDT",
            "active": False,
            "precision": {"amount": 8, "price": 8},
            "limits": {
                "amount": {"min": 0.06646786, "max": None},
                "price": {"min": 1e-08, "max": None},
            },
            "info": {},
        },
        "LTC/USD": {
            "id": "USD-LTC",
            "symbol": "LTC/USD",
            "base": "LTC",
            "quote": "USD",
            "active": True,
            "precision": {"amount": 8, "price": 8},
            "limits": {
                "amount": {"min": 0.06646786, "max": None},
                "price": {"min": 1e-08, "max": None},
            },
            "info": {},
        },
        "XLTCUSDT": {
            "id": "xLTCUSDT",
            "symbol": "XLTCUSDT",
            "base": "LTC",
            "quote": "USDT",
            "active": True,
            "precision": {"amount": 8, "price": 8},
            "limits": {
                "amount": {"min": 0.06646786, "max": None},
                "price": {"min": 1e-08, "max": None},
            },
            "info": {},
        },
        "LTC/ETH": {
            "id": "LTCETH",
            "symbol": "LTC/ETH",
            "base": "LTC",
            "quote": "ETH",
            "active": True,
            "precision": {"base": 8, "quote": 8, "amount": 3, "price": 5},
            "limits": {
                "amount": {"min": 0.001, "max": 10000000.0},
                "price": {"min": 1e-05, "max": 1000.0},
                "cost": {"min": 0.01, "max": None},
            },
        },
    }


def patch_exchange(mocker, api_mock=None, id="binance", mock_markets=True) -> None:
    mocker.patch("freqtrade.exchange.Exchange._load_async_markets", MagicMock(return_value={}))
    mocker.patch("freqtrade.exchange.Exchange.validate_pairs", MagicMock())
    mocker.patch("freqtrade.exchange.Exchange.validate_timeframes", MagicMock())
    mocker.patch("freqtrade.exchange.Exchange.validate_ordertypes", MagicMock())
    mocker.patch("freqtrade.exchange.Exchange.validate_stakecurrency", MagicMock())
    mocker.patch("freqtrade.exchange.Exchange.id", PropertyMock(return_value=id))
    mocker.patch("freqtrade.exchange.Exchange.name", PropertyMock(return_value=id.title()))
    mocker.patch("freqtrade.exchange.Exchange.precisionMode", PropertyMock(return_value=2))
    if mock_markets:
        mocker.patch(
            "freqtrade.exchange.Exchange.markets", PropertyMock(return_value=get_markets())
        )

    if api_mock:
        mocker.patch("freqtrade.exchange.Exchange._init_ccxt", MagicMock(return_value=api_mock))
    else:
        mocker.patch("freqtrade.exchange.Exchange._init_ccxt", MagicMock())


def patch_whitelist(mocker, conf) -> None:
    mocker.patch(
        "freqtrade.freqtradebot.FreqtradeBot._refresh_active_whitelist",
        MagicMock(return_value=conf["exchange"]["pair_whitelist"]),
    )


def patch_freqtradebot(mocker, config) -> None:
    """
    This function patch _init_modules() to not call dependencies
    :param mocker: a Mocker object to apply patches
    :param config: Config to pass to the bot
    :return: None
    """
    mocker.patch("freqtrade.freqtradebot.RPCManager", MagicMock())
    init_db(config["db_url"])
    patch_exchange(mocker)
    mocker.patch("freqtrade.freqtradebot.RPCManager._init", MagicMock())
    mocker.patch("freqtrade.freqtradebot.RPCManager.send_msg", MagicMock())
    patch_whitelist(mocker, config)


def get_patched_freqtradebot(mocker, config) -> FreqtradeBot:
    """
    This function patches _init_modules() to not call dependencies
    :param mocker: a Mocker object to apply patches
    :param config: Config to pass to the bot
    :return: FreqtradeBot
    """
    patch_freqtradebot(mocker, config)
    config["datadir"] = Path(config["datadir"])
    return FreqtradeBot(config)


@pytest.fixture
def testdatadir(tmp_path) -> Path:
    """Return the path where testdata files are stored"""
    user_data = tmp_path / "user_data"
    user_data.mkdir()
    for name in ("strategies", "data"):
        user_data.joinpath(name).mkdir()
    shutil.copyfile(
        REPO_ROOT / "NostalgiaForInfinityNext.py",
        user_data / "strategies" / "NostalgiaForInfinityNext.py",
    )
    shutil.copyfile(
        REPO_ROOT / "NostalgiaForInfinityX.py",
        user_data / "strategies" / "NostalgiaForInfinityX.py",
    )
    return user_data


@pytest.fixture(scope="function")
def default_conf(testdatadir):
    return get_default_conf(testdatadir)


def get_default_conf(testdatadir):
    """Returns validated configuration suitable for most tests"""
    configuration = {
        "max_open_trades": 1,
        "stake_currency": "USDT",
        "stake_amount": 0.001,
        "fiat_display_currency": "USD",
        "timeframe": "5m",
        "dry_run": True,
        "cancel_open_orders_on_exit": False,
        "minimal_roi": {"40": 0.0, "30": 0.01, "20": 0.02, "0": 0.04},
        "dry_run_wallet": 1000,
        "stoploss": -0.10,
        "unfilledtimeout": {"buy": 10, "sell": 30},
        "bid_strategy": {
            "ask_last_balance": 0.0,
            "use_order_book": False,
            "order_book_top": 1,
            "check_depth_of_market": {"enabled": False, "bids_to_ask_delta": 1},
        },
        "ask_strategy": {
            "use_order_book": False,
            "order_book_top": 1,
        },
        "exchange": {
            "name": "binance",
            "enabled": True,
            "key": "key",
            "secret": "secret",
            "pair_whitelist": ["ETH/BTC", "LTC/BTC", "XRP/BTC", "NEO/BTC"],
            "pair_blacklist": [
                "DOGE/BTC",
                "HOT/BTC",
            ],
        },
        "pairlists": [{"method": "StaticPairList"}],
        "telegram": {
            "enabled": True,
            "token": "token",
            "chat_id": "0",
            "notification_settings": {},
        },
        "datadir": str(testdatadir),
        "initial_state": "running",
        "db_url": "sqlite://",
        "user_data_dir": testdatadir,
        "verbosity": 3,
        "strategy_path": str(testdatadir / "strategies"),
        "strategy": "NostalgiaForInfinityNext",
        "disableparamexport": True,
        "internals": {},
        "export": "none",
    }
    return configuration


def generate_mock_trade(
    pair: str,
    fee: float,
    is_open: bool,
    sell_reason: str = SellType.SELL_SIGNAL,
    min_ago_open: int = None,
    min_ago_close: int = None,
    profit_rate: float = 0.9,
):
    open_rate = random.random()

    trade = Trade(
        pair=pair,
        stake_amount=0.01,
        fee_open=fee,
        fee_close=fee,
        open_date=datetime.utcnow() - timedelta(minutes=min_ago_open or 200),
        close_date=datetime.utcnow() - timedelta(minutes=min_ago_close or 30),
        open_rate=open_rate,
        is_open=is_open,
        amount=0.01 / open_rate,
        exchange="binance",
    )
    trade.recalc_open_trade_value()
    if not is_open:
        trade.close(open_rate * profit_rate)
        trade.sell_reason = sell_reason

    return trade


@pytest.fixture
def bot(mocker, default_conf):
    return get_patched_freqtradebot(mocker, default_conf)


@pytest.fixture
def strategy(bot):
    return bot.strategy
