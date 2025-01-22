import pytest
from unittest.mock import MagicMock
from datetime import datetime
from NostalgiaForInfinityX5 import NostalgiaForInfinityX5


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
    "max_open_trades": 10,
    "user_data_dir": tmp_path,  # Use pytest's temporary directory
    "runmode": RunModeMock("backtest"),  # Simulate the execution mode
  }


# Define a mock trade object
class MockTrade:
  def __init__(self, is_short, enter_tag, fee_open=0.001, fee_close=0.001):
    self.is_short = is_short
    self.enter_tag = enter_tag
    self.enter_tags = enter_tag.split()
    self.open_rate = 100.0
    self.max_rate = 110.0
    self.min_rate = 90.0
    self.entry_side = "buy"
    self.exit_side = "sell"
    self.fee_open = fee_open
    self.fee_close = fee_close

  def select_filled_orders(self, side):
    # Simulate returning an empty list of filled orders for the test
    return [
      MagicMock(average=100.0, amount=1.0),  # Example filled order
    ]


@pytest.mark.parametrize(
  "trade, expected_function",
  [
    # Rebuy and grind only tags
    (MockTrade(False, "61"), "long_rebuy_adjust_trade_position"),  # Long rebuy tag
    (MockTrade(False, "120"), "long_grind_adjust_trade_position"),  # Long grind tag
    # Other tags
    (MockTrade(True, "620"), "short_grind_adjust_trade_position"),  # Short grind tag
    (MockTrade(False, "161"), "long_grind_adjust_trade_position"),  # Long derisk tag
    (MockTrade(False, "6"), "long_grind_adjust_trade_position"),  # Long normal tag
    (MockTrade(False, "81"), "long_grind_adjust_trade_position"),  # Long high profit tag
    (MockTrade(False, "41"), "long_grind_adjust_trade_position"),  # Long quick tag
    (MockTrade(False, "101"), "long_grind_adjust_trade_position"),  # Long rapid tag
    (MockTrade(False, "141"), "long_grind_adjust_trade_position"),  # Long top coins tag
    (MockTrade(False, "999"), "long_grind_adjust_trade_position"),  # Long unknown tag
    # Rebuy + grind tags
    (MockTrade(False, "61 120"), "long_rebuy_adjust_trade_position"),  # Long rebuy + long grind tags
    (MockTrade(False, "120 61"), "long_rebuy_adjust_trade_position"),  # Long grind + long rebuy tags
    # (Rebuy or grind) + other tags
    (MockTrade(False, "120 6"), "long_grind_adjust_trade_position"),  # Long grind + long normal tag
    (MockTrade(False, "61 6"), "long_grind_adjust_trade_position"),  # Long rebuy + long normal tag
    # No tags!
    (MockTrade(False, ""), "long_rebuy_adjust_trade_position"),  # Empty enter_tags
  ],
)
def test_adjust_trade_position(mock_config, mocker, trade, expected_function):
  """Test that adjust_trade_position calls the correct function."""
  strategy = NostalgiaForInfinityX5(mock_config)
  strategy.position_adjustment_enable = True

  # Mock adjustment functions
  strategy.long_rebuy_adjust_trade_position = mocker.MagicMock()
  strategy.long_grind_adjust_trade_position = mocker.MagicMock()
  strategy.short_grind_adjust_trade_position = mocker.MagicMock()

  # Derive enter_tags from trade.enter_tag
  enter_tags = trade.enter_tag.split()

  # Call adjust_trade_position
  strategy.adjust_trade_position(
    trade,
    current_time=None,
    current_rate=0.0,
    current_profit=0.0,
    min_stake=None,
    max_stake=10.0,
    current_entry_rate=0.0,
    current_exit_rate=0.0,
    current_entry_profit=0.0,
    current_exit_profit=0.0,
  )

  # Verify correct function call
  if expected_function:
    getattr(strategy, expected_function).assert_called_once_with(
      trade,
      enter_tags,
      None,
      0.0,
      0.0,
      None,
      10.0,
      0.0,
      0.0,
      0.0,
      0.0,
    )
  else:
    called_functions = []
    for func_name, func in [
      ("long_rebuy_adjust_trade_position", strategy.long_rebuy_adjust_trade_position),
      ("long_grind_adjust_trade_position", strategy.long_grind_adjust_trade_position),
      ("short_grind_adjust_trade_position", strategy.short_grind_adjust_trade_position),
    ]:
      if func.called:
        called_functions.append(f"{func_name} called with: {func.call_args_list}")

    if called_functions:
      pytest.fail(f"Unexpected function calls: {called_functions}")


