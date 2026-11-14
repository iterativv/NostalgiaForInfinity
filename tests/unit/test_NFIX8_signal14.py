"""Guards for the signal 14 daily recovery long: protection chains, trigger and the columns it reads."""

import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"

TF_RANK = {"5m": 0, "15m": 1, "1h": 2, "4h": 3, "1d": 4}
FAMILY = ["rsi_3", "rsi_14", "cmf_20", "mfi_14", "aroonu_14", "aroond_14", "stochrsi_k", "willr_14", "roc_2", "roc_9"]
CLAUSE = re.compile(r"\(([a-z][a-z0-9_]*)\)")


def _src() -> str:
  return STRATEGY.read_text()


def _block() -> str:
  src = _src()
  start = src.index("# Condition #14 - Daily recovery, fresh 4h turn (Long, experimental).")
  end = src.index("# Condition #", start + 1)
  return src[start:end]


def _flat(text: str) -> str:
  """A chain the formatter wraps over several lines, back on one line as '& ((a) | (b) | ...)'."""
  return re.sub(
    r"(& )?\(\n((?:\s*\|?\s*\(\w+\)\n)+)\s*\)\n",
    lambda m: (m.group(1) or "") + "(" + " ".join(line.strip() for line in m.group(2).splitlines()) + ")\n",
    text,
  )


def _protections() -> str:
  block = _block()
  return _flat(block[block.index("# Protections") : block.index("# Logic")])


def _logic() -> str:
  block = _block()
  return block[block.index("# Logic") :]


def _chains() -> list[str]:
  """Every protection chain of the block, in file order, as '(a) | (b) | (c)'."""
  chains = []
  for line in _protections().splitlines():
    m = re.match(r"^\s*&?\s*\((\(.*\|.*\))\)$", line.strip()) or re.match(r"^\s*(\(.*\|.*\))$", line.strip())
    if m and not m.group(1).startswith("((macdh_12_26_9_1h"):
      chains.append(m.group(1))
  return chains


def _timeframe(name: str) -> str:
  m = re.search(r"_(15m|1h|4h|1d)_(?:gt|lt)_", name)
  return m.group(1) if m else "5m"


def _lead_key(chain: str) -> tuple[int, int]:
  """(timeframe rank, family rank) of a chain's lead clause."""
  name = re.search(r"\(([a-z][a-z0-9_]*?)_(?:gt|lt)_", chain).group(1)
  tf = (re.search(r"_(15m|1h|4h|1d)$", name) or [None, "5m"])[1]
  base = re.sub(r"_(15m|1h|4h|1d)$", "", name)
  family = next((f for f in FAMILY if base.startswith(f)), base)
  return TF_RANK[tf], FAMILY.index(family) if family in FAMILY else len(FAMILY)


def test_the_block_has_its_protection_chains():
  # Then: all 183 chains are there.
  assert len(_chains()) == 183


def test_the_chains_live_inside_one_protection_append():
  protections = _protections()
  # Then: the chains are AND-ed operands of one append, not an append each.
  for chain in _chains():
    assert f"long_entry_logic.append({chain})" not in protections
  assert protections.count("long_entry_logic.append(") == 4


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


def test_the_chains_are_two_to_five_clauses_on_two_timeframes_or_more():
  for chain in _chains():
    clauses = CLAUSE.findall(chain)
    # Then: two to five cached booleans, at least two frames.
    assert 2 <= len(clauses) <= 5, chain
    assert chain == " | ".join(f"({c})" for c in clauses), chain
    assert len({_timeframe(c) for c in clauses}) >= 2, chain


def test_no_chain_is_implied_by_another():
  src = _src()
  defs = {
    m.group(1): (m.group(2), m.group(3), float(m.group(4)))
    for m in re.finditer(r"^\s{2,6}([a-z0-9_]+) = ([a-z0-9_]+) ([<>]) (-?\d+(?:\.\d+)?)$", src, re.M)
  }

  def implies(b, a):
    (series_b, op_b, value_b), (series_a, op_a, value_a) = defs[b], defs[a]
    return series_b == series_a and op_b == op_a and (value_b <= value_a if op_b == "<" else value_b >= value_a)

  sets = [frozenset(CLAUSE.findall(chain)) for chain in _chains()]
  # Then: every chain is distinct, and no chain is implied by a stricter one (it would never block on its own),
  # counting thresholds: (rsi_3_lt_40) implies (rsi_3_lt_46).
  assert len(set(sets)) == len(sets)
  for i, a in enumerate(sets):
    for j, b in enumerate(sets):
      assert i == j or not all(any(implies(x, y) for y in a) for x in b), (sorted(a), sorted(b))


def test_btc_1h_is_read_only_inside_the_block():
  # Then: with signal 14 off, BTC 1h data is not required.
  src = _src()
  assert src.count('np_view("BTC_RSI_14_1h")') == 1
  assert 'np_view("BTC_RSI_14_1h")' in _block()


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


