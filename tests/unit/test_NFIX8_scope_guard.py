"""Guard: no function in the strategy may read a name its scope chain never binds.

Context: the de-risk level 4 block of `long_grind_adjust_trade_position_v4` read
`derisk_4_threshold` / `derisk_4_stake`, but those names were only assigned in *other* methods
of the class (the v3_2 implementation), and a hard-coded `derisk_4_enable = False` short
circuit hid the problem until the config flag was wired up — at which point live trading would
raise `NameError`.

A file-wide "is it assigned somewhere?" check cannot catch that: the names *are* assigned in the
file. This test resolves names per scope: a read is valid only if the name is bound in the same
function, an enclosing function scope, the module globals, or builtins.
"""

import ast
import builtins
from pathlib import Path

STRATEGY_PATH = Path(__file__).parents[2] / "NostalgiaForInfinityX8.py"
# provided by the import machinery / runtime, not by user code
IGNORED = {"__file__", "__name__", "__doc__", "__spec__", "__package__", "__loader__", "__builtins__"}


def _module_names(tree):
  names = set(dir(builtins)) | IGNORED
  for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
      names.add(node.name)
    if isinstance(node, ast.Assign):
      for target in node.targets:
        for sub in ast.walk(target):
          if isinstance(sub, ast.Name):
            names.add(sub.id)
    if isinstance(node, ast.Import):
      for alias in node.names:
        names.add((alias.asname or alias.name).split(".")[0])
    if isinstance(node, ast.ImportFrom):
      for alias in node.names:
        names.add(alias.asname or alias.name)
    if isinstance(node, ast.Try):
      for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
          names.add(sub.id)
  return names


def _scope_names(fn):
  """Names bound in fn's own scope (nested function bodies excluded)."""
  names = set()
  for arg in fn.args.args + fn.args.kwonlyargs + fn.args.posonlyargs:
    names.add(arg.arg)
  if fn.args.vararg:
    names.add(fn.args.vararg.arg)
  if fn.args.kwarg:
    names.add(fn.args.kwarg.arg)

  def walk(node):
    for child in ast.iter_child_nodes(node):
      if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.add(child.name)  # the def statement binds a name here
        continue
      if isinstance(child, ast.Lambda):
        continue
      if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
        names.add(child.id)
      if isinstance(child, ast.ExceptHandler) and child.name:
        names.add(child.name)
      if isinstance(child, (ast.Global, ast.Nonlocal)):
        names.update(child.names)
      if isinstance(child, ast.comprehension):
        for target in ast.walk(child.target):
          if isinstance(target, ast.Name):
            names.add(target.id)
      walk(child)

  walk(fn)
  return names


def _find_undefined_reads(tree, lines):
  problems = []

  def traverse(node, known, function_name):
    for child in ast.iter_child_nodes(node):
      if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
        known.add(child.name)
        traverse_function(child, known)
        continue
      if isinstance(child, ast.Lambda):
        lambda_known = set(known)
        for arg in child.args.args + child.args.kwonlyargs + child.args.posonlyargs:
          lambda_known.add(arg.arg)
        if child.args.vararg:
          lambda_known.add(child.args.vararg.arg)
        if child.args.kwarg:
          lambda_known.add(child.args.kwarg.arg)
        traverse(child.body, lambda_known, function_name)
        continue
      if isinstance(child, ast.ClassDef):
        known.add(child.name)
        traverse(child, known, child.name)
        continue
      if isinstance(child, ast.Name):
        if isinstance(child.ctx, ast.Load):
          if child.id not in known:
            problems.append((child.lineno, function_name, child.id, lines[child.lineno - 1].strip()[:100]))
        else:
          known.add(child.id)
        continue
      if isinstance(child, ast.ExceptHandler) and child.name:
        known.add(child.name)
      if isinstance(child, ast.comprehension):
        for target in ast.walk(child.target):
          if isinstance(target, ast.Name):
            known.add(target.id)
      traverse(child, known, function_name)

  def traverse_function(fn, enclosing):
    known = set(enclosing) | _scope_names(fn)
    traverse(fn, known, fn.name)

  parents = {}
  for node in ast.walk(tree):
    for child in ast.iter_child_nodes(node):
      parents[child] = node

  def enclosing_function(node):
    parent = parents.get(node)
    while parent is not None:
      if isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
        return parent
      parent = parents.get(parent)
    return None

  module_names = _module_names(tree)
  for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and enclosing_function(node) is None:
      traverse_function(node, module_names)
  return problems


def test_no_undefined_name_reads_in_strategy():
  source = STRATEGY_PATH.read_text(encoding="utf-8")
  tree = ast.parse(source)
  lines = source.splitlines()
  problems = _find_undefined_reads(tree, lines)
  details = "\n".join(f"  line {ln} in {fn}(): `{name}` — {src}" for ln, fn, name, src in sorted(problems))
  assert not problems, f"read of names never bound in their scope chain:\n{details}"


def test_derisk_level_4_is_wired_in_v4_grind():
  """The v4 grind path must honour the level 4 flag and define its threshold/stake."""
  source = STRATEGY_PATH.read_text(encoding="utf-8")
  tree = ast.parse(source)
  fn = next(
    node
    for node in ast.walk(tree)
    if isinstance(node, ast.FunctionDef) and node.name == "long_grind_adjust_trade_position_v4"
  )
  body = ast.get_source_segment(source, fn) or ""
  assert "derisk_4_enable = self.system_v4_derisk_level_4_enable" in body
  assert "derisk_4_threshold = self.system_v4_derisk_level_4_futures[1]" in body
  assert "derisk_4_threshold = self.system_v4_derisk_level_4_spot[1]" in body
  assert "derisk_4_stake = self.system_v4_derisk_level_4_stake_futures" in body
  assert "derisk_4_stake = self.system_v4_derisk_level_4_stake_spot" in body
