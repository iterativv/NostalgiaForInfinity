"""Long V4 queue-4/9 contracts through persistent orders and the public bot callback."""

from datetime import datetime
from datetime import timedelta
from itertools import count
from unittest.mock import MagicMock

import pytest
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import Trade
from freqtrade.wallets import Wallets

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8
from tests.unit import test_NFIX8_buyback_quantity as buyback
from tests.unit import test_NFIX8_grind_after_derisk as after
from tests.unit import test_NFIX8_legacy_grind_funding as legacy
from tests.unit import test_NFIX8_v4_grind_funding as funding
from tests.unit import test_NFIX8_v4_grind_funding_engine as engine
from tests.unit import test_NFIX8_v4_grind_quantity as quantity


NOW = funding.NOW
SETTING = "system_v4_grind_9_primary_gap"
v4_case = funding.v4_case
quantity_bot = quantity.quantity_bot
funding_case = engine.funding_case
funded_grind_case = engine.funded_grind_case
legacy_grind_case = legacy.legacy_grind_case
restore_database_sessions = after.restore_database_sessions


@pytest.fixture
def level():
  return 4


@pytest.fixture
def split_case(v4_case):
  strategy, trade, _ = v4_case
  # The funding fixture pins these values; this feature exercises the shipped queue-4 ladder.
  for market in ("spot", "futures"):
    for name in ("stakes", "thresholds", "derisk", "profit_threshold"):
      strategy.__dict__.pop(f"system_v4_grind_4_{name}_{market}", None)
  strategy.system_v4_grind_4_enable = True
  strategy.system_v4_grind_4_use_derisk = True
  strategy.long_grind_entry_v4 = MagicMock(return_value=True)
  strategy.dp.send_msg = MagicMock()
  trade.liquidation_price = None
  return strategy, trade


def add_fill(case, tag, amount=1.0, price=100.0, filled=None, side=None):
  _, trade = case
  funding.fill(trade, side or trade.entry_side, amount, price, tag, filled=filled)
  order = trade.orders[-1]
  # Keep modeled history older than both native retry/timing guards, even after a recycle.
  order.order_date = order.order_filled_date = NOW - timedelta(hours=7)
  Trade.session.flush()
  return order


def adjust(case, rate, max_stake=10000.0, min_stake=5.0, entry_rate=None):
  strategy, trade = case
  profit = trade.calc_profit_ratio(rate)
  return strategy.adjust_trade_position(
    trade,
    NOW,
    rate,
    profit,
    min_stake,
    max_stake,
    rate if entry_rate is None else entry_rate,
    rate,
    profit,
    profit,
  )


def candles(case, rate, signal=False, fallback=False, profit_exit=False):
  strategy, trade = case
  frame, _ = strategy.dp.get_analyzed_dataframe(trade.pair, "5m")
  frame = frame.assign(
    close=rate,
    RSI_3=100.0 if profit_exit else 50.0,
    RSI_3_15m=50.0,
    RSI_14=25.0 if fallback else 50.0,
    EMA_20=rate / 0.97,
    WILLR_14=-50.0,
    STOCHRSIk_14_14_3_3=50.0,
    protections_long_global=signal,
    enter_long=signal,
  )
  frame["BBU_20_2.0"] = rate * 2.0
  strategy.dp._set_cached_df(trade.pair, "5m", frame, strategy.config["candle_type_def"])


@pytest.fixture
def split_bot(quantity_bot, split_case):
  bot = quantity_bot
  _, trade = split_case
  bot.config.update(
    max_open_trades=6,
    stake_amount="unlimited",
    entry_pricing={"price_side": "other", "use_order_book": False},
  )
  bot.strategy.hold_support_enabled = bot.strategy.exit_profit_only = False
  bot.exchange.get_pair_quote_currency.return_value = "USDT"
  bot.exchange.get_fee.return_value = 0.0
  bot.exchange.get_precision_amount.return_value = 8
  bot.exchange.get_precision_price.return_value = 8
  bot.exchange.precisionMode = 2
  bot.exchange.get_contract_size.return_value = 1.0
  bot.exchange.price_to_precision.side_effect = lambda pair, price: price
  bot.exchange.amount_to_precision.side_effect = lambda pair, amount: round(amount, 8)
  bot.exchange.get_max_leverage.return_value = trade.leverage
  bot.exchange.get_option.side_effect = lambda name, default=None: default
  bot.rpc = MagicMock()
  bot.edge = None
  order_ids = count()

  def create_order(**kwargs):
    return {
      "id": f"split-{next(order_ids)}",
      "symbol": trade.pair,
      "type": "limit",
      "side": kwargs["side"],
      "status": "open",
      "price": kwargs["rate"],
      "amount": kwargs["amount"],
      "filled": 0.0,
      "remaining": kwargs["amount"],
      "cost": 0.0,
      "timestamp": int(NOW.timestamp() * 1000),
    }

  bot.exchange.create_order.side_effect = create_order
  return bot


