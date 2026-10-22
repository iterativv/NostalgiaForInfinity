from pathlib import Path
import re

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"
SRC = STRATEGY.read_text()

CHAINS = [
  "((stochrsi_k_15m_gt_30) | (aroonu_14_1h_lt_25) | (stochrsi_k_1d_lt_60))",
  "((rsi_3_gt_10) | (aroonu_14_15m_gt_40) | (aroonu_14_1d_lt_80))",
  "((stochrsi_k_1h_lt_50) | (aroonu_14_4h_lt_60) | (aroonu_14_1d_lt_30))",
  "((stochrsi_k_15m_lt_40) | (aroonu_14_4h_lt_80) | (aroonu_14_1d_gt_10))",
  "((rsi_3_15m_gt_5) | (aroonu_14_15m_gt_10) | (aroonu_14_4h_lt_40))",
  "((stochrsi_k_15m_lt_70) | (aroonu_14_4h_gt_10) | (stochrsi_k_4h_gt_20))",
  "((aroonu_14_15m_lt_20) | (rsi_3_1h_gt_20) | (stochrsi_k_1h_lt_60))",
]
PALETTE = ("rsi_3", "aroonu_14", "stochrsi_k", "roc_9")
TF_ORDER = {"": 0, "_15m": 1, "_1h": 2, "_4h": 3, "_1d": 4}
FAM_ORDER = {name: i for i, name in enumerate(PALETTE)}


def _chain_lines():
  lines = SRC.splitlines()
  start = next(i for i, line in enumerate(lines) if "Per-loss chains" in line)
  out = []
  for line in lines[start + 1 :]:
    text = line.strip()
    if text.startswith("& (("):
      out.append(text[2:])
    elif text.startswith("#") or not text:
      continue
    elif out:
      break
  return out


def _clauses(line):
  return re.findall(r"\(([a-z0-9_]+)\)", line)


def _family(name):
  return next(f for f in PALETTE if name.startswith(f))


def _rank(name):
  family = _family(name)
  rest = name[len(family) :]
  tf = next((t for t in ("_15m", "_1h", "_4h", "_1d") if rest.startswith(t)), "")
  return TF_ORDER[tf], FAM_ORDER[family]


def test_seven_per_loss_chains_are_present():
  assert _chain_lines() == CHAINS


def test_chains_are_three_palette_booleans_each():
  for line in _chain_lines():
    names = _clauses(line)
    assert len(names) == 3, line
    for name in names:
      assert name.startswith(PALETTE), name


def test_chains_have_no_raw_comparison():
  for line in _chain_lines():
    assert not re.search(r"[<>]\s*-?\d", line), line


def test_chain_clauses_are_ordered_low_to_high_timeframe():
  for line in _chain_lines():
    ranks = [_rank(name) for name in _clauses(line)]
    assert ranks == sorted(ranks), line


def test_palette_booleans_are_defined_in_the_file():
  used = {name for line in _chain_lines() for name in _clauses(line)}
  assert len(used) == 21
  for name in used:
    assert re.search(r"^\s+" + name + r" = ", SRC, re.MULTILINE), name


def test_signal_logic_is_untouched():
  assert "vol_rel > 3.0" in SRC
  lines = SRC.splitlines()
  logic = next(i for i, line in enumerate(lines) if line.strip() == "# Logic" and i > 32000)
  body = "\n".join(lines[logic : logic + 20])
  for cached in ("rsi_3", "stochrsi_k", "aroonu_14"):
    assert cached not in body


def test_signal_is_disabled_by_default():
  assert '"short_entry_condition_669_enable": False' in SRC
