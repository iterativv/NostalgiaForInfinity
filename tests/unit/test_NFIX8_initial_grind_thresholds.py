"""Initial exits honor the configured threshold for their trading mode."""

import pytest

from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_liquidation_rescue as rescue


rescue_case = rescue.rescue_case
buyback_quantity_bot = buyback.buyback_quantity_bot
CASES = [
  pytest.param(("profit", 0.015625, 0.0625, 0.001, True, (True, False)), id="profit-futures-hold"),
  pytest.param(("profit", 0.0625, 0.015625, 0.001, True, (False, True)), id="profit-futures-exit"),
  pytest.param(("profit", 0.03125, 0.03125, 0.0, True, (False, False)), id="profit-equality"),
  pytest.param(("profit", 0.015625, 0.015625, 0.0078125, True, (False, False)), id="profit-fee-equality"),
  pytest.param(("profit", None, None, 0.001, False, (True, True)), id="profit-default"),
  pytest.param(("profit", 0.0625, 0.0625, 0.001, False, (True, True)), id="profit-unsafe-ignored"),
  pytest.param(("profit", 0.015625, 0.015625, 0.001, True, (True, True)), id="profit-equal-settings-exit"),
  pytest.param(("profit", 0.0625, 0.0625, 0.001, True, (False, False)), id="profit-equal-settings-hold"),
  pytest.param(("stop", -0.125, -0.5, 0.001, True, (True, False)), id="stop-futures-hold"),
  pytest.param(("stop", -0.5, -0.125, 0.001, True, (False, True)), id="stop-futures-exit"),
  pytest.param(("stop", -0.25, -0.25, 0.001, True, (False, False)), id="stop-equality"),
  pytest.param(("stop", None, None, 0.001, False, (True, True)), id="stop-default"),
  pytest.param(("stop", -0.5, -0.5, 0.001, False, (True, True)), id="stop-unsafe-ignored"),
  pytest.param(("stop", -0.125, -0.125, 0.001, True, (True, True)), id="stop-equal-settings-exit"),
  pytest.param(("stop", -0.5, -0.5, 0.001, True, (False, False)), id="stop-equal-settings-hold"),
]


@pytest.mark.parametrize(
  "rescue_case", [(False, 1), (False, 3), (True, 3)], indirect=True, ids=["spot", "long", "short"]
)
@pytest.mark.parametrize("case", CASES)
def test_initial_exit_uses_its_market_threshold(buyback_quantity_bot, mocker, tmp_path, caplog, case):
  kind, spot, futures, fee, advanced, allowed = case
  bot, trade, _ = buyback_quantity_bot
  prefix = f"grind_mode_first_entry_{kind}_threshold"
  config = bot.strategy.config.copy()
  config.update(
    user_data_dir=tmp_path,
    nfi_advanced_mode=advanced,
    nfi_parameters={} if spot is None else {f"{prefix}_spot": spot, f"{prefix}_futures": futures},
  )
  # Use the real configuration loader, including its advanced-mode restriction.
  bot.strategy.__init__(config)
  bot.config = bot.strategy.config
  trade.enter_tag = "620" if trade.is_short else "120"
  trade.fee_open = trade.fee_close = fee
  first = trade.orders[0]
  first.ft_order_tag = trade.enter_tag
  first.price = first.average = first.ft_price = 128.0
  first.cost = first.filled * first.price
  trade.recalc_trade_from_orders()
  mocker.patch.object(bot.strategy, "long_grind_entry", return_value=False)
  mocker.patch.object(bot.strategy, "short_grind_entry", return_value=False)
  move = {"profit": 0.03125, "stop": -0.25}[kind]
  rate = 128.0 * (1.0 - move if trade.is_short else 1.0 + move)
  bot.exchange.get_rates.return_value = (rate, rate)
  bot.exchange.get_max_pair_stake_amount.return_value = 0.0
  before = trade.amount

  bot.check_and_call_adjust_trade_position(trade)

  assert all(record.levelno < 40 for record in caplog.records)
  bot.execute_entry.assert_not_called()
  if not allowed[trade.leverage > 1]:
    bot.exchange.create_order.assert_not_called()
    assert trade.amount == before
    return
  bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_side == trade.exit_side
  assert order.ft_order_tag == {"profit": "gm0", "stop": "gmd0"}[kind]
  # Ten coins less the unchanged 7.75 quote reserve, at exchange precision.
  expected = {132.0: 9.94128787, 124.0: 9.9375, 96.0: 9.91927083, 160.0: 9.9515625}[rate]
  buyback.assert_exit_units(order, expected)
  buyback.settle_exit(trade, order, order.amount)
  assert trade.amount == pytest.approx(before - expected, rel=0, abs=1e-8)
  assert trade.is_open