def settle(bot, trade, order, filled=None, status="closed", when=NOW):
  filled = order.amount if filled is None else filled
  buyback.settle_exit(trade, order, filled, status)
  order.order_filled_date = when
  bot.strategy.order_filled(trade.pair, trade, order, when)
  Trade.session.flush()
  bot.wallets.update()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("signal", ["native", "fallback"])
def test_real_engine_places_and_settles_original_first_four_allocations(split_bot, split_case, mocker, caplog, signal):
  strategy, trade = split_case
  trade.orders[-1].ft_order_tag = "seed"
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  # Restore the real entry executor: only the exchange and notification boundaries are mocked.
  split_bot.execute_entry = FreqtradeBot.execute_entry.__get__(split_bot)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime).now
  expected = [(90.0, 50.0, 4), (82.0, 60.0, 4), (76.0, 70.0, 9), (69.0, 80.0, 9)]

  for index, (rate, stake, queue) in enumerate(expected):
    clock.return_value = NOW + timedelta(hours=7 * index)
    candles(split_case, rate, signal=signal == "native", fallback=signal == "fallback")
    split_bot.exchange.get_rates.return_value = (rate, rate)
    split_bot.exchange.create_order.reset_mock()
    before = trade.amount

    split_bot.check_and_call_adjust_trade_position(trade)

    assert adjustment.spy_exception is None
    assert adjustment.spy_return == (pytest.approx(stake / trade.leverage), f"grind_{queue}_entry")
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_{queue}_entry"
    assert order.ft_order_side == trade.entry_side
    assert order.amount * rate / trade.leverage == pytest.approx(stake / trade.leverage, abs=1e-6)
    assert strategy._grind_entry_tag == (f"g{queue}_fb1" if signal == "fallback" else ("g9" if queue == 9 else "g0"))
    settle(split_bot, trade, order, when=clock.return_value)
    assert trade.amount == pytest.approx(before + order.amount, abs=1e-8)

  clock.return_value += timedelta(hours=7)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return is None
  split_bot.exchange.create_order.assert_not_called()
  assert [o.ft_order_tag for o in trade.select_filled_orders(trade.entry_side)][-4:] == [
    "grind_4_entry",
    "grind_4_entry",
    "grind_9_entry",
    "grind_9_entry",
  ]
  lower_amount = sum(o.safe_filled for o in trade.orders if o.ft_order_tag == "grind_9_entry")
  clock.return_value += timedelta(hours=7)
  candles(split_case, 80.0, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (80.0, 80.0)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_called_once()
  reduction = trade.orders[-1]
  assert reduction.ft_order_tag.startswith("grind_9_exit ")
  assert reduction.amount == pytest.approx(lower_amount, abs=1e-8)
  settle(split_bot, trade, reduction, when=clock.return_value)

  # A fresh native signal can recycle the lower queue while the same two parents remain.
  clock.return_value += timedelta(hours=7)
  candles(split_case, 76.0, signal=True)
  split_bot.exchange.get_rates.return_value = (76.0, 76.0)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  assert adjustment.spy_return == (pytest.approx(70.0 / trade.leverage), "grind_9_entry")
  split_bot.exchange.create_order.assert_called_once()
  assert trade.orders[-1].ft_order_tag == "grind_9_entry"
  settle(split_bot, trade, trade.orders[-1], when=clock.return_value)
  assert all(record.levelno < 40 for record in caplog.records)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0), (False, 5.0)], indirect=True)