@pytest.mark.parametrize(
  "trade, expected_calls, exit_returns",
  [
    # Single long entry tags
    (MockTrade(False, "1"), ["long_exit_normal"], {}),
    (MockTrade(False, "21"), ["long_exit_pump"], {}),
    (MockTrade(False, "41"), ["long_exit_quick"], {}),
    (MockTrade(False, "61"), ["long_exit_rebuy"], {}),
    (MockTrade(False, "81"), ["long_exit_high_profit"], {}),
    (MockTrade(False, "101"), ["long_exit_rapid"], {}),
    (MockTrade(False, "120"), ["long_exit_grind"], {}),
    (MockTrade(False, "141"), ["long_exit_top_coins"], {}),
    (MockTrade(False, "161"), ["long_exit_derisk"], {}),
    (MockTrade(False, "999"), ["long_exit_normal"], {}),
    # Single short entry tags
    (MockTrade(True, "500"), ["short_exit_normal"], {}),
    (MockTrade(True, "521"), ["short_exit_pump"], {}),
    (MockTrade(True, "541"), ["short_exit_quick"], {}),
    (MockTrade(True, "561"), ["short_exit_rebuy"], {}),
    (MockTrade(True, "581"), ["short_exit_high_profit"], {}),
    (MockTrade(True, "601"), ["short_exit_rapid"], {}),
    # TODO: FAILING TEST! Currently code calls short_exit_normal
    # (MockTrade(True, "620"), ["short_exit_grind"], {}),
    # TODO: FAILING TEST! Currently code calls short_exit_normal
    # (MockTrade(True, "641"), ["short_exit_top_coins"], {}),
    # TODO: FAILING TEST! Currently code calls short_exit_normal
    # (MockTrade(True, "661"), ["short_exit_derisk"], {}),
    # Combined long entry tags
    # normal + pump
    (MockTrade(False, "1 21"), ["long_exit_normal", "long_exit_pump"], {}),
    # rapid + rebuy + grind + derisk (rebuy, grind and derisk are all exclusive. Rapid can combine with the others)
    (MockTrade(False, "101 61 120 161"), ["long_exit_rapid"], {}),
    # long normal + pump + quick + high_profit + top_coins (all can combine together)
    (
      MockTrade(False, "1 21 41 81 141"),
      ["long_exit_normal", "long_exit_pump", "long_exit_quick", "long_exit_high_profit", "long_exit_top_coins"],
      {},
    ),
    # Combined entry tags that are exclusive
    # rebuy + grind
    (MockTrade(False, "61 120"), [], {}),
    # rebuy + grind + derisk
    (MockTrade(False, "61 120 161"), [], {}),
  ],
)
def test_custom_exit_calls_correct_functions(mock_config, mocker, trade, expected_calls, exit_returns):
  """Test to validate that custom_exit calls the correct exit functions."""
  # Instantiate the real strategy
  strategy = NostalgiaForInfinityX5(mock_config)

  # Mock the dp attribute to provide fake data
  strategy.dp = MagicMock()
  mocker.patch.object(
    strategy.dp,
    "get_analyzed_dataframe",
    return_value=(
      MagicMock(
        iloc=MagicMock(
          side_effect=[
            MagicMock(squeeze=lambda: {"close": 105.0, "RSI_14": 85.0, "BBU_20_2.0": 104.0}),
            MagicMock(squeeze=lambda: {"close": 104.0, "RSI_14": 83.0, "BBU_20_2.0": 103.0}),
            MagicMock(squeeze=lambda: {"close": 103.0, "RSI_14": 82.0, "BBU_20_2.0": 102.0}),
            MagicMock(squeeze=lambda: {"close": 102.0, "RSI_14": 81.0, "BBU_20_2.0": 101.0}),
            MagicMock(squeeze=lambda: {"close": 101.0, "RSI_14": 80.0, "BBU_20_2.0": 100.0}),
            MagicMock(squeeze=lambda: {"close": 100.0, "RSI_14": 79.0, "BBU_20_2.0": 99.0}),
          ]
        )
      ),
      None,
    ),
  )

  # Mock calc_total_profit to prevent ZeroDivisionError
  mocker.patch.object(strategy, "calc_total_profit", return_value=(100.0, 1.0, 0.1, 0.05))

  # Mock exit functions to track their calls
  functions_to_mock = [
    "long_exit_normal",
    "long_exit_rebuy",
    "long_exit_grind",
    "long_exit_pump",
    "long_exit_quick",
    "long_exit_rebuy",
    "long_exit_high_profit",
    "long_exit_rapid",
    "long_exit_top_coins",
    "long_exit_derisk",
    "short_exit_normal",
    "short_exit_pump",
    "short_exit_quick",
    "short_exit_rebuy",
    "short_exit_high_profit",
    "short_exit_rapid",
  ]
  mocked_functions = {}
  for func_name in functions_to_mock:
    # Set return value based on parameterized `exit_returns` or default to (False, None)
    return_value = exit_returns.get(func_name, (False, None)) if exit_returns else (False, None)
    mocked_functions[func_name] = mocker.patch.object(strategy, func_name, return_value=return_value)

  # Generic values for required parameters
  pair = "BTC/USDT"
  current_time = datetime(2023, 1, 1)  # Arbitrary date
  current_rate = 105.0  # Example current rate
  current_profit = 0.05  # Example profit

  # Call the real custom_exit function
  strategy.custom_exit(
    pair=pair,
    trade=trade,
    current_time=current_time,
    current_rate=current_rate,
    current_profit=current_profit,
  )

  # Verify the calls
  actual_calls = [func_name for func_name, mock in mocked_functions.items() if mock.call_count > 0]

  # Assert that the actual calls match the expected calls
  assert actual_calls == expected_calls, f"Expected calls: {expected_calls}, but got: {actual_calls}"


