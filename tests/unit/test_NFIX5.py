import pytest
from unittest.mock import MagicMock
from NostalgiaForInfinityX5 import NostalgiaForInfinityX5
from pathlib import Path

@pytest.fixture
def mock_config(tmp_path):
    class RunModeMock:
        def __init__(self, value):
            self.value = value

    return {
        "exchange": {
            "name": "binance",
            "ccxt_config": {
                "apiKey": "dummy_key",
                "secret": "dummy_secret",
                "password": None,
            },
            "pair_whitelist": ["BTC/USDT"],
            "pair_blacklist": [],
        },
        "stake_currency": "USDT",
        "stake_amount": 10,
        "dry_run": True,
        "timeframe": "5m",
        "max_open_trades": 5,
        "user_data_dir": tmp_path,  # Use pytest's temporary directory
        "runmode": RunModeMock("backtest"),  # Simulate the execution mode
    }

def test_update_signals_from_config(mock_config):
    """Test that the update_signals_from_config function correctly updates signals"""
    strategy = NostalgiaForInfinityX5(mock_config)  # mock_config is injected by pytest

    # Test setup with actual signals
    test_config = {
        'long_entry_signal_params': {
            'long_entry_condition_1_enable': False,
            'long_entry_condition_2_enable': True,
            'long_entry_condition_3_enable': False,
            'long_entry_condition_4_enable': True,
            'long_entry_condition_5_enable': False,
            'long_entry_condition_6_enable': True,
            'long_entry_condition_41_enable': False,
            'long_entry_condition_42_enable': True,
            'long_entry_condition_43_enable': False,
            'long_entry_condition_120_enable': True,
            'long_entry_condition_141_enable': False,
            'long_entry_condition_142_enable': True,
            'long_entry_condition_143_enable': False
        },
        'short_entry_signal_params': {
            'short_entry_condition_501_enable': False
        }
    }
    
    # Save initial state of the signals
    initial_signals = {
        'long': dict(strategy.long_entry_signal_params),
        'short': dict(strategy.short_entry_signal_params)
    }

    strategy.update_signals_from_config(test_config)
    
    # Verify that the long signals were updated correctly
    for signal_name, value in test_config['long_entry_signal_params'].items():
        assert strategy.long_entry_signal_params[signal_name] == value, (
        f"Mismatch in {signal_name}: "
        f"expected {value}, got {strategy.long_entry_signal_params[signal_name]}"
    )
        
    # Verify that the short signals were updated correctly
    for signal_name, value in test_config['short_entry_signal_params'].items():
        assert strategy.short_entry_signal_params[signal_name] == value
    
    # Verify that signals not included in the config retain their original values
    for signal_name in initial_signals['long']:
        if signal_name not in test_config['long_entry_signal_params']:
            assert strategy.long_entry_signal_params[signal_name] == initial_signals['long'][signal_name]
            
    for signal_name in initial_signals['short']:
        if signal_name not in test_config['short_entry_signal_params']:
            assert strategy.short_entry_signal_params[signal_name] == initial_signals['short'][signal_name]
    
    # Test with partial configuration
    partial_config = {
        'long_entry_signal_params': {
            'long_entry_condition_1_enable': True
        }
    }
    
    strategy.update_signals_from_config(partial_config)
    assert strategy.long_entry_signal_params['long_entry_condition_1_enable'] is True
    # Verify that other signals remain unchanged
    assert strategy.long_entry_signal_params['long_entry_condition_2_enable'] is True
