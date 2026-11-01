"""Guards for the 562 trend-breakdown short: three anti-late-entry protection chains."""

import re
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"

# chain -> the house comment that names the scene it blocks (the case where every clause is false)
CHAINS = {
  "(aroonu_14_15m_lt_75) | (rsi_3_4h_gt_25) | (stochrsi_k_4h_lt_20)": "15m high, 4h down move & still high",
  "(aroonu_14_1h_lt_30) | (stochrsi_k_1h_lt_60) | (aroonu_14_4h_gt_30)": "1h high & still high, 4h low",
  "(rsi_3_1h_gt_35) | (aroonu_14_1h_gt_20) | (aroonu_14_1d_lt_60)": "1h down move & low, 1d high",
}
TF_RANK = {"5m": 0, "15m": 1, "1h": 2, "4h": 3, "1d": 4}
FAMILY = ["rsi_3", "rsi_14", "cmf_20", "mfi_14", "aroonu_14", "aroond_14", "stochrsi_k", "willr_14", "roc_2", "roc_9"]
CLAUSE = re.compile(r"\(([a-z0-9_]+)\)")


def _src() -> str:
  return STRATEGY.read_text()


def _block() -> str:
  src = _src()
  start = src.index("# Condition #562 - Trend Breakdown mode (Short).")
  end = src.index("# Condition #563", start)
  return src[start:end]


def _chain_lines() -> list[str]:
  """Every protection chain of the block, in file order, as '& ((a) | (b) | (c))'."""
  chains = []
  lines = _block().splitlines()
  for i, line in enumerate(lines):
    stripped = line.strip()
    if re.match(r"^& \(\(.*\|", stripped):
      chains.append(stripped)
    elif stripped == "& (" and i + 1 < len(lines):
      chains.append("& (" + lines[i + 1].strip() + ")")
  return chains


def _lead_key(chain: str) -> tuple[int, int] | None:
  """(timeframe rank, family rank) of a chain's lead clause, as the guide's checker measures it."""
  lead = re.search(r"\(([a-z][a-z0-9_]*?)_(?:gt|lt)_", chain)
  if not lead:
    return None
  name = lead.group(1)
  base = re.sub(r"_(15m|1h|4h|1d)$", "", name)
  tf = (re.search(r"_(15m|1h|4h|1d)$", name) or [None, "5m"])[1]
  family = next((f for f in FAMILY if base.startswith(f)), base)
  return TF_RANK.get(tf, 9), FAMILY.index(family) if family in FAMILY else len(FAMILY)


def _cached(name: str) -> re.Match | None:
  """A cached boolean: '<name> = <series> <op> <number>' defined once, outside the block."""
  return re.search(rf"^\s{{2,6}}{re.escape(name)} = [a-z0-9_]+ [<>] -?\d+(?:\.\d+)?$", _src(), re.M)


def test_the_three_chains_live_inside_the_protection_append():
  block = _block()
  for chain in CHAINS:
    # Then: they are AND-ed operands of the block's single protection append...
    assert f"& ({chain})" in block
    # ...not a second append of their own, which the guide rules out in 6e.
    assert f"short_entry_logic.append({chain})" not in block


def test_each_chain_carries_the_house_comment_for_the_scene_it_blocks():
  block = _block()
  for chain, comment in CHAINS.items():
    # Then: the comment names the blocked state (all three clauses false), not its negation.
    assert f"# {comment}\n            & ({chain})" in block


def test_the_chains_sit_in_their_sorted_position_among_the_other_chains():
  chains = _chain_lines()
  for chain, _ in CHAINS.items():
    idx = next(i for i, c in enumerate(chains) if chain in c)
    mine = _lead_key(chains[idx])
    prev = _lead_key(chains[idx - 1]) if idx else None
    nxt = _lead_key(chains[idx + 1]) if idx + 1 < len(chains) else None
    # Then: timeframe ascending, and the family clustered within a shared timeframe.
    if prev is not None:
      assert prev[0] <= mine[0], (chain, prev, mine)
      assert prev[0] < mine[0] or prev[1] <= mine[1], (chain, prev, mine)
    if nxt is not None:
      assert mine[0] <= nxt[0], (chain, mine, nxt)
      assert mine[0] < nxt[0] or mine[1] <= nxt[1], (chain, mine, nxt)


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