def test_the_chains_sit_in_sorted_order():
  keys = [_lead_key(chain) for chain in _chains()]
  # Then: timeframe ascending, and the family clustered within a shared timeframe.
  assert keys == sorted(keys)


@pytest.mark.parametrize(
  "clause",
  [
    # daily recovery: fast KAMA still under the slow one, green 4h fast heikin-ashi candle back over the slow KAMA
    "(kama_153_1d > kama_40_1d)",
    "& (ha_fast_close_4h > ha_fast_open_4h)",
    "& (ha_fast_close_4h > kama_153_1d)",
    # not more than 3 ATR over the slow KAMA
    "& (close_4h < (kama_153_1d + (3.0 * atr_14_4h)))",
    # trending but not exhausted, on rising volume
    "& (adx_13_4h > 10.0)",
    "& (adx_13_4h < 55.0)",
    "& (vol_rel_27_4h > 1.0)",
    # fresh turn: the previous 4h fast heikin-ashi candle was red
    "& (np_shift(ha_fast_close_4h, 48) < np_shift(ha_fast_open_4h, 48))",
    # BTC not weak
    "& (btc_rsi_14_1h > 50.0)",
    # not already 15% over the previous 20 candle low, not after a 24h pump
    "& (close <= (dc_low_20 * 1.15))",
    "& (roc_288 < 15.0)",
  ],
)
def test_the_logic_holds_every_trigger_condition(clause):
  # Then: the entry is the one signal 14 was validated with, condition for condition.
  assert clause in _logic()


def test_the_protections_hold_the_1h_two_of_three_guard():
  block = _block()
  protections = block[block.index("# Protections") : block.index("# Logic")]
  guard = (
    "& (\n"
    "              ((macdh_12_26_9_1h > 0.0) & (plus_di_14_1h > minus_di_14_1h))\n"
    "              | ((macdh_12_26_9_1h > 0.0) & (rsi_14_1h > 50.0))\n"
    "              | ((plus_di_14_1h > minus_di_14_1h) & (rsi_14_1h > 50.0))\n"
    "            )\n"
  )
  # Then: 1h agrees, two of three, AND-ed into the protection chain and not in the logic.
  assert guard in protections
  assert "macdh_12_26_9_1h" not in _logic()


def test_the_protections_keep_the_empty_candle_global_cold_coin_and_pump_guards():
  protections = _protections()
  # Then: enough candles, the global long guard, a coin in its own bottom-third 28 day run is skipped, no 1d pump.
  assert "long_entry_logic.append(num_empty_288 <= allowed_empty_candles_288)" in protections
  assert "long_entry_logic.append(protections_long_global == True)" in protections
  assert "long_entry_logic.append(mom_28_cold_1d < 0.5)" in protections
  assert "& (roc_9_1d < 35.0)" in protections


def test_the_signal_is_disabled_by_default():
  assert NostalgiaForInfinityX8.long_entry_signal_params["long_entry_condition_14_enable"] is False
  assert "14" in NostalgiaForInfinityX8.long_normal_mode_tags


@pytest.fixture
def daily_frame():
  rng = np.random.default_rng(16)
  close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.03, 800)))
  # a deep 28 day crash at the end of the series
  close[-28:] = close[-29] * np.exp(np.linspace(-0.02, -0.9, 28))
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
  for col in ("KAMA_40", "KAMA_153", "MOM_28_COLD"):
    np.testing.assert_allclose(cut[col].to_numpy(), full[col].to_numpy()[: len(cut)], equal_nan=True, err_msg=col)


def test_the_cold_flag_does_not_depend_on_how_far_back_history_starts():
  # Given: 1500 days, once whole and once with the first 500 days missing (a live bot holds about 1000).
  rng = np.random.default_rng(28)
  close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.03, 1500)))
  frame = pd.DataFrame(
    {
      "date": pd.date_range("2021-01-01", periods=len(close), freq="D", tz="UTC"),
      "open": close,
      "high": close * 1.02,
      "low": close * 0.98,
      "close": close,
      "volume": 1000.0,
    }
  )
  full, cut = (
    _daily(frame)["MOM_28_COLD"].to_numpy(),
    _daily(frame.iloc[500:].reset_index(drop=True))["MOM_28_COLD"].to_numpy(),
  )
  # Then: once the shorter copy has 704 days (24 returns + 28 + 4 held), the flag is identical.
  np.testing.assert_array_equal(cut[704:], full[500 + 704 :])
  assert full[1204:].sum() > 0


def test_a_coin_in_its_bottom_third_run_is_cold_and_stays_cold(daily_frame):
  cold = _daily(daily_frame)["MOM_28_COLD"].to_numpy()
  # Then: the crash at the end is in the coin's own bottom third, and a cold flag holds for five days.
  assert cold[-1] == 1.0
  starts = np.where((cold[1:] == 1.0) & (cold[:-1] == 0.0))[0] + 1
  for s in starts[starts + 5 <= len(cold)]:
    assert (cold[s : s + 5] == 1.0).all()
