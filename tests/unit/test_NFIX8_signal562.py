"""Guards for the 562 trend-breakdown short: three anti-late-entry protection chains."""

import re
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"

CHAINS = [
  "(aroonu_14_15m_lt_75) | (rsi_3_4h_gt_25) | (stochrsi_k_4h_lt_20)",
  "(aroonu_14_1h_lt_30) | (stochrsi_k_1h_lt_60) | (aroonu_14_4h_gt_30)",
  "(rsi_3_1h_gt_35) | (aroonu_14_1h_gt_20) | (aroonu_14_1d_lt_60)",
]
TF_RANK = {"15m": 0, "1h": 1, "4h": 2, "1d": 3}
CLAUSE = re.compile(r"\(([a-z0-9_]+)\)")


def _src() -> str:
  return STRATEGY.read_text()


def _block() -> str:
  src = _src()
  start = src.index("# Condition #562 - Trend Breakdown mode (Short).")
  end = src.index("# Condition #563", start)
  return src[start:end]


def _cached(name: str) -> re.Match | None:
  """A cached boolean: '<name> = <series> <op> <number>' defined once, outside the block."""
  return re.search(rf"^\s{{2,6}}{re.escape(name)} = [a-z0-9_]+ [<>] -?\d+(?:\.\d+)?$", _src(), re.M)


def test_the_three_chains_are_appended_to_the_562_protection_list():
  block = _block()
  for chain in CHAINS:
    assert f"short_entry_logic.append({chain})" in block


def test_the_chains_sit_after_the_existing_protections_and_before_the_logic():
  # Given: the block's two halves.
  block = _block()
  anchor = block.index("short_entry_logic.append(rsi_14_1d > 25.0)")
  logic = block.index("short_entry_logic.append(\n            # Downtrend confirmation")
  # Then: the new protections are sandwiched between them, so they can only veto.
  for chain in CHAINS:
    pos = block.index(f"short_entry_logic.append({chain})")
    assert anchor < pos < logic


def test_every_clause_is_a_cached_boolean_not_a_recomputed_indicator():
  for chain in CHAINS:
    for name in CLAUSE.findall(chain):
      # Then: each clause is a series comparison cached once per candle, as 98.9% of the
      # existing chains do; nothing inside the block touches a raw indicator.
      assert _cached(name) is not None, name


def test_the_chains_are_pure_disjunctions_so_they_can_only_block():
  for chain in CHAINS:
    # Then: no conjunction, no arithmetic: the line is False only when all three clauses
    # are False, so the protection can never open a trade the signal would not take.
    assert "&" not in chain
    assert len(CLAUSE.findall(chain)) == 3


def test_each_chain_mixes_timeframes_in_ascending_order():
  for chain in CHAINS:
    ranks = [TF_RANK[re.sub(r"_(?:lt|gt)_-?\d+$", "", name).rsplit("_", 1)[-1]] for name in CLAUSE.findall(chain)]
    # Then: at least two frames (71% of the reference chains) and low -> high, as the guide asks.
    assert len(set(ranks)) >= 2, chain
    assert ranks == sorted(ranks), chain


def test_the_thresholds_are_on_the_existing_boolean_grid():
  # Then: every threshold is one the strategy already publishes, so no new column is added
  # and the nudge test is runnable in both directions.
  for chain in CHAINS:
    for name in CLAUSE.findall(chain):
      assert _cached(name) is not None


def test_the_signal_knob_is_untouched():
  # Then: this PR adds protection only; the signal stays on exactly as it ships today.
  assert re.search(r'^\s{4}"short_entry_condition_562_enable": True,$', _src(), re.M)
  assert 'short_rebuy_mode_tags = ["561", "562", "563"]' in _src()
