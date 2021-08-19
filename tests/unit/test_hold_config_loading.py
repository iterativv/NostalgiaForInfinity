import json
import logging

import pytest
from freqtrade.persistence import Trade

from tests.unit.conftest import generate_mock_trade
from tests.unit.conftest import REPO_ROOT


@pytest.fixture(autouse=True)
def quiet_freqtrade_logs(caplog):
    with caplog.at_level(logging.WARNING, logger="freqtrade"):
        yield


def test_initial_no_config(strategy):
    assert strategy.hold_trades_cache is None


@pytest.fixture
def initial_trade(strategy):
    Trade.query.session.add(generate_mock_trade(pair="BTC/USDT", fee=0.025, is_open=True))


@pytest.fixture
def v1_syntax_hold_file(testdatadir, initial_trade):
    hold_trade_file = testdatadir / "strategies" / "hold-trades.json"
    hold_trade_file.write_text(json.dumps({"trade_ids": [1], "profit_ratio": 0.0025}))
    return hold_trade_file


@pytest.fixture
def v2_syntax_hold_file(testdatadir, initial_trade):
    hold_trade_file = testdatadir / "strategies" / "hold-trades.json"
    hold_trade_file.write_text(json.dumps({"trade_ids": {"1": 0.0035}}))
    return hold_trade_file


def test_hold_support_v1_syntax(strategy, v1_syntax_hold_file):
    assert strategy.get_hold_trades_config_file() == v1_syntax_hold_file
    strategy.load_hold_trades_config()
    assert strategy.hold_trades_cache.data == {1: 0.0025}


def test_hold_support_v2_syntax(strategy, v2_syntax_hold_file):
    assert strategy.get_hold_trades_config_file() == v2_syntax_hold_file
    strategy.load_hold_trades_config()
    assert strategy.hold_trades_cache.data == {1: 0.0035}


@pytest.fixture
def symlink_strat(testdatadir, strategy, initial_trade):
    # Remove copied strat file
    testdatadir.joinpath("strategies", "NostalgiaForInfinityNext.py").unlink()
    testdatadir.joinpath("strategies", "NostalgiaForInfinityNext.py").symlink_to(
        REPO_ROOT.joinpath("NostalgiaForInfinityNext.py")
    )
    hold_trade_file = testdatadir / "strategies" / "hold-trades.json"
    hold_trade_file.write_text(json.dumps({"trade_ids": [1], "profit_ratio": 0.0025}))
    return strategy


def test_symlinked_strat_hold_config_file(symlink_strat, testdatadir):
    assert testdatadir.joinpath("strategies", "NostalgiaForInfinityNext.py").is_symlink()
    symlink_strat.load_hold_trades_config()
    assert symlink_strat.hold_trades_cache.data == {1: 0.0025}


def test_missing_hold_trades(strategy, caplog, testdatadir):
    with caplog.at_level(logging.WARNING, "NostalgiaForInfinityNext"):
        strategy.load_hold_trades_config()
    expected_log_message = (
        "The 'hold-trades.json' file was not found. Looked in '{}'. HOLD support disabled.".format(
            testdatadir / "strategies" / "hold-trades.json"
        )
    )
    assert expected_log_message in caplog.text


@pytest.fixture
def symlink_strat_no_config(testdatadir, strategy):
    # Remove copied strat file
    testdatadir.joinpath("strategies", "NostalgiaForInfinityNext.py").unlink()
    testdatadir.joinpath("strategies", "NostalgiaForInfinityNext.py").symlink_to(
        REPO_ROOT.joinpath("NostalgiaForInfinityNext.py")
    )
    return strategy


def test_missing_hold_trades_symlinked_strat(symlink_strat_no_config, caplog, testdatadir):
    with caplog.at_level(logging.WARNING, "NostalgiaForInfinityNext"):
        symlink_strat_no_config.load_hold_trades_config()
    expected_log_message = (
        "The 'hold-trades.json' file was not found. Looked in {}. HOLD support disabled.".format(
            "'{}' and '{}'".format(
                REPO_ROOT / "hold-trades.json", testdatadir / "strategies" / "hold-trades.json"
            )
        )
    )
    assert expected_log_message in caplog.text


def test_hold_caches_save_raises_exception(strategy, v2_syntax_hold_file):
    assert strategy.get_hold_trades_config_file() == v2_syntax_hold_file
    strategy.load_hold_trades_config()
    assert strategy.hold_trades_cache.data == {1: 0.0035}
    strategy.hold_trades_cache.data[2] = 0.0035
    with pytest.raises(RuntimeError):
        strategy.hold_trades_cache.save()
