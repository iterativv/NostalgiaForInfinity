"""Official exit-order creation, fill and close with real registry semantics."""

from datetime import datetime, timedelta
from functools import wraps
from unittest.mock import MagicMock

import pandas as pd
import pytest
from freqtrade.enums import ExitCheckTuple, ExitType, MarginMode, RunMode, State
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.optimize.backtesting import Backtesting
from freqtrade.persistence import LocalTrade, Trade
from freqtrade.wallets import Wallets

from tests.unit import nfix8_demand_fixtures as fixtures
from tests.unit.nfix8_demand_fixtures import DUE, EXIT, KEY, make_d1


database = fixtures.database
case = fixtures.case


@pytest.mark.parametrize("change", ["unchanged", "price", "funding", "next_candle"])
def test_bot_exit_before_adjust_then_later_exit_in_due_candle(case, mocker, change):
  strategy = case.strategy
  strategy.config.update(
    runmode=RunMode.DRY_RUN,
    dry_run=True,
    dry_run_wallet=100000.0,
    tradable_balance_ratio=1.0,
    trading_mode=case.trade.trading_mode,
  )
  bot = FreqtradeBot.__new__(FreqtradeBot)
  bot.config = strategy.config
  bot.strategy = strategy
  bot.trading_mode = case.trade.trading_mode
  bot.state = State.RUNNING
  bot._exit_reason_cache = {}
  bot.exchange = MagicMock()
  bot.exchange.get_proxy_coin.return_value = "USDT"
  bot.exchange.get_pair_base_currency.return_value = "ETH"
  bot.exchange.get_rates.return_value = (11.0, 11.0)
  bot.exchange.get_min_pair_stake_amount.return_value = 5.0
  bot.exchange.get_max_pair_stake_amount.return_value = 100000.0
  bot.exchange.fetch_ticker.return_value = {"bid": 11.0, "ask": 11.0}
  strategy.dp._exchange = bot.exchange
  bot.wallets = Wallets(bot.config, bot.exchange)
  bot.execute_trade_exit = MagicMock(return_value=True)
  clock = mocker.patch("freqtrade.freqtradebot.datetime", wraps=datetime)
  custom_exit = mocker.spy(strategy, "custom_exit")
  adjustment = mocker.spy(strategy, "adjust_trade_position")
  case.frame(11.0)
  assert case.demand() is False

  # process() checks exits before adjusting positions, with separate clock reads.
  clock.now.return_value = DUE
  assert bot._check_and_execute_exit(case.trade, 11.0, False, False, None) is False
  assert custom_exit.call_args.kwargs["current_time"] == DUE
  bot.execute_trade_exit.assert_not_called()
  assert case.trade.get_custom_data(KEY)["closing"] is False

  adjusted_at = DUE + timedelta(seconds=1)
  clock.now.return_value = adjusted_at
  bot.check_and_call_adjust_trade_position(case.trade)
  assert adjustment.call_args.kwargs["current_time"] == adjusted_at
  assert adjustment.spy_return is None
  assert strategy._legacy_grind_demand_snapshot is not None
  bot.execute_trade_exit.assert_not_called()

  exit_time = DUE + timedelta(seconds=6)
  rate = 11.0
  if change == "price":
    rate = 11.01
  elif change == "funding":
    case.trade.funding_fees += 0.01
  elif change == "next_candle":
    exit_time = DUE + timedelta(minutes=5)
  clock.now.return_value = exit_time
  exited = bot._check_and_execute_exit(case.trade, rate, False, False, None)
  assert custom_exit.call_args.kwargs["current_time"] == exit_time
  assert strategy._legacy_grind_demand_snapshot is None
  if change == "unchanged":
    assert exited is True
    bot.execute_trade_exit.assert_called_once_with(
      case.trade, rate, ExitCheckTuple(ExitType.CUSTOM_EXIT, EXIT), exit_tag=None
    )
    assert case.trade.get_custom_data(KEY)["intent_time"] == exit_time.isoformat()
  else:
    assert exited is False
    bot.execute_trade_exit.assert_not_called()
    assert case.trade.get_custom_data(KEY) is None
    clock.now.return_value = exit_time + timedelta(seconds=1)
    assert bot._check_and_execute_exit(case.trade, 11.0, False, False, None) is False
    bot.execute_trade_exit.assert_not_called()


