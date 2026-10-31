from datetime import datetime, timezone
import logging

import pytest
from freqtrade.persistence import Trade, init_db
from freqtrade.strategy.strategy_wrapper import strategy_safe_wrapper

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8


NOW = datetime(2026, 10, 31, 12, tzinfo=timezone.utc)


@pytest.fixture
def strategy():
  original_use_db = Trade.use_db
  Trade.use_db = True
  init_db("sqlite://")
  engine = Trade.session.get_bind()
  instance = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  instance.grind_mode_coins = ["INJ"]
  instance.grind_mode_max_slots = 1
  try:
    yield instance
  finally:
    Trade.session.rollback()
    Trade.session.remove()
    engine.dispose()
    Trade.use_db = original_use_db


def add_open_trade(pair, tag):
  trade = Trade(
    pair=pair,
    exchange="binance",
    is_open=True,
    is_short=False,
    amount=1.0,
    stake_amount=100.0,
    open_rate=100.0,
    open_date=NOW,
    fee_open=0.0,
    fee_close=0.0,
    enter_tag=tag,
  )
  Trade.session.add(trade)
  Trade.session.flush()


@pytest.mark.parametrize(
  "tags,limit,allowed",
  [
    ([], 1, True),
    ([None], 1, True),
    ([""], 1, True),
    ([" \t\n"], 1, True),
    (["1"], 1, True),
    (["force_entry"], 1, True),
    (["620"], 1, True),
    (["120"], 1, False),
    ([" 120\t"], 1, False),
    (["120 120"], 1, False),
    (["120 144"], 1, True),
    ([None, "120"], 1, False),
    ([None], 0, False),
    ([""], 0, False),
    (["120"], 2, True),
    (["120", "120"], 2, False),
  ],
)
def test_grind_slots_use_only_nonempty_grind_tags(strategy, caplog, tags, limit, allowed):
  for pair, tag in zip(("ETH/USDT", "BTC/USDT"), tags, strict=False):
    add_open_trade(pair, tag)
  strategy.grind_mode_max_slots = limit
  confirm = strategy_safe_wrapper(strategy.confirm_trade_entry, default_retval=True)

  result = confirm("INJ/USDT", "limit", 1.0, 10.0, "GTC", NOW, "120", "long")

  assert result is allowed
  assert not any(record.levelno >= logging.ERROR for record in caplog.records)


@pytest.mark.parametrize("entry_tag,allowed", [("120", False), ("force_entry", True)])
def test_coin_restriction_and_force_entry_precedence_are_preserved(strategy, entry_tag, allowed):
  add_open_trade("ETH/USDT", None)
  strategy.grind_mode_max_slots = 0
  confirm = strategy_safe_wrapper(strategy.confirm_trade_entry, default_retval=True)

  result = confirm("OTHER/USDT", "limit", 1.0, 10.0, "GTC", NOW, entry_tag, "long")

  assert result is allowed