@pytest.mark.parametrize("offset,allowed", [(-0.0001, True), (0.0, True), (0.0001, False)])
def test_lower_admission_uses_current_quantity_weighted_raw_price(split_case, offset, allowed):
  strategy, trade = split_case
  latest_parent = add_fill(split_case, "grind_4_entry", 3.0, 80.0)
  # One unit at 100 plus three at 80 gives 85, irrespective of the whole-trade average or leverage.
  rate = 85.0 * 0.90 + offset
  # The weighted gate passes at 76.5 while the old third-step -8% band from the last 80 fill does not.
  assert (rate - latest_parent.safe_price) / latest_parent.safe_price > -0.08
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  candles(split_case, rate, signal=True)

  result = adjust(split_case, rate)

  assert result == ((pytest.approx(70.0 / trade.leverage), "grind_9_entry") if allowed else None)
  if allowed:
    assert strategy._grind_entry_tag == "g9"


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_parent_gate_compares_entry_quote_instead_of_exit_quote(split_case):
  add_fill(split_case, "grind_4_entry", 3.0, 80.0)
  assert adjust(split_case, 74.0, entry_rate=76.5001) is None
  assert adjust(split_case, 74.0, entry_rate=76.5)[1] == "grind_9_entry"


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("gap,allowed", [(0.10, True), (0.11, False)])
def test_gap_is_a_safe_long_only_configuration_parameter(split_case, tmp_path, nested, gap, allowed):
  strategy, trade = split_case
  add_fill(split_case, "grind_4_entry")
  config = strategy.config.copy()
  config.update(user_data_dir=tmp_path, trading_mode=trade.trading_mode, nfi_advanced_mode=False)
  config["nfi_parameters"] = {SETTING: gap} if nested else {}
  if not nested:
    config[SETTING] = gap
  strategy.target_profit_cache = MagicMock()
  strategy.__init__(config)

  result = adjust(split_case, 90.0)

  assert getattr(strategy, SETTING) == gap
  assert result == ((pytest.approx(70.0), "grind_9_entry") if allowed else None)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "state,eligible",
  [
    ("empty", False),
    ("one", False),
    ("two", True),
    ("unfilled-canceled", False),
    ("unfilled-open", False),
    ("closed-then-one", False),
    ("closed-then-two", True),
    ("overfull-3", False),
    ("overfull-4", False),
    ("overfull-5", False),
  ],
)
def test_only_two_current_filled_parents_unlock_lower_queue(split_case, state, eligible):
  _, trade = split_case
  if state == "empty":
    trade.orders[-1].ft_order_tag = "seed"
  elif state.startswith("unfilled"):
    order = add_fill(split_case, "grind_4_entry", filled=0.0)
    if state == "unfilled-open":
      order.ft_is_open = True
      order.status = "open"
  elif state.startswith("closed"):
    add_fill(split_case, "grind_4_entry")
    add_fill(split_case, "grind_4_exit old-cluster", 2.0, side=trade.exit_side)
    add_fill(split_case, "grind_4_entry")
    if state == "closed-then-two":
      add_fill(split_case, "grind_4_entry")
  elif state == "two":
    add_fill(split_case, "grind_4_entry")
  elif state.startswith("overfull"):
    for _ in range(int(state[-1]) - 1):
      add_fill(split_case, "grind_4_entry")

  result = adjust(split_case, 90.0)

  if eligible:
    assert result == (pytest.approx(70.0 / trade.leverage), "grind_9_entry")
  else:
    assert result is None or result[1] != "grind_9_entry"


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("parents", [3, 4, 5])
def test_old_overfull_parent_inventory_is_still_fully_reduced(split_case, parents):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  for _ in range(parents - 1):
    add_fill(split_case, "grind_4_entry")
  expected_ids = " ".join(str(order.id) for order in reversed(trade.orders[2:]))
  expected_stake = parents * trade.stake_amount / trade.amount

  result = adjust(split_case, 77.0)

  assert result == (pytest.approx(-expected_stake), f"grind_4_derisk {expected_ids}")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("length", [0, 1, 2, 3, 4, 5])