@pytest.fixture
def engine(case):
  original_use_db = Trade.use_db
  Trade.use_db = False
  LocalTrade.reset_trades()
  LocalTrade.add_bt_trade(case.trade)
  backtester = Backtesting.__new__(Backtesting)
  backtester.strategy = case.strategy
  backtester.order_id_counter = 10000
  backtester.precision_mode = 2
  backtester.fee = case.trade.fee_open
  backtester.margin_mode = MarginMode.ISOLATED
  backtester.wallets = MagicMock()
  backtester._run_funding_fees = MagicMock()
  backtester.run_protections = MagicMock()
  case.strategy._should_hold_trade = MagicMock(return_value=False)
  try:
    yield backtester
  finally:
    LocalTrade.reset_trades()
    Trade.use_db = original_use_db


def row():
  return (pd.Timestamp(DUE), 11.0, 11.1, 10.9, 11.0, 0, 0, 0, 0, None, None)


def intent(case):
  case.demand()
  case.adjust()
  assert case.exit() == EXIT


def test_order_fill_callback_does_not_release_slot_before_engine_close(case, engine):
  intent(case)
  observations = []
  original = case.strategy.order_filled

  @wraps(original)
  def observe_fill(*args, **kwargs):
    original(*args, **kwargs)
    observations.append((case.trade.is_open, case.trade in LocalTrade.bt_trades_open, case.demand(DUE)))

  case.strategy.order_filled = observe_fill
  created = engine._get_exit_for_signal(case.trade, row(), ExitCheckTuple(ExitType.CUSTOM_EXIT, EXIT), DUE)
  assert created is case.trade
  order = case.trade.orders[-1]
  assert order.ft_is_open and order.safe_filled == 0.0
  assert order.amount == pytest.approx(0.1)
  assert case.demand(DUE) is False

  engine._process_exit_order(order, case.trade, DUE, row(), case.trade.pair)

  assert observations == [(True, True, False)]
  assert order.safe_filled == pytest.approx(0.1)
  assert not case.trade.is_open
  assert case.trade not in LocalTrade.bt_trades_open
  assert case.trade in LocalTrade.bt_trades
  assert case.demand(DUE) is True


def test_real_confirmation_veto_keeps_slot_and_persistent_intent(case, engine):
  intent(case)
  state = case.trade.get_custom_data(KEY)
  case.strategy._should_hold_trade = MagicMock(return_value=True)
  created = engine._get_exit_for_signal(case.trade, row(), ExitCheckTuple(ExitType.CUSTOM_EXIT, EXIT), DUE)
  assert created is None
  assert len(case.trade.orders) == 2
  assert case.trade.is_open and case.trade in LocalTrade.bt_trades_open
  assert case.trade.get_custom_data(KEY) == state
  assert case.demand(DUE) is False


def test_base_fee_remainder_order_uses_net_amount(database):
  case = make_d1(leverage=1.0, base_fee=1.0)
  intent(case)
  backtester = Backtesting.__new__(Backtesting)
  backtester.strategy = case.strategy
  backtester.order_id_counter = 10000
  backtester.precision_mode = 2
  backtester.fee = case.trade.fee_open
  case.strategy._should_hold_trade = MagicMock(return_value=False)
  created = backtester._get_exit_for_signal(case.trade, row(), ExitCheckTuple(ExitType.CUSTOM_EXIT, EXIT), DUE)
  assert created is case.trade
  assert case.trade.orders[-1].amount == pytest.approx(0.1)
  assert case.entry.safe_filled == 100.0
  assert case.entry.safe_amount_after_fee == 99.0
