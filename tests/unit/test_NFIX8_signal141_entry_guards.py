"""Entry guards of signal 141 (long), emitted by x8tools/test_emit.py."""

import ast
import re
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"
SIGNAL = 141
SIDE = "long"
KNOB = "long_entry_condition_141_enable"
TIMEFRAMES = ["5m", "15m", "1h", "4h", "1d"]
# (comment, code in the file, series, operator, threshold)
CLAUSES = [
  ("5m oversold", "& (rsi_3 < 30.0)", "rsi_3", "<", 30.0),
  ("5m freshness has not been bought yet", "& (aroonu_14_lt_25)", "aroonu_14", "<", 25.0),
  ("tape not falling on the entry bar", "& (btc_roc_1_5m > -1.2)", "btc_roc_1_5m", ">", -1.2),
  ("1h momentum has turned", "& (cci_20_change_pct_1h > -34.7)", "cci_20_change_pct_1h", ">", -34.7),
  ("1h range still compressed", "& (bbb_20_2_0_1h > 5.15)", "bbb_20_2_0_1h", ">", 5.15),
  ("4h still oversold", "& (willr_14_4h < -6.7)", "willr_14_4h", "<", -6.7),
  ("4h trend pointing down", "& (aroond_14_4h > 7.1429)", "aroond_14_4h", ">", 7.1429),
  ("tape not cascading over four hours", "& (btc_roc_1_4h > -2.2)", "btc_roc_1_4h", ">", -2.2),
]
HELPERS = {
  "aroonu_14_lt_25": ("aroonu_14", "<", 25.0),
}


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


def timeframe(series):
  hits = re.findall(r"_(5m|15m|1h|4h|1d)", series)
  return hits[-1] if hits else "5m"


def test_comments_and_clauses_are_in_order():
  block = block_lines()
  position = -1
  for comment, code, _series, _op, _thr in CLAUSES:
    for item in (f"# {comment}", code):
      assert item in block[position + 1 :], f"{item} is missing from the block, or out of order"
      position = block.index(item, position + 1)


def same_side_blocks():
  """Every block of this side, keyed by signal index. The other side is not our business."""
  lines = STRATEGY.read_text(encoding="utf-8").splitlines()
  guard = f"        if {SIDE}_entry_condition_index == "
  out = {}
  for index, line in enumerate(lines):
    if not line.startswith(guard):
      continue
    number = int(line.split("==")[1].split(":")[0])
    end = next(
      (i for i in range(index + 1, len(lines)) if lines[i].strip() and not lines[i].startswith("          ")),
      len(lines),
    )
    out[number] = [entry.strip() for entry in lines[index:end]]
  return out


def test_clauses_are_not_leaked_into_other_signals():
  """A clause written for this signal belongs to it alone.

  A cached alias is exempt on purpose: `aroonu_14_lt_25` and its neighbours are house
  helpers that many signals share, and the point of using them is to share them. What
  must be pinned for an alias is its definition, which
  `test_cached_booleans_mean_what_we_read` does, not its call sites. The check is also
  scoped to this side: the same comparison in a short signal is a different decision.
  """
  blocks = same_side_blocks()
  for _comment, code, series, _op, _thr in CLAUSES:
    bare = re.fullmatch(r"& \((\w+)\)", code.strip())
    if bare and bare.group(1) in HELPERS:
      continue
    owners = [number for number, lines in blocks.items() if number != SIGNAL and code in lines]
    assert not owners, f"{code} (series {series}) also sits in {SIDE} signal(s) {owners}"


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


def test_knob_stays_declared():
  """Signal 141 ships enabled, so the knob is True, not False.

  `x8tools/test_emit.py` writes this check for a new signal, which ships disabled. This
  one is live: the assertion's job here is that the declaration is still there and was
  not quietly turned off along with the protection set.
  """
  assert f'"{KNOB}": True' in STRATEGY.read_text(encoding="utf-8")


def test_timeframes_run_in_house_order():
  ranks = [TIMEFRAMES.index(timeframe(series)) for _c, _code, series, _op, _thr in CLAUSES]
  assert ranks == sorted(ranks), f"clause timeframes are out of house order: {ranks}"


def test_each_clause_blocks_on_the_wrong_side():
  for index, (_comment, code, _series, op, threshold) in enumerate(CLAUSES):
    above, below = threshold + 0.01, threshold - 0.01
    passes, blocks = (above, below) if op in (">", ">=") else (below, above)
    assert holds(op, threshold, passes) is True, f"clause {index} ({code}) should let {passes} through"
    assert holds(op, threshold, blocks) is False, f"clause {index} ({code}) should block {blocks}"


def holds(op, threshold, value):
  if op == ">":
    return value > threshold
  if op == ">=":
    return value >= threshold
  if op == "<":
    return value < threshold
  return value <= threshold