def test_custom_ladder_only_supplies_actual_remaining_scaled_allocations(split_case, length):
  strategy, trade = split_case
  original = [0.03, 0.04, 0.08, 0.11, 0.20][:length]
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_4_stakes_{market}", original)
  add_fill(split_case, "grind_4_entry")
  minimum = 40.0 / trade.leverage
  result = adjust(split_case, 90.0, min_stake=minimum)
  if length <= 2:
    assert result is None
    return
  # Scale the original first step from 30 to 40 before taking the original third step, 80 * 4/3.
  assert result == (pytest.approx((80.0 * 4.0 / 3.0) / trade.leverage), "grind_9_entry")
  add_fill(split_case, result[1], result[0] * trade.leverage / 90.0, 90.0)
  result = adjust(split_case, 81.0, min_stake=minimum)
  if length == 3:
    assert result is None
  else:
    assert result == (pytest.approx((110.0 * 4.0 / 3.0) / trade.leverage), "grind_9_entry")
    add_fill(split_case, result[1], result[0] * trade.leverage / 81.0, 81.0)
    assert adjust(split_case, 80.0, min_stake=minimum) is None
  assert strategy.system_v4_grind_4_stakes_spot == original


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_parent_third_entry_is_blocked_even_when_original_third_spacing_is_met(split_case):
  strategy, _ = split_case
  add_fill(split_case, "grind_4_entry")
  strategy.system_v4_grind_9_primary_gap = 0.20
  assert adjust(split_case, 90.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("length", [0, 1])
def test_parent_cap_respects_a_short_custom_ladder(split_case, length):
  strategy, _ = split_case
  for market in ("spot", "futures"):
    setattr(strategy, f"system_v4_grind_4_stakes_{market}", [0.05][:length])
  assert adjust(split_case, 90.0) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize(
  "gate", ["retry", "timing", "stake", "wallet", "queue", "spacing", "open_order", "signal", "unlock"]
)
def test_lower_admission_retains_native_guards(split_case, gate):
  strategy, trade = split_case
  parent = add_fill(split_case, "grind_4_entry")
  max_stake = 10000.0
  if gate == "retry":
    parent.order_filled_date = NOW - timedelta(minutes=4)
  elif gate == "timing":
    parent.order_filled_date = NOW - timedelta(minutes=10)
    add_fill(split_case, "exit_normal", 0.1, 90.0, side=trade.exit_side).order_filled_date = NOW - timedelta(minutes=9)
  elif gate == "stake":
    strategy.system_v4_max_stake = 0.1
  elif gate == "wallet":
    max_stake = 1.0
  elif gate == "queue":
    add_fill(split_case, "grind_9_entry", 0.1)
    add_fill(split_case, "grind_9_entry", 0.1)
  elif gate == "spacing":
    add_fill(split_case, "grind_9_entry", 0.1, 98.0)
  elif gate == "open_order":
    order = add_fill(split_case, "grind_9_entry", filled=0.0)
    order.ft_is_open = True
    order.status = "open"
  elif gate == "signal":
    strategy.long_grind_entry_v4.return_value = False
  else:
    strategy.system_v4_grind_only_after_derisk_enable = True
  assert adjust(split_case, 90.0, max_stake=max_stake) is None


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_lower_uses_its_own_original_fourth_step_spacing_and_recycles(split_bot, split_case):
  strategy, trade = split_case
  add_fill(split_case, "grind_4_entry")
  add_fill(split_case, "grind_9_entry", 0.5, 90.0)
  assert adjust(split_case, 82.0) is None  # Passes the old second-step -7%, but not the original fourth-step -9%.
  result = adjust(split_case, 81.0)
  assert result == (pytest.approx(80.0 / trade.leverage), "grind_9_entry")
  add_fill(split_case, result[1], result[0] * trade.leverage / 81.0, 81.0)
  assert adjust(split_case, 80.0) is None
  entries = [o for o in trade.orders if o.ft_order_tag == "grind_9_entry"]
  tag = "grind_9_exit " + " ".join(str(o.id) for o in reversed(entries))
  closed = add_fill(split_case, tag, sum(o.safe_filled for o in entries), 95.0, side=trade.exit_side)
  strategy.order_filled(trade.pair, trade, closed, NOW)
  assert adjust(split_case, 90.0) == (pytest.approx(70.0 / trade.leverage), "grind_9_entry")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("parent_exit", ["exit", "derisk"])
@pytest.mark.parametrize("reason,rate", [("exit", 85.0), ("derisk", 50.0)])
def test_lower_exit_and_derisk_survive_parent_close_and_database_reload(
  split_bot, split_case, mocker, caplog, parent_exit, reason, rate
):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  second_parent = add_fill(split_case, "grind_4_entry")
  first = add_fill(split_case, "grind_9_entry", 0.6, 80.0)
  second = add_fill(split_case, "grind_9_entry", 0.8, 70.0)
  candles(split_case, 82.0)
  assert adjust(split_case, 82.0) is None
  high_water = trade.get_custom_data("grind_9_cluster_max_profit_rate")
  assert high_water > 0.0
  trade.set_custom_data("grind_4_cluster_max_profit_rate", 1.0)
  parent = add_fill(
    split_case, f"grind_4_{parent_exit} {second_parent.id} {trade.orders[2].id}", 2.0, side=trade.exit_side
  )
  strategy.order_filled(trade.pair, trade, parent, NOW)
  assert trade.get_custom_data("grind_4_cluster_max_profit_rate") == 0.0
  assert trade.get_custom_data("grind_9_cluster_max_profit_rate") == high_water
  trade_id = trade.id
  Trade.session.flush()
  Trade.session.expunge_all()
  trade = Trade.session.get(Trade, trade_id)
  assert trade.get_custom_data("system_version") == "system_v4"
  candles((strategy, trade), rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_called_once()
  order = trade.orders[-1]
  assert order.ft_order_tag == f"grind_9_{reason} {second.id} {first.id}"
  assert order.amount == pytest.approx(1.4, abs=1e-8)
  settle(split_bot, trade, order)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)
  assert trade.get_custom_data("grind_9_cluster_max_profit_stake") == 0.0
  assert trade.get_custom_data("grind_9_cluster_max_profit_rate") == 0.0
  assert all(record.levelno < 40 for record in caplog.records)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 90.0), ("derisk", 60.0)])
