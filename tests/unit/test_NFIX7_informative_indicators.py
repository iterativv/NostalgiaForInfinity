"""Executable characterization for the NFI X7 informative-indicator refactor (#450).

The two ``new_public`` tests are intentionally RED until Phase 4 adds the API.
Everything else is required to pass against the immutable unrefactored baseline.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURE_SOURCE = REPO_ROOT / "NostalgiaForInfinityX7.py"
BASELINE_SOURCE = REPO_ROOT / "artifacts/nfix7-baseline/NostalgiaForInfinityX7.py"
PROFILES = ("1d", "4h", "1h", "15m")
WRAPPERS = {profile: f"informative_{profile}_indicators" for profile in PROFILES}
DP_ASSERTION = "DataProvider is required for multiple timeframes."

SOURCE_COLUMNS = ["open", "high", "low", "close", "volume"]
EXPECTED_GENERATED_COLUMNS = {
  "1d": [
    "RSI_3",
    "RSI_14",
    "STOCHk_14_3_3",
    "STOCHRSIk_14_14_3_3",
    "MFI_14",
    "CMF_20",
    "WILLR_14",
    "AROONU_14",
    "AROOND_14",
    "ROC_2",
    "ROC_9",
    "RSI_3_change_pct",
    "change_pct",
    "top_wick_pct",
    "bot_wick_pct",
    "high_max_6",
    "high_max_12",
    "high_max_20",
    "high_max_30",
    "low_min_6",
    "low_min_12",
    "low_min_20",
    "low_min_30",
  ],
  "4h": [
    "RSI_3",
    "RSI_14",
    "ADX_14",
    "PLUS_DI_14",
    "MINUS_DI_14",
    "AROONU_14",
    "AROOND_14",
    "BBP_20_2.0",
    "STOCHk_14_3_3",
    "STOCHRSIk_14_14_3_3",
    "KST_10_15_20_30_10_10_10_15",
    "KSTs_9",
    "MFI_14",
    "CMF_20",
    "EMA_12",
    "EMA_50",
    "EMA_100",
    "EMA_200",
    "WILLR_14",
    "UO_7_14_28",
    "ROC_2",
    "ROC_9",
    "CCI_20",
    "STOCHRSIk_14_14_3_3_change_pct",
    "CCI_20_change_pct",
    "RSI_3_change_pct",
    "RSI_14_change_pct",
    "change_pct",
    "top_wick_pct",
    "high_max_6",
    "high_max_12",
    "high_max_24",
    "low_min_12",
    "low_min_24",
  ],
  "1h": [
    "RSI_3",
    "RSI_14",
    "RSI_3_change_pct",
    "RSI_14_change_pct",
    "EMA_12",
    "EMA_200",
    "SMA_16",
    "BBL_20_2.0",
    "BBU_20_2.0",
    "BBB_20_2.0",
    "MFI_14",
    "CMF_20",
    "WILLR_14",
    "WILLR_84",
    "AROONU_14",
    "AROOND_14",
    "STOCHk_14_3_3",
    "STOCHRSIk_14_14_3_3",
    "KST_10_15_20_30_10_10_10_15",
    "KSTs_9",
    "UO_7_14_28",
    "ROC_2",
    "ROC_9",
    "CCI_20",
    "CCI_20_change_pct",
    "change_pct",
    "high_max_6",
    "high_max_12",
    "high_max_24",
    "low_min_6",
    "low_min_12",
    "low_min_24",
  ],
  "15m": [
    "RSI_3",
    "RSI_14",
    "RSI_3_change_pct",
    "RSI_14_change_pct",
    "EMA_12",
    "EMA_20",
    "EMA_26",
    "EMA_50",
    "EMA_200",
    "MFI_14",
    "CMF_20",
    "WILLR_14",
    "AROONU_14",
    "AROOND_14",
    "STOCHk_14_3_3",
    "STOCHRSIk_14_14_3_3",
    "UO_7_14_28",
    "UO_7_14_28_change_pct",
    "OBV_change_pct",
    "ROC_9",
    "CCI_20",
    "CCI_20_change_pct",
    "change_pct",
  ],
}
EXPECTED_HELPER_ORDER = {
  "1d": ["stochrsi_k", "chaikin_money_flow", "fast_pct_change"],
  "4h": ["stochrsi_k", "calc_kst", "chaikin_money_flow"] + ["fast_pct_change"] * 4,
  "1h": ["stochrsi_k", "calc_kst", "chaikin_money_flow"] + ["fast_pct_change"] * 3,
  "15m": ["stochrsi_k", "chaikin_money_flow"] + ["fast_pct_change"] * 5,
}
EXPECTED_TA_COUNTS = {
  "1d": {"RSI": 2, "AROON": 1, "STOCHF": 1, "MIN": 5, "MAX": 5, "SMA": 1, "MFI": 1, "WILLR": 1, "ROC": 2},
  "4h": {
    "RSI": 2,
    "AROON": 1,
    "ADX": 1,
    "PLUS_DI": 1,
    "MINUS_DI": 1,
    "BBANDS": 1,
    "STOCHF": 1,
    "MIN": 3,
    "MAX": 4,
    "SMA": 6,
    "ROC": 6,
    "MFI": 1,
    "EMA": 4,
    "WILLR": 1,
    "ULTOSC": 1,
    "CCI": 1,
  },
  "1h": {
    "RSI": 2,
    "BBANDS": 1,
    "AROON": 1,
    "STOCHF": 1,
    "MIN": 4,
    "MAX": 4,
    "SMA": 7,
    "ROC": 6,
    "MFI": 1,
    "EMA": 2,
    "WILLR": 2,
    "ULTOSC": 1,
    "CCI": 1,
  },
  "15m": {
    "RSI": 2,
    "AROON": 1,
    "STOCHF": 1,
    "MIN": 1,
    "MAX": 1,
    "SMA": 1,
    "MFI": 1,
    "EMA": 5,
    "WILLR": 1,
    "ULTOSC": 1,
    "OBV": 1,
    "ROC": 1,
    "CCI": 1,
  },
}
CALLABLE_ROLES = {
  ("stochrsi_k", 1): ("ta_min", "MIN"),
  ("stochrsi_k", 2): ("ta_max", "MAX"),
  ("stochrsi_k", 3): ("ta_sma", "SMA"),
  ("calc_kst", 1): ("ta_roc", "ROC"),
  ("calc_kst", 2): ("ta_sma", "SMA"),
}


def load_strategy_module(path: Path, name: str):
  spec = importlib.util.spec_from_file_location(name, path)
  assert spec and spec.loader
  module = importlib.util.module_from_spec(spec)
  sys.modules[name] = module
  spec.loader.exec_module(module)
  return module


def make_strategy(cls):
  strategy = object.__new__(cls)
  strategy.dp = None
  return strategy


class FakeDP:
  def __init__(self, frame: pd.DataFrame):
    self.frame = frame
    self.calls: list[dict[str, Any]] = []

  def get_pair_dataframe(self, **kwargs):
    self.calls.append(kwargs)
    return self.frame


def normal_frame(length: int = 512) -> pd.DataFrame:
  i = np.arange(512, dtype=np.float64)
  open_ = 100 + 0.05 * i + 2 * np.sin(i / 11)
  close = open_ + 0.7 * np.sin(i / 7)
  frame = pd.DataFrame(
    {
      "open": open_,
      "high": np.maximum(open_, close) + 1 + 0.1 * (i % 5),
      "low": np.minimum(open_, close) - 1 - 0.1 * (i % 3),
      "close": close,
      "volume": 1000 + 10 * (i % 17) + 0.5 * i,
    },
    index=pd.date_range("2024-01-01T00:00:00Z", periods=512, freq="5min"),
  )
  return frame.iloc[:length].copy()


def fixture_matrix() -> dict[str, pd.DataFrame]:
  normal = normal_frame()
  empty = normal.iloc[:0].copy()
  zero_open = normal.copy()
  zero_open.iloc[[0, 256, 511], zero_open.columns.get_loc("open")] = 0.0
  nan_ohlcv = normal.copy()
  for column, row in {"open": 3, "high": 17, "low": 63, "close": 255, "volume": 400}.items():
    nan_ohlcv.iloc[row, nan_ohlcv.columns.get_loc(column)] = np.nan
  passthrough = normal.copy()
  passthrough["custom_passthrough"] = np.arange(512, dtype=np.float64)
  duplicate = normal.copy()
  duplicate["RSI_3"] = np.arange(512, dtype=np.float64)
  non_default = normal.copy()
  non_default.index = pd.Index(1000 + 3 * np.arange(512), name="non_default")
  return {
    "normal_512": normal,
    "empty": empty,
    "short_1": normal_frame(1),
    "short_13": normal_frame(13),
    "short_199": normal_frame(199),
    "zero_open": zero_open,
    "nan_ohlcv": nan_ohlcv,
    "passthrough": passthrough,
    "duplicate_indicator": duplicate,
    "non_default_index": non_default,
  }


def array_fingerprint(value: Any):
  array = np.asarray(value)
  contiguous = np.ascontiguousarray(array)
  return (array.shape, array.dtype.str, hashlib.sha256(contiguous.view(np.uint8).tobytes()).hexdigest())


def value_fingerprint(call: str, position: int | None, value: Any):
  role = CALLABLE_ROLES.get((call, position))
  if role:
    semantic, expected_name = role
    # ``talib.abstract.Function`` is callable but exposes its stable semantic
    # name through ``info`` rather than ``__name__`` in the pinned image.
    callable_name = getattr(value, "__name__", None) or getattr(value, "info", {}).get("name")
    assert callable(value) and callable_name == expected_name
    return ("callable-role", semantic, type(value).__name__)
  if isinstance(value, (np.ndarray, pd.Series)):
    return ("array",) + array_fingerprint(value)
  return (f"{type(value).__module__}.{type(value).__qualname__}", repr(value))


def canonical_call(call: str, args: tuple[Any, ...], kwargs: dict[str, Any]):
  return {
    "name": call,
    "args": [value_fingerprint(call, i, value) for i, value in enumerate(args)],
    "kwargs": [(key, value_fingerprint(call, None, kwargs[key])) for key in sorted(kwargs)],
  }


def ast_method(source: Path, name: str) -> ast.FunctionDef:
  tree = ast.parse(source.read_text())
  cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "NostalgiaForInfinityX7")
  return next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == name)


def signature_dump(node: ast.FunctionDef) -> str:
  return ast.dump(
    ast.Module(
      body=[
        ast.FunctionDef(
          name="method", args=node.args, body=[ast.Pass()], decorator_list=[], returns=node.returns, type_comment=None
        )
      ],
      type_ignores=[],
    ),
    include_attributes=False,
  )


@pytest.fixture(scope="module")
def feature_module():
  return load_strategy_module(FEATURE_SOURCE, "nfix7_unit_feature")


@pytest.mark.parametrize("profile", PROFILES)
def test_exact_profile_columns_and_source_immutability(feature_module, profile):
  source = normal_frame()
  before = source.copy(deep=True)
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  strategy.dp = FakeDP(source)
  result = getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, profile)
  assert list(result.columns) == SOURCE_COLUMNS + EXPECTED_GENERATED_COLUMNS[profile]
  assert_frame_equal(source, before, check_exact=True)
  assert result.index is source.index


@pytest.mark.parametrize("loaded_timeframe", ["4h", "custom-sentinel"])
def test_direct_1d_wrapper_passes_loaded_timeframe_unchanged(feature_module, loaded_timeframe):
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  strategy.dp = FakeDP(normal_frame(13))
  strategy.informative_1d_indicators({"pair": "TEST/USDT"}, loaded_timeframe)
  assert strategy.dp.calls == [{"pair": "TEST/USDT", "timeframe": loaded_timeframe}]


def test_dp_assertion_precedes_metadata_for_wrapper(feature_module):
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  with pytest.raises(AssertionError, match=f"^{DP_ASSERTION}$"):
    strategy.informative_1d_indicators({}, "custom-sentinel")


def test_missing_pair_precedes_dp_call_for_wrapper(feature_module):
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  strategy.dp = FakeDP(normal_frame(1))
  with pytest.raises(KeyError) as error:
    strategy.informative_1d_indicators({}, "custom-sentinel")
  assert error.value.args == ("pair",)
  assert strategy.dp.calls == []


def test_info_switcher_unsupported_exact_error(feature_module):
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  with pytest.raises(RuntimeError) as error:
    strategy.info_switcher({"pair": "TEST/USDT"}, "2h")
  assert str(error.value) == "2h not supported as informative timeframe for BTC pair."


def test_info_switcher_is_virtual_and_ignores_public_name_collision(feature_module):
  class Collision(feature_module.NostalgiaForInfinityX7):
    def informative_1d_indicators(self, metadata, info_timeframe):
      return ("wrapper", metadata, info_timeframe)

    def informative_indicators(self, *args, **kwargs):
      raise AssertionError("colliding additive API must not be called")

  strategy = make_strategy(Collision)
  assert strategy.info_switcher({"pair": "P"}, "1d") == ("wrapper", {"pair": "P"}, "1d")


@pytest.mark.parametrize("profile", PROFILES)
def test_empty_returns_identical_object_without_ta_or_helpers(feature_module, monkeypatch, profile):
  source = fixture_matrix()["empty"]
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  strategy.dp = FakeDP(source)

  def forbidden(*args, **kwargs):
    raise AssertionError("empty guard must precede TA/helper/context/builder work")

  for name in dir(feature_module.ta):
    if name.isupper() and callable(getattr(feature_module.ta, name)):
      monkeypatch.setattr(feature_module.ta, name, forbidden)
  for name in ("fast_pct_change", "stochrsi_k", "chaikin_money_flow", "calc_kst"):
    monkeypatch.setattr(strategy, name, forbidden)
  if hasattr(feature_module, "_NFIInformativeContext"):
    monkeypatch.setattr(feature_module, "_NFIInformativeContext", forbidden)
  result = getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, "custom-sentinel")
  assert result is source
  assert strategy.dp.calls == [{"pair": "TEST/USDT", "timeframe": "custom-sentinel"}]


@pytest.mark.parametrize("profile", PROFILES)
def test_passthrough_duplicate_labels_and_non_default_index(feature_module, profile):
  for fixture_name in ("passthrough", "duplicate_indicator", "non_default_index"):
    source = fixture_matrix()[fixture_name]
    strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
    strategy.dp = FakeDP(source)
    result = getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, profile)
    assert list(result.columns[: len(source.columns)]) == list(source.columns)
    assert result.index.equals(source.index)
    assert result.index.name == source.index.name
    if fixture_name == "duplicate_indicator":
      assert list(result.columns).count("RSI_3") == 2


@pytest.mark.parametrize("profile", PROFILES)
def test_stateful_helper_order_and_outputs_are_deterministic(feature_module, profile):
  base_cls = feature_module.NostalgiaForInfinityX7

  class Stateful(base_cls):
    trace: list[dict[str, Any]]
    counter: int

    def _record(self, name, args, kwargs, inherited):
      self.counter += 1
      self.trace.append(canonical_call(name, args, kwargs) | {"counter": self.counter})
      result = inherited(*args, **kwargs)
      delta = self.counter * 2**-40
      if isinstance(result, tuple):
        return tuple(np.asarray(item) + delta for item in result)
      return np.asarray(result) + delta

    def fast_pct_change(self, *args, **kwargs):
      return self._record("fast_pct_change", args, kwargs, base_cls.fast_pct_change)

    def stochrsi_k(self, *args, **kwargs):
      return self._record("stochrsi_k", args, kwargs, base_cls.stochrsi_k)

    def chaikin_money_flow(self, *args, **kwargs):
      return self._record("chaikin_money_flow", args, kwargs, base_cls.chaikin_money_flow)

    def calc_kst(self, *args, **kwargs):
      return self._record("calc_kst", args, kwargs, base_cls.calc_kst)

  def execute():
    strategy = make_strategy(Stateful)
    strategy.trace = []
    strategy.counter = 0
    strategy.dp = FakeDP(normal_frame())
    frame = getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, profile)
    return strategy.trace, frame

  trace_a, frame_a = execute()
  trace_b, frame_b = execute()
  assert [entry["name"] for entry in trace_a] == EXPECTED_HELPER_ORDER[profile]
  assert json.dumps(trace_a, sort_keys=True) == json.dumps(trace_b, sort_keys=True)
  assert_frame_equal(frame_a, frame_b, check_exact=True)


@pytest.mark.parametrize("profile", PROFILES)
def test_pure_ta_call_multiset_fingerprint(feature_module, monkeypatch, profile):
  calls = []
  for name in sorted(set().union(*[set(counts) for counts in EXPECTED_TA_COUNTS.values()])):
    original = getattr(feature_module.ta, name)

    def wrapper(*args, __name=name, __original=original, **kwargs):
      calls.append(canonical_call(__name, args, kwargs))
      return __original(*args, **kwargs)

    monkeypatch.setattr(feature_module.ta, name, wrapper)
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  strategy.dp = FakeDP(normal_frame())
  getattr(strategy, WRAPPERS[profile])({"pair": "TEST/USDT"}, profile)
  assert Counter(call["name"] for call in calls) == Counter(EXPECTED_TA_COUNTS[profile])
  assert all(call["args"] or call["kwargs"] for call in calls)


def test_callable_fingerprints_are_canonical_across_isolated_imports():
  first = load_strategy_module(BASELINE_SOURCE, "nfix7_callable_a")
  second = load_strategy_module(BASELINE_SOURCE, "nfix7_callable_b")
  pairs = [
    ("stochrsi_k", 1, (first.ta.MIN, first.ta.MAX, first.ta.SMA), (second.ta.MIN, second.ta.MAX, second.ta.SMA)),
    ("calc_kst", 1, (first.ta.ROC, first.ta.SMA), (second.ta.ROC, second.ta.SMA)),
  ]
  for call, start, values, other in pairs:
    assert [value_fingerprint(call, i + start, value) for i, value in enumerate(values)] == [
      value_fingerprint(call, i + start, value) for i, value in enumerate(other)
    ]


@pytest.mark.parametrize("wrapper", WRAPPERS.values())
def test_wrapper_ast_signatures_match_baseline(wrapper):
  assert signature_dump(ast_method(FEATURE_SOURCE, wrapper)) == signature_dump(ast_method(BASELINE_SOURCE, wrapper))


def test_fixture_matrix_is_exact():
  fixtures = fixture_matrix()
  assert list(fixtures) == [
    "normal_512",
    "empty",
    "short_1",
    "short_13",
    "short_199",
    "zero_open",
    "nan_ohlcv",
    "passthrough",
    "duplicate_indicator",
    "non_default_index",
  ]
  assert all(
    all(dtype == np.dtype("float64") for dtype in frame[SOURCE_COLUMNS].dtypes) for frame in fixtures.values()
  )
  assert fixtures["zero_open"].index[fixtures["zero_open"]["open"] == 0].tolist() == [
    fixtures["zero_open"].index[i] for i in (0, 256, 511)
  ]
  assert {column: np.flatnonzero(fixtures["nan_ohlcv"][column].isna()).tolist() for column in SOURCE_COLUMNS} == {
    "open": [3],
    "high": [17],
    "low": [63],
    "close": [255],
    "volume": [400],
  }


# Exactly these two tests are the Phase-2 strict RED tracer bullets.
def test_new_public_supported_profile(feature_module):
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  strategy.dp = FakeDP(normal_frame(13))
  result = strategy.informative_indicators({"pair": "TEST/USDT"}, "1d")
  assert list(result.columns) == SOURCE_COLUMNS + EXPECTED_GENERATED_COLUMNS["1d"]
  assert strategy.dp.calls == [{"pair": "TEST/USDT", "timeframe": "1d"}]

  strategy.dp = None
  with pytest.raises(AssertionError, match=f"^{DP_ASSERTION}$"):
    strategy.informative_indicators({}, "1d")

  strategy.dp = FakeDP(normal_frame(1))
  with pytest.raises(KeyError) as error:
    strategy.informative_indicators({}, "1d")
  assert error.value.args == ("pair",)
  assert strategy.dp.calls == []

  with pytest.raises(RuntimeError, match="^invalid-private not supported as informative profile\\.$"):
    feature_module.NostalgiaForInfinityX7._nfix7_informative_indicators_impl(
      strategy, {}, loaded_timeframe="custom-sentinel", profile="invalid-private"
    )


def test_new_public_invalid_profile_precedes_dp_and_metadata(feature_module):
  strategy = make_strategy(feature_module.NostalgiaForInfinityX7)
  with pytest.raises(RuntimeError, match="^invalid-profile not supported as informative profile\\.$"):
    strategy.informative_indicators({}, "invalid-profile")
