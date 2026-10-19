"""Regression guards for the 2026-10-19 X8/X7 bug audit (see reports/x8-bug-audit.md).

Each test pins one invariant that the audit found broken, so the defect cannot come back
silently. They are AST checks on the strategy sources: the failures were all in *static*
structure (a comparison sign, a name built by an f-string, a missing line in one entry block),
so no candle fixture is needed and the checks stay fast.

X7 carries the same three defects as X8, so every check runs against both files.

H1  short_grind_entry_v3/_v4 compare `slice_profit` with the LONG sign. `slice_profit` is the raw
    price change, so for a SHORT a positive value is the adverse move (price rose = loss). The four
    "loss recovery" signals must therefore test `>`. The short g21 must also measure from the same
    base as the long one (`slice_profit_entry`), so the two sides stay exact mirrors.
H2  Every cached `*_stoploss_u_e` reason must be built as `exit_<mode>_stoploss_u_e` (that is what
    every producer writes). A `exit_profit_<mode>_...` spelling silently disables the exclusion
    guard, so an armed u_e stop gets re-marked and postponed instead of respected.
H3  Every long entry-condition block must filter stale data with `num_empty_288`. Block 120 was the
    only one missing it.
"""

import ast
from pathlib import Path

REPO = Path(__file__).parents[2]

# file, grind-entry versions present in that file, minimum number of long entry-condition blocks
STRATEGIES = (
  ("NostalgiaForInfinityX8.py", ("v3", "v4"), 53),
  ("NostalgiaForInfinityX7.py", ("v3",), 51),
)


def _strategy_class(filename):
  tree = ast.parse((REPO / filename).read_text(encoding="utf-8"))
  return next(node for node in tree.body if isinstance(node, ast.ClassDef) and "NostalgiaForInfinity" in node.name)


def _function(cls, name):
  return next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _slice_profit_compares(function, names=("slice_profit",)):
  compares = []
  for node in ast.walk(function):
    if isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id in names:
      compares.append(node)
  return compares


def _constant_value(node):
  """Numeric value of a literal, including the unary minus that Python parses from a negative threshold."""
  if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
    return float(node.value)
  if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
    inner = node.operand
    if isinstance(inner, ast.Constant) and isinstance(inner.value, (int, float)):
      return -float(inner.value)
  return None


def test_short_grind_entry_treats_a_price_rise_as_the_adverse_move():
  for filename, versions, _ in STRATEGIES:
    cls = _strategy_class(filename)
    for version in versions:
      name = f"short_grind_entry_{version}"
      compares = _slice_profit_compares(_function(cls, name), ("slice_profit", "slice_profit_entry"))
      assert compares, f"{filename}:{name}: no slice_profit condition found"
      thresholds = set()
      for node in compares:
        assert len(node.ops) == 1, f"{filename}:{node.lineno}: chained comparison not supported by this guard"
        assert isinstance(node.ops[0], ast.Gt), (
          f"{filename}:{name}:{node.lineno}: a short loses when the price RISES, so the comparison must be "
          "'slice_profit > threshold'"
        )
        value = _constant_value(node.comparators[0])
        assert value is not None and value > 0, f"{filename}:{node.lineno}: threshold must be positive"
        thresholds.add(round(value, 4))
      assert thresholds == {0.02, 0.06, 0.10, 0.16}, f"{filename}:{name}: unexpected thresholds {sorted(thresholds)}"


def test_long_grind_entry_still_treats_a_price_drop_as_the_adverse_move():
  """Guard the asymmetry on purpose: the long side must keep the negative thresholds."""
  for filename, versions, _ in STRATEGIES:
    cls = _strategy_class(filename)
    for version in versions:
      name = f"long_grind_entry_{version}"
      compares = _slice_profit_compares(_function(cls, name), ("slice_profit", "slice_profit_entry"))
      assert compares, f"{filename}:{name}: no slice_profit condition found"
      for node in compares:
        assert isinstance(node.ops[0], ast.Lt), f"{filename}:{name}:{node.lineno}: the long side must compare with <"
        value = _constant_value(node.comparators[0])
        assert value is not None and value < 0, f"{filename}:{name}:{node.lineno}: threshold must be negative"


