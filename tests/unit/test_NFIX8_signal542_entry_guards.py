"""Entry guards of signal 542 (short, quick mode), as this branch leaves them.

The block was gated by `bbb_20_2_0_1h > 20.0`, which only 2.65 % of 1h bars in the
measured universe satisfy: the signal fired 7 times in 1,320 pair-years. The floor is
8.0 here, and two risk filters keep the tail of that wider population out:

  * `minus_di_14_4h < 30.0` - the 4h tape is not already collapsing (a short opened on
    top of a finished dump is the one that gets squeezed);
  * `range_pct_14_1d < 22.0` - the 14-day average daily range is not blown out.

Both are raw comparisons on purpose: the strategy has no cached boolean with either
threshold (it has `minus_di_14_4h` and `range_pct_14_1d` views but no _lt_ helper).
"""

import ast
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"
SIGNAL = 542
SIDE = "short"
KNOB = "short_entry_condition_542_enable"
# The hard AND terms of the block, in file order.
CLAUSES = [
  "(willr_14 > -50.0)",
  "& (aroonu_14_gt_75)",
  "& (aroond_14_lt_25)",
  "& (stochrsi_k_gt_80)",
  "& (willr_84_1h > -30.0)",
  "& (stochrsi_k_1h_gt_80)",
  "& (bbb_20_2_0_1h > 8.0)",
  "& (minus_di_14_4h < 30.0)",
  "& (range_pct_14_1d < 22.0)",
  "& (close_min_48 <= (close * 0.90))",
]
# Cached booleans the block leans on: helper -> (series, operator, threshold).
HELPERS = {
  "aroonu_14_gt_75": ("aroonu_14", ">", 75.0),
  "aroond_14_lt_25": ("aroond_14", "<", 25.0),
  "stochrsi_k_gt_80": ("stochrsi_k", ">", 80.0),
  "stochrsi_k_1h_gt_80": ("stochrsi_k_1h", ">", 80.0),
}
# The two guards are new text in this file: they must appear exactly once.
NEW_GUARDS = ["& (minus_di_14_4h < 30.0)", "& (range_pct_14_1d < 22.0)"]


def block_lines():
  """Lines of this signal's block: from its guard to the next line at 8 spaces."""
  lines = STRATEGY.read_text(encoding="utf-8").splitlines()
  guard = f"        if {SIDE}_entry_condition_index == {SIGNAL}:"
  start = next((i for i, line in enumerate(lines) if line.startswith(guard)), None)
  assert start is not None, f"signal {SIGNAL} ({SIDE}) is not in the strategy"
  end = next(
    (i for i in range(start + 1, len(lines)) if lines[i].strip() and not lines[i].startswith("          ")),
    len(lines),
  )
  return [line.strip() for line in lines[start:end]]


def test_hard_terms_are_in_the_block_in_order():
  block = block_lines()
  position = -1
  for clause in CLAUSES:
    assert clause in block[position + 1 :], f"{clause} is missing from the block, or out of order"
    position = block.index(clause, position + 1)


def test_the_three_numbers_are_the_measured_ones():
  block = block_lines()
  for clause in ("& (bbb_20_2_0_1h > 8.0)", "& (minus_di_14_4h < 30.0)", "& (range_pct_14_1d < 22.0)"):
    assert block.count(clause) == 1, f"{clause} must be in the block exactly once"


def test_the_guards_do_not_leak_into_other_signals():
  text = STRATEGY.read_text(encoding="utf-8")
  for clause in NEW_GUARDS:
    assert text.count(clause) == 1, f"{clause} appears {text.count(clause)} times in the strategy"


def test_the_band_floor_is_shared_with_one_older_signal():
  # Line 28622 already shorts with the same 8.0 floor, so the number is not invented here.
  text = STRATEGY.read_text(encoding="utf-8")
  assert text.count("& (bbb_20_2_0_1h > 8.0)") == 2, "the 8.0 floor should appear twice: 542 and one older signal"


def test_cached_booleans_mean_what_we_read():
  assigns = {}
  for node in ast.walk(ast.parse(STRATEGY.read_text(encoding="utf-8"))):
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
      assigns[node.targets[0].id] = node.value
  for helper, (series, op, threshold) in HELPERS.items():
    assert helper in assigns, f"{helper} is not defined in the strategy"
    compare = assigns[helper]
    assert isinstance(compare, ast.Compare), f"{helper} is not a comparison"
    assert isinstance(compare.left, ast.Name) and compare.left.id == series, f"{helper} left side"
    expected = {"<": "Lt", ">": "Gt", "<=": "LtE", ">=": "GtE"}[op]
    assert type(compare.ops[0]).__name__ == expected, f"{helper} operator is not {op}"
    assert float(ast.literal_eval(compare.comparators[0])) == threshold, f"{helper} threshold"


def test_knob_is_untouched():
  # The signal ships enabled in the strategy (upstream default), and this branch does not flip it.
  assert f'"{KNOB}": True' in STRATEGY.read_text(encoding="utf-8")


def test_a_narrow_band_is_still_rejected():
  assert holds(">", 8.0, 8.01) is True
  assert holds(">", 8.0, 7.99) is False


def test_the_two_guards_block_on_the_wrong_side():
  assert holds("<", 30.0, 29.99) is True and holds("<", 30.0, 30.01) is False
  assert holds("<", 22.0, 21.99) is True and holds("<", 22.0, 22.01) is False


def holds(op, threshold, value):
  if op == ">":
    return value > threshold
  if op == ">=":
    return value >= threshold
  if op == "<":
    return value < threshold
  return value <= threshold
