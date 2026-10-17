"""Offline integration: real FT order/accounting code, simulated exchange only."""

import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from freqtrade.data.dataprovider import DataProvider
from freqtrade.enums import ExitCheckTuple, ExitType, MarginMode, RunMode, TradingMode
from freqtrade.exceptions import ExchangeError
from freqtrade.exchange import Exchange
from freqtrade.freqtradebot import FreqtradeBot
from freqtrade.persistence import Order, Trade
from freqtrade.persistence.models import init_db
from freqtrade.resolvers import StrategyResolver
from freqtrade.wallets import Wallets

from extensions.pair_switch.models import LINK_KEY, Phase, Request, SwitchError
from extensions.pair_switch.strategy import PairSwitchStrategy


NOW = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)


class Clock(datetime):
  @classmethod
  def now(cls, tz=None):
    return NOW if tz is not None else NOW.replace(tzinfo=None)


class EngineTests(unittest.TestCase):
  def setUp(self):
    self.tmp = tempfile.TemporaryDirectory()
    self.addCleanup(self.tmp.cleanup)
    self.root = Path(self.tmp.name)
    init_db("sqlite://")
    self.addCleanup(Trade.session.remove)
    self.clock = patch("freqtrade.freqtradebot.datetime", Clock)
    self.clock.start()
    self.addCleanup(self.clock.stop)
    self.config = {
      "exchange": {"name": "binance"},
      "runmode": RunMode.DRY_RUN,
      "dry_run": True,
      "db_url": "sqlite://",
      "stake_currency": "USDT",
      "stake_amount": 500,
      "dry_run_wallet": 10000,
      "tradable_balance_ratio": 0.99,
      "trading_mode": TradingMode.SPOT,
      "margin_mode": MarginMode.NONE,
      "timeframe": "5m",
      "max_open_trades": 3,
      "user_data_dir": self.root,
      "pair_switch": {"database": str(self.root / "switch.sqlite")},
    }
    self.strategy = PairSwitchStrategy(self.config)
    self.strategy.hold_support_enabled = False
    self.strategy.system_name_use = self.strategy.system_v4_name
    self.strategy.dp = MagicMock(spec=DataProvider)
    self.strategy.dp.runmode = RunMode.DRY_RUN
    self.strategy.dp.current_whitelist.return_value = ["ADA/USDT", "ALGO/USDT"]
    self.strategy.dp.market.return_value = {"active": True}
    self.strategy.dp.get_analyzed_dataframe.side_effect = self.frame
    self.strategy.bot_start()
    self.addCleanup(self.strategy.ft_bot_cleanup)
    self.store = self.strategy._switch.store
    self.exchange = MagicMock(spec=Exchange)
    self.exchange.id = "binance"
    self.exchange.margin_mode = MarginMode.NONE
    self.exchange.precisionMode = 4
    self.exchange.precision_mode_price = 4
    self.exchange.get_proxy_coin.return_value = "USDT"
    self.exchange.get_pair_base_currency.side_effect = lambda pair: pair.split("/")[0]
    self.exchange.get_precision_amount.return_value = 0.00000001
    self.exchange.get_precision_price.return_value = 0.00000001
    self.exchange.get_contract_size.return_value = 1.0
    self.exchange.get_min_pair_stake_amount.return_value = 5.0
    self.exchange.get_max_pair_stake_amount.return_value = 100000.0
    self.exchange.get_funding_fees.return_value = 0.0
    self.exchange.get_fee.return_value = 0.001
    self.exchange.get_liquidation_price.return_value = None
    self.exchange.get_option.return_value = False
    self.exchange.check_order_canceled_empty.return_value = False
    self.exchange.order_has_fee.return_value = True
    self.exchange.extract_cost_curr_rate.side_effect = lambda fee, *args: (
      fee["cost"],
      fee["currency"],
      fee["rate"],
    )
    self.orders = []
    self.exchange.create_order.side_effect = self.place_order
    self.bot = FreqtradeBot.__new__(FreqtradeBot)
    self.bot.config = self.config
    self.bot.strategy = self.strategy
    self.bot.exchange = self.exchange
    self.bot.trading_mode = TradingMode.SPOT
    self.bot.margin_mode = MarginMode.NONE
    self.bot._exit_reason_cache = {}
    self.bot._notify_enter = MagicMock()
    self.bot._notify_exit = MagicMock()
    # Notifications/protection plugins are not part of the order execution seam.
    self.bot.handle_protections = MagicMock()
    self.bot.wallets = Wallets(self.config, self.exchange)
    self.source = Trade(
      exchange="binance",
      pair="ADA/USDT",
      open_rate=1.0,
      amount=1000,
      stake_amount=1000,
      fee_open=0.001,
      fee_close=0.001,
      open_date=NOW - timedelta(days=1),
      trading_mode=TradingMode.SPOT,
      leverage=1.0,
      amount_precision=0.00000001,
      price_precision=0.00000001,
      precision_mode=4,
      precision_mode_price=4,
      contract_size=1.0,
      enter_tag="manual",
    )
    Trade.session.add(self.source)
    Trade.commit()
    seed = self.order("seed", "ADA/USDT", "buy", 1000.0, 1.0, closed=True)
    self.source.orders.append(Order.parse_from_ccxt_object(seed, "ADA/USDT", "buy", 1000, 1))
    self.source.update_trade(self.source.orders[-1])
    self.request = Request(
      token="a" * 32,
      source_id=self.source.id,
      target="ALGO/USDT",
      stake=500,
      expires_at=NOW + timedelta(hours=1),
    )

  def frame(self, pair, timeframe):
    rate = 0.4 if pair == "ALGO/USDT" else 0.9
    return pd.DataFrame(
      {
        "date": [pd.Timestamp(NOW - timedelta(minutes=5))],
        "close": [rate],
        "volume": [1000.0],
      }
    ), NOW

  def order(self, oid, pair, side, amount, rate, closed=False):
    return {
      "id": oid,
      "symbol": pair,
      "type": "limit",
      "side": side,
      "price": rate,
      "average": rate if closed else None,
      "amount": amount,
      "filled": amount if closed else 0.0,
      "remaining": 0.0 if closed else amount,
      "cost": rate * amount if closed else 0.0,
      "status": "closed" if closed else "open",
      "timestamp": int(NOW.timestamp() * 1000),
      "fee": {"cost": rate * amount * 0.001 if closed else 0.0, "currency": "USDT", "rate": 0.001},
    }

  def place_order(self, *, pair, side, amount, rate, **kwargs):
    result = self.order(str(len(self.orders) + 1), pair, side, amount, rate)
    self.orders.append(result)
    return result

  def close_source(self):
    self.store.submit(self.request)
    self.strategy.bot_loop_start(NOW)
    reason = self.strategy.custom_exit("ADA/USDT", self.source, NOW, 0.9, -0.1)
    self.assertEqual(reason, "ps_exit_" + self.request.token)
    self.assertTrue(
      self.bot.execute_trade_exit(
        self.source,
        0.9,
        ExitCheckTuple(ExitType.CUSTOM_EXIT, reason),
      )
    )
    self.strategy.bot_loop_start(NOW)
    self.assertEqual(self.store.active().phase, Phase.CLOSING)
    fill = self.order("1", "ADA/USDT", "sell", 1000.0, 0.9, closed=True)
    self.bot.update_trade_state(self.source, "1", fill)
    self.strategy.bot_loop_start(NOW)
    self.assertEqual(self.store.active().phase, Phase.READY)
    self.assertAlmostEqual(self.source.close_profit_abs, -101.9)

  def test_real_engine_switch_preserves_source_and_links_target(self):
    # Given: a real source Trade, explicit intent, simulated exchange.
    self.close_source()
    tag = self.store.active().tag
    # When: actual FT sizing, confirmation, order creation, fill and accounting run.
    self.assertTrue(self.bot.execute_entry("ALGO/USDT", 500, 0.4, enter_tag=tag))
    target = Trade.get_open_trades()[0]
    self.assertEqual(self.store.active().phase, Phase.ADMITTED)
    self.assertFalse(self.bot.execute_entry("ALGO/USDT", 500, 0.4, enter_tag=tag))
    self.bot.update_trade_state(
      target,
      "2",
      self.order(
        "2",
        "ALGO/USDT",
        "buy",
        1250,
        0.4,
        closed=True,
      ),
    )
    self.strategy.bot_loop_start(NOW)
    # Then: one exit and one entry, independent records, actual final loss carried.
    self.assertEqual([(o["symbol"], o["side"]) for o in self.orders], [("ADA/USDT", "sell"), ("ALGO/USDT", "buy")])
    self.assertFalse(self.source.is_open)
    self.assertEqual(self.source.pair, "ADA/USDT")
    self.assertNotEqual(target.id, self.source.id)
    self.assertAlmostEqual(target.stake_amount, 500)
    self.assertEqual(target.get_custom_data(LINK_KEY)["source_id"], self.source.id)
    self.assertAlmostEqual(target.get_custom_data(LINK_KEY)["carry_profit"], -101.9)
    self.assertEqual(self.store.all()[0].phase, Phase.COMPLETE)

  def test_lost_exchange_response_does_not_reauthorize_entry(self):
    # Given: the exchange accepts an order then the response is lost.
    self.close_source()
    tag = self.store.active().tag

    def lost(**kwargs):
      self.place_order(**kwargs)
      raise ExchangeError("Synthetic response loss after acceptance.")

    self.exchange.create_order.side_effect = lost
    # When: the real FT entry method fails after authorization was consumed.
    with self.assertRaises(ExchangeError):
      self.bot.execute_entry("ALGO/USDT", 500, 0.4, enter_tag=tag)
    self.strategy.bot_loop_start(NOW)
    # Then: no local target is treated as proof that a retry is safe.
    self.assertEqual(self.store.active().phase, Phase.REVIEW)
    self.assertFalse(self.bot.execute_entry("ALGO/USDT", 500, 0.4, enter_tag=tag))
    self.assertEqual(len(self.orders), 2)
    self.assertEqual(Trade.get_open_trade_count(), 0)

  def test_cli_submit_and_status_are_idempotent(self):
    # Given: a started strategy and a request file for the CLI.
    request_path = self.root / "request.json"
    request_path.write_text(self.request.model_dump_json())
    command = [sys.executable, "-m", "extensions.pair_switch", "--database", str(self.store.path)]
    # When: the actual CLI retries the same request and reads status.
    for _ in range(2):
      result = subprocess.run(command + ["submit", str(request_path)], capture_output=True, text=True, timeout=20)
      self.assertEqual(result.returncode, 0, result.stderr)
    status = subprocess.run(command + ["status"], capture_output=True, text=True, timeout=20)
    # Then: exactly one persisted intent, and no exchange orders.
    self.assertEqual(status.returncode, 0, status.stderr)
    self.assertEqual(len(json.loads(status.stdout)), 1)
    self.assertEqual(self.orders, [])

  def test_second_bot_cannot_own_same_journal(self):
    # Given: the running fixture owns the journal for its entire lifetime.
    other = PairSwitchStrategy(self.config.copy())
    # When / Then: a second startup cannot acquire the execution lease.
    with self.assertRaises(BlockingIOError):
      other.bot_start()
    self.assertTrue(other._switch_fault)

  def test_live_mode_requires_explicit_opt_in(self):
    # Given: live configuration without a live authorization flag.
    config = {**self.config, "dry_run": False, "runmode": RunMode.LIVE}
    other = PairSwitchStrategy(config)
    # When / Then: startup rejects before any journal ownership or orders.
    with self.assertRaises(SwitchError):
      other.bot_start()
    self.assertTrue(other._switch_fault)

  def test_stale_target_data_rejects_before_source_exit(self):
    # Given: the target's analyzed data is older than the bounded freshness window.
    frame, _ = self.frame("ALGO/USDT", "5m")
    frame.loc[0, "date"] = pd.Timestamp(NOW - timedelta(hours=1))
    self.strategy.dp.get_analyzed_dataframe.return_value = (frame, NOW)
    self.strategy.dp.get_analyzed_dataframe.side_effect = None
    self.store.submit(self.request)
    # When: the bot evaluates the request.
    self.strategy.bot_loop_start(NOW)
    # Then: no liquidation is requested.
    self.assertEqual(self.store.all()[0].phase, Phase.REJECTED)
    self.assertTrue(self.source.is_open)
    self.assertEqual(self.orders, [])

  def test_wallet_adjustment_above_budget_is_rejected_at_final_admission(self):
    # Given: exchange/wallet validation raises stake after the strategy sized it.
    self.close_source()
    tag = self.store.active().tag
    with patch.object(self.bot.wallets, "validate_stake_amount", return_value=600):
      # When: real execute_entry reaches final admission with the enlarged amount.
      entered = self.bot.execute_entry("ALGO/USDT", 500, 0.4, enter_tag=tag)
    # Then: it cannot create an oversized replacement order.
    self.assertFalse(entered)
    self.assertEqual(len(self.orders), 1)
    self.assertEqual(self.store.active().phase, Phase.READY)

  def test_official_strategy_resolver_loads_extension(self):
    # Given: a real FT strategy path, not a manually imported loader class.
    config = {
      **self.config,
      "strategy": "NostalgiaForInfinityX8PairSwitch",
      "strategy_path": str(Path(__file__).resolve().parents[2] / "extensions" / "strategies"),
    }
    # When: Freqtrade's own loader imports and validates the strategy.
    loaded = StrategyResolver.load_strategy(config)
    # Then: the deployed class is the extension over the pinned NFI root.
    self.assertIsInstance(loaded, PairSwitchStrategy)
    self.assertEqual(loaded.get_strategy_name(), "NostalgiaForInfinityX8PairSwitch")
    self.assertEqual(loaded.version(), "v18.0.130")

  def test_source_exit_authorization_is_not_reused_after_response_loss(self):
    # Given: a source liquidation is accepted by the exchange but not persisted.
    self.store.submit(self.request)
    self.strategy.bot_loop_start(NOW)
    reason = self.strategy.custom_exit("ADA/USDT", self.source, NOW, 0.9, -0.1)

    def lost(**kwargs):
      self.place_order(**kwargs)
      raise ExchangeError("Synthetic source exit response loss.")

    self.exchange.create_order.side_effect = lost
    # When: FT receives the failure after the exit admission has been consumed.
    with self.assertRaises(ExchangeError):
      self.bot.execute_trade_exit(self.source, 0.9, ExitCheckTuple(ExitType.CUSTOM_EXIT, reason))
    self.strategy.bot_loop_start(NOW)
    # Then: even a cached exit signal cannot resubmit this switch's liquidation.
    self.assertFalse(
      self.bot.execute_trade_exit(
        self.source,
        0.9,
        ExitCheckTuple(ExitType.CUSTOM_EXIT, reason),
      )
    )
    self.assertEqual(len(self.orders), 1)
    self.assertEqual(self.store.active().phase, Phase.CLOSING)
    self.assertTrue(self.store.active().exit_admitted)

  def futures_switch(self, short):
    source_pair, target_pair = "ADA/USDT:USDT", "ALGO/USDT:USDT"
    self.config["trading_mode"] = TradingMode.FUTURES
    self.config["margin_mode"] = MarginMode.ISOLATED
    self.bot.trading_mode = TradingMode.FUTURES
    self.bot.margin_mode = MarginMode.ISOLATED
    self.exchange.margin_mode = MarginMode.ISOLATED
    self.exchange.get_max_leverage.return_value = 10
    self.exchange.get_funding_fees.return_value = 2.0
    self.strategy.is_futures_mode = True
    self.strategy.can_short = True
    self.strategy.dp.current_whitelist.return_value = [source_pair, target_pair]
    self.strategy.dp.get_analyzed_dataframe.side_effect = lambda pair, timeframe: self.frame(
      pair.split(":")[0], timeframe
    )
    self.source.pair = source_pair
    self.source.trading_mode = TradingMode.FUTURES
    self.source.is_short = short
    self.source.leverage = 3.0
    initial = self.source.orders[0]
    initial.ft_pair = initial.symbol = source_pair
    initial.ft_order_side = initial.side = self.source.entry_side
    self.source.recalc_trade_from_orders()
    Trade.commit()
    self.request = self.request.model_copy(update={"target": target_pair, "stake": 100})
    self.store.submit(self.request)
    self.strategy.bot_loop_start(NOW)
    exit_rate = 1.1 if short else 0.9
    reason = self.strategy.custom_exit(source_pair, self.source, NOW, exit_rate, -0.3)
    self.assertTrue(
      self.bot.execute_trade_exit(
        self.source,
        exit_rate,
        ExitCheckTuple(ExitType.CUSTOM_EXIT, reason),
      )
    )
    self.assertTrue(self.exchange.create_order.call_args.kwargs["reduceOnly"])
    self.bot.update_trade_state(
      self.source,
      "1",
      self.order(
        "1",
        source_pair,
        self.source.exit_side,
        1000,
        exit_rate,
        closed=True,
      ),
    )
    self.strategy.bot_loop_start(NOW)
    ready = self.store.active()
    self.assertEqual(ready.phase, Phase.READY)
    self.assertTrue(self.bot.execute_entry(target_pair, 100, 0.4, enter_tag=ready.tag, is_short=short))
    target = Trade.get_open_trades()[0]
    self.bot.update_trade_state(
      target,
      "2",
      self.order(
        "2",
        target_pair,
        target.entry_side,
        750,
        0.4,
        closed=True,
      ),
    )
    self.strategy.bot_loop_start(NOW)
    self.assertEqual(target.is_short, short)
    self.assertEqual(target.leverage, 3)
    self.assertAlmostEqual(target.stake_amount, 100)
    self.assertAlmostEqual(target.amount, 750)
    self.assertAlmostEqual(self.source.close_profit_abs, -100.1 if short else -99.9)
    self.assertAlmostEqual(target.get_custom_data(LINK_KEY)["carry_profit"], self.source.close_profit_abs)
    self.assertEqual(self.store.all()[0].phase, Phase.COMPLETE)

  def test_futures_long_preserves_leverage_and_net_funding(self):
    self.futures_switch(short=False)

  def test_futures_short_preserves_direction_and_net_funding(self):
    self.futures_switch(short=True)


if __name__ == "__main__":
  unittest.main()
