"""Guards for the 507 daily downtrend continuation short: protection chains, trigger and the 1d columns it reads."""

import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"

TF_RANK = {"5m": 0, "15m": 1, "1h": 2, "4h": 3, "1d": 4}
CLAUSE = re.compile(r"\(([a-z][a-z0-9_]*)\)")


def _src() -> str:
  return STRATEGY.read_text()


def _block() -> str:
  src = _src()
  start = src.index("# Condition #507 - Daily downtrend continuation (Short, experimental).")
  end = src.index("# Condition #", start + 1)
  return src[start:end]


def _protections() -> str:
  block = _block()
  return block[block.index("# Protections") : block.index("# Logic")]


def _logic() -> str:
  block = _block()
  return block[block.index("# Logic") :]


def _chains() -> list[str]:
  """Every protection chain of the block, in file order, as '(a) | (b) | (c)'."""
  chains = []
  for line in _protections().splitlines():
    m = re.match(r"^\s*&?\s*\((\(.*\|.*\))\)$", line.strip()) or re.match(r"^\s*(\(.*\|.*\))$", line.strip())
    if m:
      chains.append(m.group(1))
  return chains


def _timeframe(name: str) -> str:
  m = re.search(r"_(15m|1h|4h|1d)_(?:gt|lt)_", name)
  return m.group(1) if m else "5m"


def test_the_block_has_its_protection_chains():
  # Then: the mined chains are all there (154 at the time of writing, only ever more).
  assert len(_chains()) >= 150


def test_the_chains_live_inside_one_protection_append():
  protections = _protections()
  # Then: the chains are AND-ed operands of one append, not an append each.
  for chain in _chains():
    assert f"short_entry_logic.append({chain})" not in protections
  assert protections.count("short_entry_logic.append(") == 4


def test_each_chain_carries_a_comment():
  lines = [line.strip() for line in _protections().splitlines()]
  for i, line in enumerate(lines):
    if re.match(r"^&?\s*\(\(.*\|", line):
      # Then: the line above names the state the chain blocks.
      assert lines[i - 1].startswith("# "), line


def test_the_chains_are_pure_disjunctions_so_they_can_only_block():
  for chain in _chains():
    # Then: two or more clauses joined by OR, no AND inside: the line is False only when every clause is.
    assert "&" not in chain, chain
    assert len(chain.split(" | ")) >= 2, chain


def test_every_clause_is_a_cached_boolean():
  src = _src()
  for name in {c for chain in _chains() for c in CLAUSE.findall(chain)}:
    # Then: '<name> = <series> <op> <number>' is defined once, outside the block.
    defs = re.findall(rf"^\s{{2,6}}{re.escape(name)} = [a-z0-9_]+ [<>] -?\d+(?:\.\d+)?$", src, re.M)
    assert len(defs) == 1, name


def test_each_chain_keeps_its_timeframes_in_ascending_order():
  for chain in _chains():
    ranks = [TF_RANK[_timeframe(c)] for c in CLAUSE.findall(chain)]
    # Then: low -> high, as the rest of the file writes them.
    assert ranks == sorted(ranks), chain


@pytest.mark.parametrize(
  "clause",
  [
    # daily downtrend: slow KAMA under the fast one, red 4h heikin-ashi candle under the slow KAMA
    "(kama_153_1d < kama_40_1d)",
    "& (ha_close_4h < ha_open_4h)",
    "& (ha_close_4h < kama_153_1d)",
    # not more than 3 ATR under the slow KAMA
    "& (close_4h > (kama_153_1d - (3.0 * atr_14_4h)))",
    # trending but not exhausted, on rising volume
    "& (adx_13_4h > 10.0)",
    "& (adx_13_4h < 55.0)",
    "& (vol_rel_27_4h > 1.0)",
    # BTC not strong
    "& (btc_rsi_14_1h < 50.0)",
    # not already 15% under the previous 20 candle high, not after a 24h crash
    "& (close >= (dc_high_20 * 0.85))",
    "& (roc_288 > -15.0)",
    # 1h agrees, two of four
    "((macdh_12_26_9_1h < 0.0) & (minus_di_14_1h > plus_di_14_1h))",
    "| ((macdh_12_26_9_1h < 0.0) & (close_4h < dc_low_10_1h))",
    "| ((macdh_12_26_9_1h < 0.0) & (rsi_14_1h < 50.0))",
    "| ((minus_di_14_1h > plus_di_14_1h) & (close_4h < dc_low_10_1h))",
    "| ((minus_di_14_1h > plus_di_14_1h) & (rsi_14_1h < 50.0))",
    "| ((close_4h < dc_low_10_1h) & (rsi_14_1h < 50.0))",
  ],
)
def test_the_logic_holds_every_trigger_condition(clause):
  # Then: the entry is the one 507 was validated with, condition for condition.
  assert clause in _logic()


def test_the_protections_keep_the_empty_candle_global_and_hot_coin_guards():
  protections = _protections()
  # Then: enough candles, the global short guard, and a coin in its own top-third 28 day run is skipped.
  assert "short_entry_logic.append(num_empty_288 <= allowed_empty_candles_288)" in protections
  assert "short_entry_logic.append(protections_short_global == True)" in protections
  assert "short_entry_logic.append(mom_28_hot_1d < 0.5)" in protections


def test_the_signal_is_disabled_by_default():
  assert NostalgiaForInfinityX8.short_entry_signal_params["short_entry_condition_507_enable"] is False
  assert "507" in NostalgiaForInfinityX8.short_normal_mode_tags


@pytest.fixture
def daily_frame():
  rng = np.random.default_rng(507)
  close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.03, 800)))
  # a strong 28 day run at the end of the series
  close[-28:] = close[-29] * np.exp(np.linspace(0.02, 0.9, 28))
  return pd.DataFrame(
    {
      "date": pd.date_range("2022-01-01", periods=len(close), freq="D", tz="UTC"),
      "open": close,
      "high": close * 1.02,
      "low": close * 0.98,
      "close": close,
      "volume": 1000.0,
    }
  )


def _daily(frame: pd.DataFrame) -> pd.DataFrame:
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.dp = SimpleNamespace(get_pair_dataframe=lambda **kwargs: frame.copy())
  return strategy.informative_1d_indicators({"pair": "ETH/USDT:USDT"}, "1d")


def test_the_daily_columns_do_not_read_future_candles(daily_frame):
  # Given: the same series, once whole and once cut 100 days short.
  full, cut = _daily(daily_frame), _daily(daily_frame.iloc[:-100].reset_index(drop=True))
  # Then: every row the cut series has is identical in the whole one.
  for col in ("KAMA_40", "KAMA_153", "MOM_28_HOT"):
    np.testing.assert_allclose(cut[col].to_numpy(), full[col].to_numpy()[: len(cut)], equal_nan=True, err_msg=col)


def test_a_coin_in_its_top_third_run_is_hot_and_stays_hot(daily_frame):
  hot = _daily(daily_frame)["MOM_28_HOT"].to_numpy()
  # Then: the run at the end is in the coin's own top third, and a hot flag holds for five days.
  assert hot[-1] == 1.0
  starts = np.where((hot[1:] == 1.0) & (hot[:-1] == 0.0))[0] + 1
  for s in starts[starts + 5 <= len(hot)]:
    assert (hot[s : s + 5] == 1.0).all()
