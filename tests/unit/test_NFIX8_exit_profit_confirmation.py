import json

import pytest

from tests.unit import test_NFIX8_bad_trade_profit as profit_tests


NOW = profit_tests.NOW
profit_case = profit_tests.profit_case


@pytest.mark.parametrize("offset_delta", [-0.0001, 0.0, 0.0001])
def test_profit_offset_keeps_current_stake_basis_and_inclusive_boundary(profit_case, offset_delta):
  strategy, trade = profit_case
  strategy.hold_support_enabled = False
  strategy.exit_profit_only = True
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 5.0, 98.0 if trade.is_short else 102.0)
  assert trade.realized_profit == pytest.approx(10.0)
  strategy.exit_profit_offset = 10.0 / trade.stake_amount + offset_delta

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, 100.0, "gtc", "exit_fixture", NOW)

  assert result is (offset_delta <= 0.0)


@pytest.mark.parametrize("profit_case", [(False, 3), (True, 3)], indirect=True, ids=["long", "short"])
@pytest.mark.parametrize("funding_fee", [-9.0, 9.0])
def test_profit_confirmation_includes_remaining_position_funding(profit_case, funding_fee):
  strategy, trade = profit_case
  strategy.hold_support_enabled = False
  strategy.exit_profit_only = True
  strategy.exit_profit_offset = 0.0
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 1.0, 90.0 if trade.is_short else 110.0)
  trade.set_funding_fees(funding_fee)
  rate = 102.0 if trade.is_short else 98.0
  assert trade.calculate_profit(rate).total_profit == pytest.approx(-8.0 + funding_fee)

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, rate, "gtc", "exit_fixture", NOW)

  assert result is (funding_fee > 8.0)


@pytest.mark.parametrize("reason", ["force_exit", "stop_loss", "trailing_stop_loss"])
def test_profit_confirmation_preserves_force_and_stop_rules(profit_case, reason):
  strategy, trade = profit_case
  strategy.hold_support_enabled = False
  strategy.exit_profit_only = True
  strategy.exit_profit_offset = 10.0 if reason == "force_exit" else 0.0
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 1.0, 90.0 if trade.is_short else 110.0)

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, 100.0, "gtc", reason, NOW)

  assert result is (reason == "force_exit")


def test_profit_confirmation_preserves_configured_hold(profit_case, tmp_path):
  strategy, trade = profit_case
  strategy.config["user_data_dir"] = tmp_path
  strategy.exit_profit_only = True
  strategy.exit_profit_offset = 0.0
  profit_tests.fill(trade, True, 10.0, 100.0)
  profit_tests.fill(trade, False, 1.0, 90.0 if trade.is_short else 110.0)
  (tmp_path / "nfi-hold-trades.json").write_text(json.dumps({"trade_ids": {str(trade.id): 1.0}}))

  result = strategy.confirm_trade_exit(trade.pair, trade, "limit", trade.amount, 100.0, "gtc", "exit_fixture", NOW)

  assert not result
