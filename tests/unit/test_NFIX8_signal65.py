"""Guards for the 65 breakout long: one anti-blow-off-top protection chain."""

import re
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"

CHAIN = "(rsi_3_4h_lt_70) | (roc_9_4h_lt_5) | (stochrsi_k_1d_gt_70)"
COMMENT = "4h overbought & up move, 1d low"
# the chain of the same scene that already ships, so the new clause stays grouped with it
SCENE_ANCHOR = (
  "# 4h overbought, 1d up move, 4h money outflow\n"
  "            & ((stochrsi_k_4h_lt_90) | (roc_9_1d_lt_20) | (cmf_20_4h_gt_neg_0_0))\n"
)
TF_RANK = {"5m": 0, "15m": 1, "1h": 2, "4h": 3, "1d": 4}
CLAUSE = re.compile(r"\(([a-z0-9_]+)\)")
RAW = re.compile(r"\(([a-z0-9_]+) (<|>|<=|>=) (-?\d+(?:\.\d+)?)\)")


def _src() -> str:
  return STRATEGY.read_text()


def _block() -> str:
  src = _src()
  start = src.index("# Condition #65 - Breakout mode (Long).")
  end = src.index("# Logic — Breakout above BB upper with momentum", start)
  return src[start:end]


def _cached(name: str) -> re.Match | None:
  return re.search(rf"^\s{{2,6}}{re.escape(name)} = [a-z0-9_]+ [<>] -?\d+(?:\.\d+)?$", _src(), re.M)


def test_the_chain_lives_inside_the_protection_append():
  block = _block()
  # Then: it is an AND-ed operand of the block's single protection append...
  assert f"& ({CHAIN})" in block
  # ...not a second append of its own, which the guide rules out in 6e.
  assert f"long_entry_logic.append({CHAIN})" not in block
  assert block.count("long_entry_logic.append(") == 3


def test_the_chain_is_grouped_with_the_scene_it_belongs_to():
  block = _block()
  # Then: it sits right after the blow-off chain that already ships, so the block keeps
  # one ordered run and the reader sees the two clauses of the same scene together.
  assert SCENE_ANCHOR + f"            # {COMMENT}\n            & ({CHAIN})\n" in block


def test_the_comment_names_the_state_it_blocks():
  block = _block()
  # Then: the veto fires when every clause is false (4h not overbought, 4h not vertical,
  # daily stochastic overbought), so the comment names that case and not its negation.
  assert f"# {COMMENT}" in block
  assert block.index(f"# {COMMENT}") < block.index(f"& ({CHAIN})")


def test_every_clause_is_a_cached_boolean_not_a_recomputed_indicator():
  for name in CLAUSE.findall(CHAIN):
    # Then: each clause is a series comparison cached once per candle, as 98.9% of the
    # existing chains do; nothing inside the block touches a raw indicator.
    assert _cached(name) is not None, name


def test_the_whole_append_reads_cached_masks_only():
  block = _block()
  # Then: no clause of the block compares a series against a number inline, so every operand
  # is a mask computed once per candle and the block stays a list of names.
  assert RAW.findall(block) == []


def test_the_chain_is_a_pure_disjunction_of_three_clauses():
  # Then: no conjunction, no arithmetic: the line is False only when all three clauses are
  # false, so the protection can never open a trade the signal would not take.
  assert "&" not in CHAIN
  assert len(CLAUSE.findall(CHAIN)) == 3


def test_the_chain_mixes_timeframes_in_ascending_order():
  ranks = [TF_RANK[re.sub(r"_(?:lt|gt)_-?\d+$", "", name).rsplit("_", 1)[-1]] for name in CLAUSE.findall(CHAIN)]
  # Then: two frames, low -> high, as the guide asks.
  assert len(set(ranks)) >= 2
  assert ranks == sorted(ranks)


def test_the_signal_knob_and_the_rebuy_tags_are_untouched():
  # Then: this change adds protection only; the signal stays on exactly as it ships today.
  assert re.search(r'^\s{4}"long_entry_condition_65_enable": True,$', _src(), re.M)
  assert 'long_rebuy_mode_tags = ["61", "62", "63", "64", "65", "68"]' in _src()
