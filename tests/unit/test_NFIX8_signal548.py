"""Guards for the 548 market-order-bubble short signal (per-loss protection chains)."""

import ast
import re
from pathlib import Path

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"

CHAINS = [
  "((aroonu_14_15m_gt_10) | (aroonu_14_1h_lt_70) | (stochrsi_k_4h_lt_70))",
  "((aroonu_14_1h_lt_70) | (stochrsi_k_1h_gt_50) | (stochrsi_k_4h_gt_60))",
  "((aroonu_14_15m_lt_70) | (stochrsi_k_15m_gt_60) | (rsi_3_1d_gt_5))",
  "((rsi_3_1h_lt_85) | (stochrsi_k_4h_gt_40) | (aroonu_14_1d_gt_10))",
  "((stochrsi_k_15m_lt_60) | (rsi_3_1h_gt_40) | (rsi_3_4h_lt_60))",
  "((rsi_3_15m_lt_70) | (rsi_3_1h_lt_80) | (aroonu_14_1h_lt_30))",
  "((rsi_3_1h_lt_70) | (stochrsi_k_4h_lt_80) | (rsi_3_1d_gt_15))",
]

CLAUSE = re.compile(r"\(([a-z0-9_]+_(?:gt|lt)_[a-z0-9_]+)\)")
TF_RANK = {"": 0, "_15m": 1, "_1h": 2, "_4h": 3, "_1d": 4}


def _block_source() -> str:
  src = STRATEGY.read_text()
  start = src.index("# Condition #548 - Market-order bubble")
  end = src.index("# Condition #561 - Downtrend Pullback", start)
  return src[start:end]


def _clauses(chain: str) -> list[str]:
  return CLAUSE.findall(chain)


def _timeframe(name: str) -> int:
  for suffix in ("_15m", "_1h", "_4h", "_1d"):
    if name.split("_gt_")[0].split("_lt_")[0].endswith(suffix):
      return TF_RANK[suffix]
  return TF_RANK[""]


def test_protection_chains_are_present():
  protections = _block_source().split("# Logic")[0]
  for chain in CHAINS:
    assert chain in protections, chain


def test_chains_are_written_in_cached_booleans_only():
  protections = _block_source().split("# Logic")[0]
  for chain in CHAINS:
    assert re.search(r"[<>]=?\s*-?\d", chain) is None, chain
    for clause in _clauses(chain):
      assert clause.split("_gt_")[0].split("_lt_")[0].rsplit("_", 1)[0] in {
        "rsi_3",
        "aroonu_14",
        "stochrsi_k",
        "roc_9",
      } or clause.split("_gt_")[0].split("_lt_")[0].startswith(("rsi_3", "aroonu_14", "stochrsi_k", "roc_9")), clause
  assert "np_view(" not in protections


def test_chain_clauses_are_ordered_low_to_high_timeframe():
  for chain in CHAINS:
    ranks = [_timeframe(name) for name in _clauses(chain)]
    assert ranks == sorted(ranks), (chain, ranks)


def test_palette_booleans_are_defined_in_the_file():
  src = STRATEGY.read_text()
  names = {name for chain in CHAINS for name in _clauses(chain)}
  assert len(names) == 20
  for name in names:
    assert re.search(rf"^\s+{name} = ", src, re.M), name


def test_signal_logic_is_untouched():
  logic = _block_source().split("# Logic")[1]
  for clause in (
    "(stochrsi_k_1d < 50.0)",
    "(stochrsi_k_1h < 80.0)",
    "(aroonu_14_4h < 50.0)",
    "(aroonu_14_1d < 50.0)",
    "(ema_50_15m < ema_200_15m)",
    "(close >= (ema_50_15m * 0.998))",
    "(close < ema_200_15m)",
    "(volume > large_bubble_thr)",
    "(cvd_sell_vol > cvd_buy_vol)",
  ):
    assert clause in logic, clause
  assert "rsi_3_1d_gt_5" not in logic


def test_signal_is_disabled_by_default():
  src = STRATEGY.read_text()
  assert '"short_entry_condition_548_enable": False' in src


def test_populate_entry_trend_extracts_the_palette():
  tree = ast.parse(STRATEGY.read_text())
  populate = next(
    node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "populate_entry_trend"
  )
  assigned = {
    target.id
    for node in ast.walk(populate)
    if isinstance(node, ast.Assign)
    for target in node.targets
    if isinstance(target, ast.Name)
  }
  for name in ("rsi_3", "rsi_3_15m", "rsi_3_1h", "rsi_3_4h", "rsi_3_1d", "aroonu_14", "stochrsi_k_4h"):
    assert name in assigned, name
