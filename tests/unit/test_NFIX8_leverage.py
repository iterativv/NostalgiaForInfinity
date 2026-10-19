import json
from datetime import datetime
from datetime import timezone
from unittest.mock import MagicMock

import pytest
from freqtrade.enums import RunMode
from freqtrade.enums import TradingMode
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import Trade

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


ROUTES = [
  ("long", "1", "long", 5.0),
  ("long", "61 62", "long_rebuy_mode", 4.0),
  ("long", "120", "long_grind_mode", 2.0),
  ("short", "501", "short", 5.0),
  ("short", "561 562", "short_rebuy_mode", 5.0),
  ("short", "620", "short_grind_mode", 5.0),
]
NOW = datetime(2026, 10, 19, tzinfo=timezone.utc)


@pytest.fixture
def strategy_config(tmp_path):
  return {
    "exchange": {"name": "binance"},
    "runmode": RunMode.BACKTEST,
    "user_data_dir": tmp_path,
    "stake_currency": "USDT",
    "trading_mode": "futures",
    "futures_mode_leverage": 5.0,
    "futures_mode_leverage_rebuy_mode": 4.0,
    "futures_mode_leverage_grind_mode": 2.0,
  }


def leverage(strategy, side, tag):
  return strategy.leverage("BTC/USDT:USDT", NOW, 100.0, 1.0, 20.0, tag, side)


@pytest.mark.parametrize("explicit_null", [False, True])
@pytest.mark.parametrize("side,tag,suffix,expected", ROUTES)
def test_unset_overrides_preserve_existing_selection(strategy_config, explicit_null, side, tag, suffix, expected):
  # Given existing configurations, including different values for each mode.
  if explicit_null:
    strategy_config["nfi_parameters"] = json.loads(
      json.dumps({f"futures_mode_leverage_{route[2]}": None for route in ROUTES})
    )
  strategy = NostalgiaForInfinityX8(strategy_config)
  # When the original entry route asks for leverage.
  actual = leverage(strategy, side, tag)
  # Then even the original short-mode fallback remains unchanged.
  assert actual == expected


@pytest.mark.parametrize("config_style", ["nested", "top_level"])
@pytest.mark.parametrize("selected", range(len(ROUTES)))
def test_each_override_only_changes_its_direction_and_mode(strategy_config, config_style, selected):
  # Given one JSON override, with advanced mode disabled.
  params = json.loads(json.dumps({f"futures_mode_leverage_{ROUTES[selected][2]}": 7.0}))
  if config_style == "nested":
    strategy_config["nfi_parameters"] = params
  else:
    strategy_config.update(params)
  strategy = NostalgiaForInfinityX8(strategy_config)
  # When all six routes request leverage.
  actual = [leverage(strategy, side, tag) for side, tag, _, _ in ROUTES]
  # Then no other direction or mode inherits this override.
  assert actual == [7.0 if i == selected else row[3] for i, row in enumerate(ROUTES)]


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("tag", [None, "", "unknown", "61 120", "561 620", "1 61", "501 561"])
def test_general_override_handles_missing_unknown_and_mixed_tags(strategy_config, side, tag):
  strategy_config["nfi_parameters"] = {
    "futures_mode_leverage_long": 6.0,
    "futures_mode_leverage_short": 3.0,
  }
  strategy = NostalgiaForInfinityX8(strategy_config)

  actual = leverage(strategy, side, tag)

  assert actual == (6.0 if side == "long" else 3.0)


def test_legacy_top_level_precedence_and_instance_isolation(strategy_config):
  strategy_config["nfi_parameters"] = {"futures_mode_leverage_short": 7.0}
  strategy_config["futures_mode_leverage_short"] = 3.0
  configured = NostalgiaForInfinityX8(strategy_config)
  clean_config = {
    key: value
    for key, value in strategy_config.items()
    if key not in ("nfi_parameters", "futures_mode_leverage_short")
  }
  clean = NostalgiaForInfinityX8(clean_config)

  actual = (leverage(configured, "short", "501"), leverage(clean, "short", "501"))

  assert actual == (3.0, 5.0)


@pytest.mark.parametrize("side,tag,suffix,legacy", ROUTES)
@pytest.mark.parametrize("requested,cap,expected", [(3.0, 10.0, 3.0), (7.0, 5.0, 5.0), (0.5, 10.0, 1.0)])
def test_engine_passes_selected_leverage_to_stake_and_exchange_limits(
  strategy_config, side, tag, suffix, legacy, requested, cap, expected
):
  # Given the real strategy and engine, mocking only wallet/exchange and stake sizing.
  strategy_config["nfi_parameters"] = {f"futures_mode_leverage_{suffix}": requested}
  strategy = NostalgiaForInfinityX8(strategy_config)
  strategy.custom_stake_amount = MagicMock(return_value=100.0)
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.strategy = strategy
  bot.config = {}
  bot.trading_mode = TradingMode.FUTURES
  bot.exchange = MagicMock()
  bot.exchange.get_max_leverage.return_value = cap
  bot.exchange.get_min_pair_stake_amount.return_value = 1.0
  bot.exchange.get_max_pair_stake_amount.return_value = 1000.0
  bot.wallets = MagicMock()
  bot.wallets.get_available_stake_amount.return_value = 1000.0
  bot.wallets.validate_stake_amount.return_value = 100.0
  # When the engine prepares a new entry.
  result = bot.get_valid_enter_price_and_stake("BTC/USDT:USDT", 100.0, 100.0, side, tag, None, "initial", None)
  # Then its real clamping and downstream leverage forwarding use the selected value.
  assert result == (100.0, 100.0, expected)
  assert strategy.custom_stake_amount.call_args.kwargs["leverage"] == expected
  assert bot.exchange.get_min_pair_stake_amount.call_args.args[-1] == expected
  assert bot.exchange.get_max_pair_stake_amount.call_args.args[-1] == expected


@pytest.mark.parametrize("side", ["long", "short"])
@pytest.mark.parametrize("existing_trade", [False, True])
def test_engine_keeps_spot_and_existing_trade_leverage(strategy_config, side, existing_trade):
  strategy_config["nfi_parameters"] = {"futures_mode_leverage_long": 7.0, "futures_mode_leverage_short": 3.0}
  strategy = NostalgiaForInfinityX8(strategy_config)
  strategy.leverage = MagicMock(wraps=strategy.leverage)
  strategy.custom_stake_amount = MagicMock(return_value=100.0)
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.strategy = strategy
  bot.config = {}
  bot.trading_mode = TradingMode.FUTURES if existing_trade else TradingMode.SPOT
  bot.exchange = MagicMock()
  bot.exchange.get_min_pair_stake_amount.return_value = 1.0
  bot.exchange.get_max_pair_stake_amount.return_value = 1000.0
  bot.wallets = MagicMock()
  bot.wallets.get_available_stake_amount.return_value = 1000.0
  bot.wallets.validate_stake_amount.return_value = 100.0
  trade = None
  if existing_trade:
    trade = Trade(pair="BTC/USDT:USDT", leverage=2.0, stake_amount=100.0, amount=2.0, open_rate=100.0, fee_open=0.001)

  result = bot.get_valid_enter_price_and_stake(
    "BTC/USDT:USDT", 100.0, 100.0, side, None, trade, "pos_adjust" if existing_trade else "initial", None
  )

  assert result[2] == (2.0 if existing_trade else 1.0)
  strategy.leverage.assert_not_called()