def test_actual_partial_lower_reduction_retries_only_net_remainder_after_reload(
  split_bot, split_case, mocker, reason, rate
):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  # Close the only parent; the lower inventory must manage itself independently.
  add_fill(split_case, "grind_4_derisk 3", 1.0, side=trade.exit_side)
  entry = add_fill(split_case, "grind_9_entry", 1.0, 80.0)
  quantity.settle_base_fee(split_bot, trade, entry, 0.001)
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  first = trade.orders[-1]
  assert first.ft_order_tag == f"grind_9_{reason} {entry.id}"
  assert first.amount == pytest.approx(0.999, abs=1e-8)
  settle(split_bot, trade, first, 0.4, "canceled")
  trade_id = trade.id
  Trade.session.expunge_all()
  trade = Trade.session.get(Trade, trade_id)
  split_bot.exchange.create_order.reset_mock()

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_called_once()
  retry = trade.orders[-1]
  assert retry.ft_order_tag == first.ft_order_tag
  assert retry.amount == pytest.approx(0.599, abs=1e-8)
  settle(split_bot, trade, retry)
  assert trade.amount == pytest.approx(6.0, abs=1e-8)
  split_bot.exchange.create_order.reset_mock()
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_partial_parent_exit_retries_before_any_lower_admission(split_bot, split_case, mocker):
  _, trade = split_case
  parent = add_fill(split_case, "grind_4_entry")
  canceled = add_fill(split_case, f"grind_4_exit {parent.id} 3", 2.0, 90.0, filled=0.4, side=trade.exit_side)
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  adjustment = mocker.spy(split_bot.strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  retry = trade.orders[-1]
  assert retry.ft_order_tag == canceled.ft_order_tag
  assert retry.amount == pytest.approx(1.6, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("amount,eligible", [(0.03, False), (0.0390625, False), (0.046875, True)])
def test_lower_profit_exit_uses_current_value_minimum(split_bot, split_case, mocker, amount, eligible):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  trade.orders[-1].ft_order_tag = "seed"
  entry = add_fill(split_case, "grind_9_entry", amount)
  candles(split_case, 128.0, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (128.0, 128.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  split_bot.check_and_call_adjust_trade_position(trade)
  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  if eligible:
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_9_exit {entry.id}"
    assert order.amount == pytest.approx(amount, abs=1e-8)
    assert -adjustment.spy_return[0] < 5.0
  else:
    split_bot.exchange.create_order.assert_not_called()


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 110.0), ("derisk", 77.0)])
def test_lower_fee_aware_reduction_preserves_minimum_residual(split_bot, split_case, reason, rate):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  previous_exit = trade.orders[1]
  previous_exit.amount = previous_exit.ft_amount = previous_exit.filled = 9.99
  previous_exit.cost = 999.0
  trade.orders[-1].ft_order_tag = "grind_9_entry"
  trade.recalc_trade_from_orders()
  quantity.settle_base_fee(split_bot, trade, trade.orders[-1], 0.001)
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  split_bot.check_and_call_adjust_trade_position(trade)
  order = trade.orders[-1]
  assert order.ft_order_tag.startswith(f"grind_9_{reason} ")
  assert order.amount == pytest.approx(1.009 - 5.0 * 1.55 / rate, abs=1e-8)
  assert order.amount < 0.999
  settle(split_bot, trade, order)
  assert trade.amount * rate == pytest.approx(5.0 * 1.55, abs=1e-6)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("funding_ratio", [0.0, 0.999, 1.0])
def test_real_wallet_full_deployment_blocks_lower_add_without_hiding_its_derisk(
  split_bot, split_case, mocker, funding_ratio
):
  strategy, trade = split_case
  add_fill(split_case, "grind_4_entry")
  entry = add_fill(split_case, "grind_9_entry", 1.0, 110.0)
  proposal = 80.0 / trade.leverage
  free = proposal * funding_ratio
  split_bot.config["dry_run_wallet"] = trade.stake_amount - trade.realized_profit + free
  split_bot.wallets = Wallets(split_bot.config, split_bot.exchange)
  assert split_bot.wallets.get_available_stake_amount() == pytest.approx(free)
  split_bot.exchange.get_rates.return_value = (85.0, 85.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(free)
  if funding_ratio == 1.0:
    split_bot.execute_entry.assert_called_once_with(
      trade.pair, proposal, price=85.0, trade=trade, is_short=False, mode="pos_adjust", enter_tag="grind_9_entry"
    )
    split_bot.exchange.create_order.assert_not_called()
  else:
    split_bot.execute_entry.assert_not_called()
    split_bot.exchange.create_order.assert_called_once()
    assert trade.orders[-1].ft_order_tag == f"grind_9_derisk {entry.id}"
    assert trade.orders[-1].amount == pytest.approx(1.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("emergency", [False, True])
def test_native_queue_five_and_emergency_keep_priority_over_lower_queue(split_case, emergency):
  strategy, trade = split_case
  add_fill(split_case, "grind_4_entry")
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  candles(split_case, 84.0)
  strategy.system_v4_grind_5_enable = True
  trade.liquidation_price = 80.0
  if emergency:
    strategy.derisk_enable = True
    strategy.system_v4_derisk_level_3_enable = True
    strategy.system_v4_derisk_level_3_liquidation_enable = True
  result = adjust(split_case, 84.0)
  if emergency:
    assert result == (pytest.approx(-500.0 / trade.leverage), "derisk_level_3")
  else:
    assert result == (pytest.approx(50.0 / trade.leverage), "grind_5_entry")
    assert strategy._grind_entry_tag == "g5_liq1"


@pytest.mark.parametrize("v4_case", [(False, 3.0)], indirect=True)
@pytest.mark.parametrize("lower", [9, 8, 10])
@pytest.mark.parametrize("inventory,eligible", [(1, True), (2, False)])
def test_lower_inventory_counts_toward_native_queue_five_rescue_limit(split_case, inventory, eligible, lower):
  strategy, trade = split_case
  strategy.long_grind_entry_v4 = NostalgiaForInfinityX8.long_grind_entry_v4.__get__(strategy)
  strategy.system_v4_grind_5_enable = True
  strategy.system_v4_grind_5_liquidation_rescue_enable = True
  add_fill(split_case, "grind_4_exit 3", 1.0, side=trade.exit_side)
  add_fill(split_case, "exit_normal", 4.0, side=trade.exit_side)
  for _ in range(inventory):
    add_fill(split_case, f"grind_{lower}_entry", 0.1)
  candles(split_case, 93.9)
  trade.liquidation_price = 90.0
  result = adjust(split_case, 93.9)
  assert result == ((pytest.approx(50.0 / trade.leverage), "grind_5_entry") if eligible else None)
  if eligible:
    assert strategy._grind_entry_tag == "g5_liq2"


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
def test_global_derisk_ends_lower_cluster_under_existing_order_protocol(split_case):
  strategy, trade = split_case
  strategy.system_v4_grind_4_enable = False
  strategy.long_grind_entry_v4.return_value = False
  add_fill(split_case, "grind_9_entry", 0.5, 80.0)
  add_fill(split_case, "derisk_global", 0.5, 90.0, side=trade.exit_side)
  candles(split_case, 110.0, profit_exit=True)
  assert adjust(split_case, 110.0) is None


@pytest.mark.parametrize("v4_case", [(True, 3.0)], indirect=True)
def test_short_retains_all_original_queue_four_steps(split_case):
  strategy, trade = split_case
  strategy.system_v4_max_stake = 2.0
  strategy.system_v4_grind_9_primary_gap = 0.99
  for rate, stake in [(114.0, 60.0), (128.0, 70.0), (144.0, 80.0), (162.0, 90.0)]:
    result = adjust(split_case, rate)
    assert result == (pytest.approx(stake / trade.leverage), "grind_4_entry")
    add_fill(split_case, result[1], result[0] * trade.leverage / rate, rate)
  result = adjust(split_case, 162.0)
  assert result is not None and result[1].startswith("grind_4_derisk ")


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize(
  "funding_case",
  [(None, 4, "grind"), ("system_v3", 4, "grind"), ("system_v3_1", 4, "grind"), ("system_v3_2", 4, "grind")],
  indirect=True,
)
def test_earlier_systems_still_admit_original_third_parent_step(funded_grind_case):
  strategy, trade, rate = funded_grind_case
  strategy.long_grind_entry_v3 = MagicMock(return_value=True)
  prefix = "grinding_v2" if trade.get_custom_data("system_version") is None else "system_v3"
  setattr(strategy, f"{prefix}_max_stake", 2.0)
  strategy.system_v4_grind_9_primary_gap = 0.99
  add_fill((strategy, trade), "grind_4_entry")
  assert funding.adjust((strategy, trade, rate), 10000.0) == (pytest.approx(150.0), "grind_4_entry")


def test_legacy_grind_mode_keeps_its_existing_route(legacy_grind_case):
  strategy, trade, _ = legacy_grind_case
  strategy.system_v4_grind_9_primary_gap = 0.99
  assert legacy.adjust(legacy_grind_case, 1000.0) == (pytest.approx(140.0 / trade.leverage), "gd1")


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_lower_pre_derisk_entry_uses_its_own_average_and_diagnostic(split_case):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  strategy.system_v4_grind_entry_before_derisk_enable = True
  add_fill(split_case, "grind_4_entry")
  add_fill(split_case, "grind_9_entry", 1.0, 110.0)
  result = adjust(split_case, 87.0)
  assert result == (pytest.approx(80.0 / trade.leverage), "grind_9_entry")
  assert strategy._grind_entry_tag == "g9_pre_derisk"


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("queue,stake", [(1, 200.0), (2, 100.0), (3, 100.0), (5, 50.0), ("buyback", 1000.0)])
def test_existing_queue_and_buyback_decisions_precede_lower_admission(split_case, queue, stake):
  strategy, trade = split_case
  add_fill(split_case, "grind_4_entry")
  if queue == "buyback":
    strategy.system_v4_buyback_1_enable = True
    strategy.long_buyback_entry_v4 = MagicMock(return_value=True)
    add_fill(split_case, "derisk_level_4", 0.1, side=trade.exit_side)
    tag = "buyback_1_entry"
  else:
    setattr(strategy, f"system_v4_grind_{queue}_enable", True)
    tag = f"grind_{queue}_entry"
  assert adjust(split_case, 90.0) == (pytest.approx(stake / trade.leverage), tag)


@pytest.mark.parametrize("v4_case", [(False, 1.0)], indirect=True)
@pytest.mark.parametrize(
  "requested,filled,prior_exit,eligible,full_close",
  [
    (0.5, 0.453125, 4.0, True, False),
    (0.5, 0.4609375, 4.0, False, False),
    (0.5, 0.47, 4.0, False, False),
    (1.0, 0.91, 9.99, False, False),
    (7.0, 6.953125, 4.0, True, True),
  ],
  ids=["current-value-only", "exact-minimum", "below-minimum", "reserve", "full-close"],
)
def test_lower_partial_retry_retains_minimum_reserve_and_full_close_rules(
  split_bot, split_case, mocker, requested, filled, prior_exit, eligible, full_close
):
  strategy, trade = split_case
  strategy.system_v4_grind_4_enable = False
  strategy.long_grind_entry_v4.return_value = False
  trade.orders[-1].ft_order_tag = "grind_9_entry"
  prior = trade.orders[1]
  prior.amount = prior.ft_amount = prior.filled = prior_exit
  prior.cost = prior_exit * 100.0
  trade.recalc_trade_from_orders()
  tag = f"grind_9_exit {trade.orders[-1].id}"
  canceled = add_fill(split_case, tag, requested, 128.0, filled=filled, side=trade.exit_side)
  candles(split_case, 128.0, profit_exit=True)
  split_bot.exchange.get_rates.return_value = (128.0, 128.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  split_bot.execute_entry.assert_not_called()
  if eligible:
    split_bot.exchange.create_order.assert_called_once()
    retry = trade.orders[-1]
    assert retry is not canceled
    assert retry.ft_order_tag == tag
    assert retry.amount == pytest.approx(requested - filled, abs=1e-8)
    settle(split_bot, trade, retry)
    assert trade.is_open is not full_close
  else:
    split_bot.exchange.create_order.assert_not_called()
    assert trade.orders[-1] is canceled


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
@pytest.mark.parametrize("reason,rate", [("exit", 85.0), ("derisk", 50.0)])
@pytest.mark.parametrize("funded", [False, True])
def test_buyback_funding_preserves_existing_lower_management(split_bot, split_case, mocker, reason, rate, funded):
  strategy, trade = split_case
  strategy.long_grind_entry_v4.return_value = False
  strategy.system_v4_buyback_1_enable = True
  strategy.long_buyback_entry_v4 = MagicMock(return_value=True)
  first_parent = trade.orders[-1]
  second_parent = add_fill(split_case, "grind_4_entry")
  lower = add_fill(split_case, "grind_9_entry", 1.0, 80.0)
  add_fill(split_case, f"grind_4_exit {second_parent.id} {first_parent.id}", 2.0, 100.0, side=trade.exit_side)
  add_fill(split_case, "derisk_level_4", 0.1, 100.0, side=trade.exit_side)
  buyback_stake = 1000.0 / trade.leverage
  free = buyback_stake * (1.25 if funded else 0.1)
  split_bot.config["dry_run_wallet"] = trade.stake_amount - trade.realized_profit + free
  split_bot.wallets = Wallets(split_bot.config, split_bot.exchange)
  assert split_bot.wallets.get_available_stake_amount() == pytest.approx(free)
  candles(split_case, rate, profit_exit=reason == "exit")
  split_bot.exchange.get_rates.return_value = (rate, rate)
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  before = trade.amount

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  strategy.long_buyback_entry_v4.assert_called_once()
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(free)
  if funded:
    split_bot.execute_entry.assert_called_once_with(
      trade.pair,
      buyback_stake,
      price=rate,
      trade=trade,
      is_short=False,
      mode="pos_adjust",
      enter_tag="buyback_1_entry",
    )
    split_bot.exchange.create_order.assert_not_called()
  else:
    split_bot.execute_entry.assert_not_called()
    split_bot.exchange.create_order.assert_called_once()
    order = trade.orders[-1]
    assert order.ft_order_tag == f"grind_9_{reason} {lower.id}"
    assert order.amount == pytest.approx(1.0, abs=1e-8)
    settle(split_bot, trade, order)
    assert trade.amount == pytest.approx(before - 1.0, abs=1e-8)


@pytest.mark.parametrize("v4_case", [(False, 1.0), (False, 3.0)], indirect=True)
def test_unfunded_buyback_still_blocks_a_cheaper_new_lower_entry(split_bot, split_case, mocker):
  strategy, trade = split_case
  strategy.system_v4_buyback_1_enable = True
  strategy.long_buyback_entry_v4 = MagicMock(return_value=True)
  add_fill(split_case, "grind_4_entry")
  add_fill(split_case, "derisk_level_4", 0.1, 100.0, side=trade.exit_side)
  free = 100.0 / trade.leverage
  split_bot.config["dry_run_wallet"] = trade.stake_amount - trade.realized_profit + free
  split_bot.wallets = Wallets(split_bot.config, split_bot.exchange)
  candles(split_case, 90.0)
  split_bot.exchange.get_rates.return_value = (90.0, 90.0)
  adjustment = mocker.spy(strategy, "adjust_trade_position")

  split_bot.check_and_call_adjust_trade_position(trade)

  assert adjustment.spy_exception is None
  strategy.long_buyback_entry_v4.assert_called_once()
  assert adjustment.call_args.kwargs["max_stake"] == pytest.approx(free)
  assert free > (70.0 / trade.leverage)
  split_bot.execute_entry.assert_not_called()
  split_bot.exchange.create_order.assert_not_called()
