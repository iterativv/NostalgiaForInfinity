"""Strict differential/evidence gate for OpenSpec #450.

This module deliberately cannot pass against the unrefactored source: Phase 4 must
first provide the architecture asserted below.  Baseline and feature are always
loaded from different source paths in the same Python process/image.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import platform
import sys
from collections import Counter
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURE_SOURCE = REPO_ROOT / "NostalgiaForInfinityX7.py"
RAW_OUTPUT = REPO_ROOT / "artifacts/nfix7-informative-raw.json"
PROFILES = ("1d", "4h", "1h", "15m")
WRAPPERS = {p: f"informative_{p}_indicators" for p in PROFILES}
ALLOWED_PATHS = sorted(
  [
    ".github/workflows/unit-tests.yml",
    "NostalgiaForInfinityX7.py",
    "tests/differential/test_NFIX7_informative_equivalence.py",
    "tests/differential/verify_nfix7_evidence.py",
    "tests/unit/test_NFIX7_informative_indicators.py",
  ]
)
REQUIRED_ENV = (
  "NFI_EVIDENCE_MODE",
  "NFI_BASE_SHA",
  "NFI_HEAD_SHA",
  "NFI_BASE_SOURCE_SHA256",
  "NFI_FEATURE_SOURCE_SHA256",
  "NFI_FEATURE_BUNDLE_SHA256",
  "NFI_CHANGED_PATHS_JSON",
  "NFI_CHANGED_PATHS_SHA256",
  "NFI_TEST_IMAGE_ID",
  "NFI_PRE_COMMIT_VERSION",
  "NFI_BASE_STRATEGY",
)
COMMON_RAW_KEYS = [
  "RSI_3",
  "RSI_14",
  "AROONU_14",
  "AROOND_14",
  "STOCHk_14_3_3",
  "MFI_14",
  "WILLR_14",
  "ROC_9",
  "change_pct",
]
COMMON_FINAL_KEYS = [
  "RSI_3",
  "RSI_14",
  "RSI_3_change_pct",
  "AROONU_14",
  "AROOND_14",
  "STOCHk_14_3_3",
  "STOCHRSIk_14_14_3_3",
  "MFI_14",
  "CMF_20",
  "WILLR_14",
  "ROC_9",
  "change_pct",
]
HELPERS = ("fast_pct_change", "stochrsi_k", "chaikin_money_flow", "calc_kst")


def _load_unit_support():
  path = REPO_ROOT / "tests/unit/test_NFIX7_informative_indicators.py"
  spec = importlib.util.spec_from_file_location("nfix7_unit_support", path)
  assert spec and spec.loader
  module = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(module)
  return module


support = _load_unit_support()
REPORT: dict[str, Any] = {
  "schema": 1,
  "matrix": {},
  "call_fingerprints": {},
  "debug_instrumentation": {},
  "runtime_instrumentation": {},
  "caller_source_gate": {},
  "structural_ast": {},
}


def sha256_path(path: Path) -> str:
  return hashlib.sha256(path.read_bytes()).hexdigest()


def class_node(path: Path) -> ast.ClassDef:
  tree = ast.parse(path.read_text())
  return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "NostalgiaForInfinityX7")


def method_node(path: Path, name: str) -> ast.FunctionDef:
  return next(n for n in class_node(path).body if isinstance(n, ast.FunctionDef) and n.name == name)


def call_name(node: ast.Call) -> str:
  if isinstance(node.func, ast.Name):
    return node.func.id
  if isinstance(node.func, ast.Attribute):
    parts = []
    value: ast.expr = node.func
    while isinstance(value, ast.Attribute):
      parts.append(value.attr)
      value = value.value
    if isinstance(value, ast.Name):
      parts.append(value.id)
    return ".".join(reversed(parts))
  return "<dynamic>"


def returned_dict_keys(method: ast.FunctionDef) -> list[str]:
  candidates = []
  for node in ast.walk(method):
    if isinstance(node, ast.Dict):
      keys = [k.value for k in node.keys if isinstance(k, ast.Constant) and isinstance(k.value, str)]
      if len(keys) > len(candidates):
        candidates = keys
  return candidates


def signature_shape(method: ast.FunctionDef) -> dict[str, Any]:
  args = method.args
  return {
    "positional": [a.arg for a in args.posonlyargs + args.args],
    "kwonly": [a.arg for a in args.kwonlyargs],
    "defaults": len(args.defaults),
    "kw_defaults": [x is not None for x in args.kw_defaults],
    "vararg": args.vararg.arg if args.vararg else None,
    "kwarg": args.kwarg.arg if args.kwarg else None,
    "annotations": [
      ast.unparse(a.annotation) if a.annotation else None for a in args.posonlyargs + args.args + args.kwonlyargs
    ],
    "returns": ast.unparse(method.returns) if method.returns else None,
  }


@pytest.fixture(scope="module")
def env():
  missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
  assert not missing, f"missing mandatory evidence environment: {missing}"
  values = {key: os.environ[key] for key in REQUIRED_ENV}
  assert values["NFI_EVIDENCE_MODE"] in ("local-precommit", "pull-request")
  if values["NFI_EVIDENCE_MODE"] == "pull-request":
    assert values["NFI_BASE_SHA"] != values["NFI_HEAD_SHA"]
  paths = json.loads(values["NFI_CHANGED_PATHS_JSON"])
  assert paths == ALLOWED_PATHS
  assert hashlib.sha256("\0".join(paths).encode()).hexdigest() == values["NFI_CHANGED_PATHS_SHA256"]
  baseline = Path(values["NFI_BASE_STRATEGY"]).resolve()
  assert baseline.is_file() and baseline != FEATURE_SOURCE.resolve()
  assert sha256_path(baseline) == values["NFI_BASE_SOURCE_SHA256"]
  assert sha256_path(FEATURE_SOURCE) == values["NFI_FEATURE_SOURCE_SHA256"]
  assert values["NFI_BASE_SOURCE_SHA256"] != values["NFI_FEATURE_SOURCE_SHA256"]
  return values


@pytest.fixture(scope="module")
def modules(env):
  baseline = support.load_strategy_module(Path(env["NFI_BASE_STRATEGY"]), "nfix7_diff_baseline")
  feature = support.load_strategy_module(FEATURE_SOURCE, "nfix7_diff_feature")
  assert baseline.__name__ != feature.__name__
  assert Path(baseline.__file__).resolve() != Path(feature.__file__).resolve()
  return baseline, feature


def run_wrapper(module, profile: str, frame: pd.DataFrame):
  strategy = support.make_strategy(module.NostalgiaForInfinityX7)
  strategy.dp = support.FakeDP(frame)
  result = getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, profile)
  return result, strategy.dp.calls


def assert_special_masks_equal(left: pd.DataFrame, right: pd.DataFrame):
  for predicate in (np.isnan, np.isposinf, np.isneginf):
    np.testing.assert_array_equal(predicate(left.to_numpy()), predicate(right.to_numpy()))


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("fixture_name", list(support.fixture_matrix()))
def test_exact_differential_matrix(modules, fixture_name, profile):
  baseline, feature = modules
  left_source = support.fixture_matrix()[fixture_name]
  right_source = left_source.copy(deep=True)
  left_before = left_source.copy(deep=True)
  right_before = right_source.copy(deep=True)
  left, left_calls = run_wrapper(baseline, profile, left_source)
  right, right_calls = run_wrapper(feature, profile, right_source)
  assert_frame_equal(
    left,
    right,
    check_like=False,
    check_exact=True,
    check_dtype=True,
    check_index_type=True,
    check_column_type=True,
    check_names=True,
  )
  assert_special_masks_equal(left, right)
  assert_frame_equal(left_source, left_before, check_exact=True)
  assert_frame_equal(right_source, right_before, check_exact=True)
  assert left_calls == right_calls == [{"pair": "TEST/USDT", "timeframe": profile}]
  REPORT["matrix"][f"{fixture_name}:{profile}"] = "passed"


def _instrument_calls(module, profile: str):
  ta_trace: list[dict[str, Any]] = []
  originals = {}
  ta_names = sorted(set().union(*[set(v) for v in support.EXPECTED_TA_COUNTS.values()]))
  for name in ta_names:
    original = getattr(module.ta, name)
    originals[name] = original

    def wrapper(*args, __name=name, __original=original, **kwargs):
      ta_trace.append(support.canonical_call(__name, args, kwargs))
      return __original(*args, **kwargs)

    wrapper.__name__ = name
    setattr(module.ta, name, wrapper)
  cls = module.NostalgiaForInfinityX7
  helper_trace: list[dict[str, Any]] = []

  class Stateful(cls):
    counter = 0

    def _record(self, name, args, kwargs, inherited):
      self.counter += 1
      helper_trace.append(support.canonical_call(name, args, kwargs) | {"counter": self.counter})
      result = inherited(*args, **kwargs)
      delta = self.counter * 2**-40
      return tuple(np.asarray(x) + delta for x in result) if isinstance(result, tuple) else np.asarray(result) + delta

    def fast_pct_change(self, *a, **k):
      return self._record("fast_pct_change", a, k, cls.fast_pct_change)

    def stochrsi_k(self, *a, **k):
      return self._record("stochrsi_k", a, k, cls.stochrsi_k)

    def chaikin_money_flow(self, *a, **k):
      return self._record("chaikin_money_flow", a, k, cls.chaikin_money_flow)

    def calc_kst(self, *a, **k):
      return self._record("calc_kst", a, k, cls.calc_kst)

  try:
    strategy = support.make_strategy(Stateful)
    strategy.dp = support.FakeDP(support.normal_frame())
    frame = getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, profile)
  finally:
    for name, original in originals.items():
      setattr(module.ta, name, original)
  canonical_ta = sorted(ta_trace, key=lambda value: json.dumps(value, sort_keys=True))
  return canonical_ta, helper_trace, frame


@pytest.mark.parametrize("profile", PROFILES)
def test_call_fingerprints_and_stateful_helper_outputs(modules, profile):
  baseline, feature = modules
  base_ta, base_helpers, base_frame = _instrument_calls(baseline, profile)
  feature_ta, feature_helpers, feature_frame = _instrument_calls(feature, profile)
  assert base_ta == feature_ta
  assert base_helpers == feature_helpers
  assert [x["name"] for x in base_helpers] == support.EXPECTED_HELPER_ORDER[profile]
  assert Counter(x["name"] for x in base_ta) == Counter(support.EXPECTED_TA_COUNTS[profile])
  assert_frame_equal(base_frame, feature_frame, check_exact=True)
  REPORT["call_fingerprints"][profile] = {"ta": base_ta, "helpers": base_helpers, "passed": True}


def test_source_identity_and_environment_manifest(env):
  REPORT["identity"] = {
    "mode": env["NFI_EVIDENCE_MODE"],
    "base_sha": env["NFI_BASE_SHA"],
    "head_sha": env["NFI_HEAD_SHA"],
    "base_source_sha256": env["NFI_BASE_SOURCE_SHA256"],
    "feature_source_sha256": env["NFI_FEATURE_SOURCE_SHA256"],
    "feature_bundle_sha256": env["NFI_FEATURE_BUNDLE_SHA256"],
    "changed_paths": json.loads(env["NFI_CHANGED_PATHS_JSON"]),
    "changed_paths_sha256": env["NFI_CHANGED_PATHS_SHA256"],
    "image_id": env["NFI_TEST_IMAGE_ID"],
    "pre_commit_version": env["NFI_PRE_COMMIT_VERSION"],
  }


def test_context_and_exact_method_signatures():
  tree = ast.parse(FEATURE_SOURCE.read_text())
  context = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_NFIInformativeContext")
  assert any(
    isinstance(d, ast.Call)
    and call_name(d) == "dataclass"
    and any(k.arg == "frozen" and isinstance(k.value, ast.Constant) and k.value.value is True for k in d.keywords)
    for d in context.decorator_list
  )
  fields = [n.target.id for n in context.body if isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name)]
  assert fields == ["source", "index", "open", "high", "low", "close", "volume"]
  expected = {
    "informative_indicators": {
      "positional": ["self", "metadata", "info_timeframe"],
      "kwonly": [],
      "returns": "DataFrame",
    },
    "_nfix7_informative_indicators_impl": {
      "positional": ["self", "metadata"],
      "kwonly": ["loaded_timeframe", "profile"],
      "returns": "DataFrame",
    },
  }
  for name, wanted in expected.items():
    shape = signature_shape(method_node(FEATURE_SOURCE, name))
    assert shape["positional"] == wanted["positional"] and shape["kwonly"] == wanted["kwonly"]
    assert (
      shape["vararg"] is None and shape["kwarg"] is None and shape["defaults"] == 0 and not any(shape["kw_defaults"])
    )
    assert shape["returns"] == wanted["returns"]
  core = signature_shape(method_node(FEATURE_SOURCE, "_nfix7_informative_indicators_impl"))
  assert core["annotations"] == [None, "dict", "str", "str"]
  raw = signature_shape(method_node(FEATURE_SOURCE, "_nfix7_common_raw_values"))
  assert raw == {
    "positional": ["context"],
    "kwonly": [],
    "defaults": 0,
    "kw_defaults": [],
    "vararg": None,
    "kwarg": None,
    "annotations": [None],
    "returns": None,
  }
  assembly = signature_shape(method_node(FEATURE_SOURCE, "_nfix7_assemble_common_values"))
  assert assembly == {
    "positional": ["raw"],
    "kwonly": ["rsi3_change", "stochrsi_k", "cmf"],
    "defaults": 0,
    "kw_defaults": [False, False, False],
    "vararg": None,
    "kwarg": None,
    "annotations": [None, None, None, None],
    "returns": None,
  }
  REPORT["structural_ast"]["signatures"] = "passed"


def _calls(method):
  return [n for n in ast.walk(method) if isinstance(n, ast.Call)]


def test_structural_ast_ownership_and_architecture():
  cls = class_node(FEATURE_SOURCE)
  methods = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
  region_names = [
    "informative_indicators",
    *WRAPPERS.values(),
    "_nfix7_informative_indicators_impl",
    "_nfix7_common_raw_values",
    "_nfix7_assemble_common_values",
    "_nfix7_build_1d_columns",
    "_nfix7_build_4h_columns",
    "_nfix7_build_1h_columns",
    "_nfix7_build_15m_columns",
  ]
  assert all(name in methods for name in region_names)
  core = methods["_nfix7_informative_indicators_impl"]
  raw = methods["_nfix7_common_raw_values"]
  assembly = methods["_nfix7_assemble_common_values"]
  assert any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in raw.decorator_list)
  assert any(isinstance(d, ast.Name) and d.id == "staticmethod" for d in assembly.decorator_list)
  assert returned_dict_keys(raw) == COMMON_RAW_KEYS
  assert returned_dict_keys(assembly) == COMMON_FINAL_KEYS
  raw_calls = Counter(call_name(c).split(".")[-1] for c in _calls(raw))
  assert raw_calls == Counter({"RSI": 2, "AROON": 1, "STOCHF": 1, "MFI": 1, "WILLR": 1, "ROC": 1, "where": 1})
  assert not any(call_name(c).split(".")[-1] in HELPERS for c in _calls(assembly))

  prohibited_dynamic = {"getattr", "setattr", "__import__"}
  for name in region_names:
    calls = [call_name(c) for c in _calls(methods[name])]
    assert not any(c.split(".")[-1] in prohibited_dynamic or c.startswith("importlib") for c in calls)

  ownership_tokens = (
    "get_pair_dataframe",
    "_NFIInformativeContext",
    "pd.DataFrame",
    "pd.concat",
    "validate_indicators",
    "log.debug",
  )
  for name in region_names:
    if name == core.name:
      continue
    calls = [call_name(c) for c in _calls(methods[name])]
    assert not any(token in calls for token in ownership_tokens), (name, calls)
    assert not any(
      isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self" and n.attr == "dp"
      for n in ast.walk(methods[name])
    )
    assert not any(
      isinstance(n, ast.Subscript)
      and isinstance(n.value, ast.Name)
      and n.value.id == "metadata"
      and isinstance(n.slice, ast.Constant)
      and n.slice.value == "pair"
      for n in ast.walk(methods[name])
    )

  core_calls = Counter(call_name(c) for c in _calls(core))
  for exact in ("get_pair_dataframe", "_NFIInformativeContext", "pd.DataFrame", "pd.concat"):
    assert sum(count for name, count in core_calls.items() if name.endswith(exact)) == 1, (exact, core_calls)
  assert sum(isinstance(n, ast.Assert) for n in ast.walk(core)) == 1
  returns = [n for n in ast.walk(core) if isinstance(n, ast.Return)]
  assert any(isinstance(n.value, ast.Name) for n in returns)
  assignments = Counter(
    t.id
    for n in ast.walk(core)
    if isinstance(n, ast.Assign)
    for t in n.targets
    if isinstance(t, ast.Name) and t.id in ("debug", "debug_time")
  )
  assert assignments == {"debug": 1, "debug_time": 1}

  for profile, wrapper_name in WRAPPERS.items():
    wrapper = methods[wrapper_name]
    executable = [n for n in wrapper.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant)]
    assert len(executable) == 1 and isinstance(executable[0], ast.Return) and isinstance(executable[0].value, ast.Call)
    call = executable[0].value
    assert call_name(call) == "NostalgiaForInfinityX7._nfix7_informative_indicators_impl"
    assert [k.arg for k in call.keywords] == ["loaded_timeframe", "profile"]
    assert isinstance(call.keywords[0].value, ast.Name) and call.keywords[0].value.id == "info_timeframe"
    assert isinstance(call.keywords[1].value, ast.Constant) and call.keywords[1].value.value == profile

  public = methods["informative_indicators"]
  assert any(
    isinstance(n, ast.Tuple) and [e.value for e in n.elts if isinstance(e, ast.Constant)] == list(PROFILES)
    for n in ast.walk(public)
  )
  assert any(call_name(c) == "NostalgiaForInfinityX7._nfix7_informative_indicators_impl" for c in _calls(public))

  builders = [methods[f"_nfix7_build_{p}_columns"] for p in PROFILES]
  for builder in builders:
    calls = Counter(call_name(c) for c in _calls(builder))
    assert calls["NostalgiaForInfinityX7._nfix7_common_raw_values"] == 1
    assert calls["NostalgiaForInfinityX7._nfix7_assemble_common_values"] == 1
    assert not any(other.name in " ".join(calls) for other in builders if other is not builder)
  REPORT["structural_ast"]["ownership"] = "passed"


class _ProbeTransformer(ast.NodeTransformer):
  def __init__(self):
    self.in_core = False
    self.found = Counter()

  def visit_FunctionDef(self, node):
    previous = self.in_core
    if node.name != "_nfix7_informative_indicators_impl":
      return node
    self.in_core = True
    node = self.generic_visit(node)
    self.in_core = previous
    return node

  def visit_Call(self, node):
    node = self.generic_visit(node)
    if not self.in_core:
      return node
    name = call_name(node)
    label = None
    if name.endswith("_NFIInformativeContext"):
      label = "context"
    elif name == "pd.DataFrame":
      label = "dataframe"
    elif name == "pd.concat":
      label = "concat"
    elif isinstance(node.func, ast.Name) and node.func.id in ("builder", "selected_builder"):
      label = "builder"
    if label:
      self.found[label] += 1
      return ast.copy_location(
        ast.Call(
          func=ast.Name(id="_nfi_probe", ctx=ast.Load()),
          args=[ast.Constant(label), node.func, *node.args],
          keywords=node.keywords,
        ),
        node,
      )
    return node


def _instrumented_feature_module():
  tree = ast.parse(FEATURE_SOURCE.read_text(), filename=str(FEATURE_SOURCE))
  transformer = _ProbeTransformer()
  tree = transformer.visit(tree)
  ast.fix_missing_locations(tree)
  assert transformer.found == {"context": 1, "builder": 1, "dataframe": 1, "concat": 1}
  spec = importlib.util.spec_from_loader("nfix7_runtime_instrumented", loader=None)
  assert spec is not None
  module = importlib.util.module_from_spec(spec)
  module.__file__ = str(FEATURE_SOURCE)
  sys.modules[module.__name__] = module
  exec(compile(tree, str(FEATURE_SOURCE), "exec"), module.__dict__)
  return module


@pytest.mark.parametrize("profile", PROFILES)
@pytest.mark.parametrize("empty", [False, True])
def test_runtime_structural_instrumentation(profile, empty):
  module = _instrumented_feature_module()
  counters = Counter()

  def probe(label, function, *args, **kwargs):
    counters[label] += 1
    return function(*args, **kwargs)

  module._nfi_probe = probe
  source = support.fixture_matrix()["empty" if empty else "normal_512"]
  strategy = support.make_strategy(module.NostalgiaForInfinityX7)
  strategy.dp = support.FakeDP(source)
  result = getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, profile)
  counters["dp"] = len(strategy.dp.calls)
  expected = {
    "dp": 1,
    "context": 0 if empty else 1,
    "builder": 0 if empty else 1,
    "dataframe": 0 if empty else 1,
    "concat": 0 if empty else 1,
  }
  assert {key: counters[key] for key in expected} == expected
  if empty:
    assert result is source
  REPORT["runtime_instrumentation"][f"{profile}:{'empty' if empty else 'nonempty'}"] = expected


class _DebugTransformer(ast.NodeTransformer):
  def __init__(self, target):
    self.target = target
    self.inside = False
    self.counts = Counter()

  def visit_FunctionDef(self, node):
    old = self.inside
    if node.name != self.target:
      return node
    self.inside = True
    node = self.generic_visit(node)
    self.inside = old
    return node

  def visit_Assign(self, node):
    node = self.generic_visit(node)
    if (
      self.inside
      and len(node.targets) == 1
      and isinstance(node.targets[0], ast.Name)
      and node.targets[0].id in ("debug", "debug_time")
      and isinstance(node.value, ast.Constant)
      and node.value.value is False
    ):
      self.counts[node.targets[0].id] += 1
      node.value = ast.Constant(True)
    return node


def _debug_module(path: Path, name: str, target: str):
  tree = ast.parse(path.read_text(), filename=str(path))
  transform = _DebugTransformer(target)
  tree = transform.visit(tree)
  ast.fix_missing_locations(tree)
  assert transform.counts == {"debug": 1, "debug_time": 1}
  spec = importlib.util.spec_from_loader(name, loader=None)
  assert spec is not None
  module = importlib.util.module_from_spec(spec)
  module.__file__ = str(path)
  sys.modules[name] = module
  exec(compile(tree, str(path), "exec"), module.__dict__)
  return module


def _debug_observation(module, profile):
  strategy = support.make_strategy(module.NostalgiaForInfinityX7)
  strategy.dp = support.FakeDP(support.normal_frame())
  validator = Mock()
  strategy.validate_indicators = validator
  logger = Mock()
  module.log = logger
  outcome = None
  try:
    getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, "custom-sentinel")
  except Exception as error:
    outcome = (type(error).__name__, str(error))
  assert validator.call_count == 1 and logger.debug.call_count == 1
  kwargs = validator.call_args.kwargs
  log_args = logger.debug.call_args.args
  return {
    "outcome": outcome,
    "columns": kwargs["columns"],
    "pair": kwargs["pair"],
    "timeframe": kwargs["timeframe"],
    "df_columns": list(kwargs["df"].columns),
    "log_format": log_args[0],
    "log_pair": log_args[1],
  }


@pytest.mark.parametrize("profile", PROFILES)
def test_debug_instrumentation(env, profile):
  baseline = _debug_module(Path(env["NFI_BASE_STRATEGY"]), f"nfix7_debug_base_{profile}", WRAPPERS[profile])
  feature = _debug_module(FEATURE_SOURCE, f"nfix7_debug_feature_{profile}", "_nfix7_informative_indicators_impl")
  left = _debug_observation(baseline, profile)
  right = _debug_observation(feature, profile)
  assert left == right
  REPORT["debug_instrumentation"][profile] = left | {"passed": True}


def ast_hash(path: Path, method: str) -> str:
  payload = ast.dump(method_node(path, method), include_attributes=False).encode()
  return hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("method", ["info_switcher", "populate_indicators"])
def test_unchanged_caller_source_hash(env, method):
  baseline_hash = ast_hash(Path(env["NFI_BASE_STRATEGY"]), method)
  feature_hash = ast_hash(FEATURE_SOURCE, method)
  assert baseline_hash == feature_hash
  REPORT["caller_source_gate"][method] = {"baseline": baseline_hash, "feature": feature_hash, "passed": True}


def _package_version(distribution: str) -> str:
  try:
    return importlib.metadata.version(distribution)
  except importlib.metadata.PackageNotFoundError:
    return "not-installed"


def test_zz_emit_raw_evidence(env):
  assert len(REPORT["matrix"]) == len(support.fixture_matrix()) * len(PROFILES)
  assert set(REPORT["call_fingerprints"]) == set(PROFILES)
  assert set(REPORT["debug_instrumentation"]) == set(PROFILES)
  assert len(REPORT["runtime_instrumentation"]) == len(PROFILES) * 2
  assert set(REPORT["caller_source_gate"]) == {"info_switcher", "populate_indicators"}
  REPORT["manifest"] = REPORT["identity"] | {
    "python": platform.python_version(),
    "freqtrade": _package_version("freqtrade"),
    "pandas": pd.__version__,
    "numpy": np.__version__,
    "ta_lib": _package_version("TA-Lib"),
    "test_counts": {
      "fixtures": len(support.fixture_matrix()),
      "profiles": len(PROFILES),
      "matrix_cases": len(REPORT["matrix"]),
    },
  }
  REPORT["result"] = "passed"
  RAW_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
  RAW_OUTPUT.write_text(json.dumps(REPORT, indent=2, sort_keys=True) + "\n")
  assert RAW_OUTPUT.is_file() and RAW_OUTPUT.stat().st_size > 0