def _signed_thresholds(function):
  """(left-hand variable, abs(threshold)) pairs and the operators used, for one grind entry signal."""
  pairs = set()
  operators = set()
  for node in _slice_profit_compares(function, ("slice_profit", "slice_profit_entry")):
    value = _constant_value(node.comparators[0])
    if value is None:
      continue
    pairs.add((node.left.id, round(abs(value), 4)))
    operators.add(type(node.ops[0]).__name__)
  return pairs, operators


def test_long_and_short_grind_entry_are_exact_mirrors():
  """Both sides must use the same bases and thresholds; only the comparison sign flips (H1 follow-up)."""
  expected = {
    ("slice_profit", 0.16),
    ("slice_profit", 0.10),
    ("slice_profit", 0.06),
    ("slice_profit_entry", 0.02),
  }
  for filename, versions, _ in STRATEGIES:
    cls = _strategy_class(filename)
    for version in versions:
      long_pairs, long_ops = _signed_thresholds(_function(cls, f"long_grind_entry_{version}"))
      short_pairs, short_ops = _signed_thresholds(_function(cls, f"short_grind_entry_{version}"))
      assert long_pairs == short_pairs == expected, (
        f"{filename}:{version}: grind entry signals diverged: long={sorted(long_pairs)} short={sorted(short_pairs)}"
      )
      assert long_ops == {"Lt"}, f"{filename}:{version}: the long side must compare with <, got {sorted(long_ops)}"
      assert short_ops == {"Gt"}, f"{filename}:{version}: the short side must compare with >, got {sorted(short_ops)}"


def _fstring_template(node):
  parts = []
  for value in node.values:
    parts.append(str(value.value) if isinstance(value, ast.Constant) else "{...}")
  return "".join(parts)


def test_cached_stoploss_u_e_reason_uses_the_produced_name():
  for filename, _, _ in STRATEGIES:
    tree = ast.parse((REPO / filename).read_text(encoding="utf-8"))
    templates = {
      _fstring_template(node)
      for node in ast.walk(tree)
      if isinstance(node, ast.JoinedStr) and "stoploss_u_e" in _fstring_template(node)
    }
    bad = sorted(template for template in templates if "exit_profit_" in template)
    assert not bad, (
      f"{filename}: cached u_e stop built with the exit_profit_ prefix, which no producer ever writes: {bad}"
    )
    assert any(template.startswith("exit_{...}_stoploss_u_e") for template in templates), (
      f"{filename}: no canonical exit_<mode>_stoploss_u_e name found: {sorted(templates)}"
    )


def _appends_empty_candle_guard(statements):
  module = ast.Module(body=statements, type_ignores=[])
  for node in ast.walk(module):
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "append"):
      continue
    for arg in node.args:
      if any(isinstance(inner, ast.Name) and inner.id == "num_empty_288" for inner in ast.walk(arg)):
        return True
  return False


def test_every_long_entry_block_filters_empty_candles():
  for filename, _, minimum in STRATEGIES:
    cls = _strategy_class(filename)
    fn = _function(cls, "populate_entry_trend")

    total = 0
    missing = []
    for node in ast.walk(fn):
      if not isinstance(node, ast.If):
        continue
      test = node.test
      if not (
        isinstance(test, ast.Compare)
        and isinstance(test.left, ast.Name)
        and test.left.id == "long_entry_condition_index"
      ):
        continue
      total += 1
      if not _appends_empty_candle_guard(node.body):
        missing.append(test.comparators[0].value)

    assert total >= minimum, f"{filename}: expected at least {minimum} long entry-condition blocks, found {total}"
    assert not missing, f"{filename}: long entry blocks without the num_empty_288 guard: {sorted(missing)}"