def test_update_signals_from_config(mock_config):
  """Test that the update_signals_from_config function correctly updates signals"""
  strategy = NostalgiaForInfinityX5(mock_config)  # mock_config is injected by pytest

  # Test setup with actual signals
  test_config = {
    "long_entry_signal_params": {
      "long_entry_condition_1_enable": False,
      "long_entry_condition_2_enable": True,
      "long_entry_condition_3_enable": False,
      "long_entry_condition_4_enable": True,
      "long_entry_condition_5_enable": False,
      "long_entry_condition_6_enable": True,
      "long_entry_condition_41_enable": False,
      "long_entry_condition_42_enable": True,
      "long_entry_condition_43_enable": False,
      "long_entry_condition_120_enable": True,
      "long_entry_condition_141_enable": False,
      "long_entry_condition_142_enable": True,
      "long_entry_condition_143_enable": False,
    },
    "short_entry_signal_params": {"short_entry_condition_501_enable": False},
  }

  # Save initial state of the signals
  initial_signals = {
    "long": dict(strategy.long_entry_signal_params),
    "short": dict(strategy.short_entry_signal_params),
  }

  strategy.update_signals_from_config(test_config)

  # Verify that the long signals were updated correctly
  for signal_name, value in test_config["long_entry_signal_params"].items():
    assert (
      strategy.long_entry_signal_params[signal_name] == value
    ), f"Mismatch in {signal_name}: expected {value}, got {strategy.long_entry_signal_params[signal_name]}"

  # Verify that the short signals were updated correctly
  for signal_name, value in test_config["short_entry_signal_params"].items():
    assert strategy.short_entry_signal_params[signal_name] == value

  # Verify that signals not included in the config retain their original values
  for signal_name in initial_signals["long"]:
    if signal_name not in test_config["long_entry_signal_params"]:
      assert strategy.long_entry_signal_params[signal_name] == initial_signals["long"][signal_name]

  for signal_name in initial_signals["short"]:
    if signal_name not in test_config["short_entry_signal_params"]:
      assert strategy.short_entry_signal_params[signal_name] == initial_signals["short"][signal_name]

  # Test with partial configuration
  partial_config = {"long_entry_signal_params": {"long_entry_condition_1_enable": True}}

  strategy.update_signals_from_config(partial_config)
  assert strategy.long_entry_signal_params["long_entry_condition_1_enable"] is True
  # Verify that other signals remain unchanged
  assert strategy.long_entry_signal_params["long_entry_condition_2_enable"] is True
