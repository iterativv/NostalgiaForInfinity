"""Guards for the 507 daily downtrend continuation short: protection chains, trigger and the 1d columns it reads."""

import re
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from NostalgiaForInfinityX8 import NostalgiaForInfinityX8

STRATEGY = Path(__file__).resolve().parents[2] / "NostalgiaForInfinityX8.py"

# chain -> the house comment that names the scene it blocks (the case where every clause is false)
CHAINS = {
  "(rsi_3_lt_90) | (aroonu_14_15m_lt_25) | (roc_9_4h_gt_neg_10)": "5m overbought, 15m uptrend, 4h down 10%+",
  "(stochrsi_k_gt_80) | (rsi_3_15m_lt_50) | (aroonu_14_1d_lt_100)": "5m not high, 15m up move, 1d fresh high",
  "(rsi_3_15m_lt_55) | (rsi_3_1h_gt_40) | (aroonu_14_1d_lt_100)": "15m up move, 1h low, 1d fresh high",
  "(rsi_3_15m_lt_80) | (aroonu_14_1h_lt_20) | (roc_9_4h_gt_neg_10)": "15m overbought, 1h uptrend, 4h down 10%+",
  "(aroonu_14_15m_lt_50) | (rsi_3_4h_gt_30) | (aroonu_14_1d_lt_100)": "15m uptrend, 4h low, 1d fresh high",
  "(aroonu_14_15m_lt_30) | (aroonu_14_4h_lt_30) | (rsi_3_1d_gt_20)": "15m uptrend, 4h uptrend, 1d low",
  "(aroonu_14_15m_gt_20) | (aroonu_14_4h_gt_0) | (aroonu_14_1d_gt_0)": "15m downtrend, 4h no new high, 1d no new high",
  "(stochrsi_k_15m_gt_80) | (aroonu_14_1h_gt_0) | (aroonu_14_1d_lt_100)": "15m not high, 1h no new high, 1d fresh high",
  # one loss each, no winner cut
  "(rsi_3_15m_gt_20) | (stochrsi_k_4h_lt_60) | (aroonu_14_1d_lt_80)": "15m low, 4h high, 1d fresh high",
  "(aroonu_14_15m_gt_0) | (stochrsi_k_1h_lt_70) | (aroonu_14_1d_gt_0)": "15m no new high, 1h high, 1d no new high",
  "(rsi_3_15m_gt_35) | (cmf_20_15m_lt_0_10) | (top_wick_pct_1d_lt_15)": "15m low, 15m inflow, 1d top wick 15%+",
  "(rsi_3_15m_gt_3) | (aroonu_14_1h_gt_0) | (aroonu_14_1d_lt_60)": "15m oversold, 1h no new high, 1d uptrend",
  "(stochrsi_k_15m_gt_70) | (rsi_3_1h_lt_55) | (aroonu_14_4h_lt_60)": "15m not high, 1h up move, 4h uptrend",
  "(aroonu_14_15m_gt_20) | (stochrsi_k_1h_lt_30) | (roc_9_4h_lt_5)": "15m downtrend, 1h not low, 4h up 5%+",
  "(rsi_3_15m_gt_3) | (rsi_3_1d_gt_20) | (aroonu_14_1d_gt_0)": "15m oversold, 1d low, 1d no new high",
  "(aroonu_14_gt_75) | (rsi_14_15m_lt_50) | (cmf_20_4h_gt_neg_0_25)": "5m not high, 15m up bias, 4h outflow",
  "(stochrsi_k_1h_gt_10) | (stochrsi_k_4h_gt_10) | (top_wick_pct_1d_lt_8)": "1h low, 4h low, 1d top wick 8%+",
  "(rsi_3_15m_gt_55) | (rsi_14_15m_lt_35) | (rsi_3_1h_gt_3)": "15m down move, 15m not oversold, 1h oversold",
  "(stochrsi_k_1h_lt_50) | (aroonu_14_4h_lt_40) | (rsi_3_1d_gt_10)": "1h not low, 4h uptrend, 1d oversold",
  "(rsi_3_gt_3) | (rsi_3_1h_gt_15) | (cmf_20_1d_gt_neg_0_10)": "5m oversold, 1h oversold, 1d outflow",
  "(cmf_20_4h_gt_neg_0_20) | (aroonu_14_4h_lt_50) | (aroonu_14_1d_lt_70)": "4h outflow, 4h uptrend, 1d uptrend",
  "(cmf_20_15m_gt_neg_0_20) | (rsi_3_4h_gt_3) | (aroonu_14_4h_gt_0)": "15m outflow, 4h oversold, 4h no new high",
  "(cmf_20_1h_gt_neg_0_20) | (stochrsi_k_4h_lt_50) | (rsi_3_1d_gt_15)": "1h outflow, 4h not low, 1d oversold",
  "(cmf_20_15m_lt_0_10) | (rsi_3_1h_gt_20) | (cmf_20_1d_gt_neg_0_20)": "15m inflow, 1h low, 1d outflow",
  "(stochrsi_k_15m_gt_10) | (cmf_20_4h_lt_0_15) | (rsi_3_1d_gt_30)": "15m low, 4h inflow, 1d low",
  "(aroonu_14_15m_lt_80) | (stochrsi_k_15m_gt_80) | (stochrsi_k_1h_gt_10)": "15m fresh high, 15m not high, 1h low",
  "(rsi_3_15m_gt_45) | (aroonu_14_15m_lt_70) | (rsi_3_4h_gt_3)": "15m down move, 15m uptrend, 4h oversold",
  "(rsi_3_gt_15) | (cmf_20_15m_gt_neg_0_35) | (stochrsi_k_15m_lt_30)": "5m oversold, 15m heavy outflow, 15m not low",
  "(rsi_3_lt_40) | (stochrsi_k_15m_gt_10) | (rsi_14_1h_gt_20)": "5m up move, 15m low, 1h deeply oversold",
  "(rsi_3_15m_lt_75) | (stochrsi_k_1h_gt_30) | (rsi_3_1d_gt_10)": "15m overbought, 1h low, 1d oversold",
  "(rsi_3_1h_lt_55) | (aroonu_14_1h_lt_60) | (cci_20_change_pct_4h_lt_0)": "1h up move, 1h uptrend, 4h CCI rising",
  "(rsi_3_15m_gt_10) | (rsi_3_4h_gt_20) | (cmf_20_4h_lt_0_15)": "15m oversold, 4h low, 4h inflow",
  "(rsi_3_1h_gt_30) | (cmf_20_4h_lt_0_15) | (roc_9_4h_gt_neg_10)": "1h low, 4h inflow, 4h down 10%+",
  "(rsi_3_15m_gt_35) | (cmf_20_15m_lt_0_30) | (aroonu_14_4h_lt_20)": "15m low, 15m strong inflow, 4h uptrend",
  "(stochrsi_k_1h_gt_10) | (cmf_20_4h_lt_0_15) | (aroonu_14_4h_gt_20)": "1h low, 4h inflow, 4h downtrend",
  "(aroond_14_4h_lt_80) | (stochrsi_k_4h_lt_60) | (roc_9_1d_gt_neg_25)": "4h fresh low, 4h high, 1d down 25%+",
  "(aroonu_14_1h_gt_0) | (stochrsi_k_4h_lt_70) | (stochrsi_k_1d_lt_20)": "1h no new high, 4h high, 1d not low",
  "(cmf_20_15m_gt_neg_0_10) | (aroonu_14_15m_gt_20) | (rsi_14_4h_gt_20)": "15m outflow, 15m downtrend, 4h deeply oversold",
  "(rsi_3_15m_gt_30) | (cmf_20_15m_lt_0_10) | (roc_9_1d_lt_15)": "15m low, 15m inflow, 1d up 15%+",
  "(aroonu_14_1h_lt_40) | (rsi_3_4h_gt_25) | (top_wick_pct_1d_lt_10)": "1h uptrend, 4h low, 1d top wick 10%+",
  "(rsi_3_1h_gt_10) | (aroonu_14_1h_gt_0) | (roc_9_4h_lt_5)": "1h oversold, 1h no new high, 4h up 5%+",
  "(aroond_14_gt_75) | (rsi_3_1h_gt_3) | (aroonu_14_1d_lt_80)": "5m no fresh low, 1h oversold, 1d fresh high",
  "(rsi_3_gt_15) | (rsi_3_4h_gt_10) | (roc_9_1d_lt_10)": "5m oversold, 4h oversold, 1d up 10%+",
  "(aroonu_14_4h_lt_70) | (rsi_3_change_pct_1d_gt_neg_20) | (stochrsi_k_1d_lt_90)": "4h uptrend, 1d RSI down 20%+, 1d overbought",
  "(rsi_3_15m_gt_35) | (stochrsi_k_15m_lt_80) | (rsi_3_1h_lt_50)": "15m low, 15m overbought, 1h up move",
  "(rsi_3_15m_lt_85) | (rsi_3_1h_gt_60) | (stochrsi_k_1h_lt_90)": "15m overbought, 1h down move, 1h overbought",
  "(rsi_14_15m_lt_30) | (cmf_20_15m_gt_neg_0_35) | (aroonu_14_1h_gt_0)": "15m not oversold, 15m heavy outflow, 1h no new high",
  "(rsi_3_15m_gt_55) | (cmf_20_15m_lt_0_10) | (top_wick_pct_1d_lt_15)": "15m down move, 15m inflow, 1d top wick 15%+",
  "(stochrsi_k_1h_lt_60) | (rsi_3_4h_gt_30) | (stochrsi_k_4h_lt_50)": "1h high, 4h low, 4h not low",
  "(cmf_20_15m_gt_neg_0_10) | (aroonu_14_15m_lt_80) | (aroonu_14_1h_lt_60)": "15m outflow, 15m fresh high, 1h uptrend",
  "(rsi_3_lt_40) | (rsi_3_15m_gt_50) | (cmf_20_15m_lt_0_30)": "5m up move, 15m down move, 15m strong inflow",
  "(rsi_3_15m_lt_80) | (cmf_20_4h_lt_0_15) | (rsi_3_1d_gt_25)": "15m overbought, 4h inflow, 1d low",
  "(rsi_14_15m_lt_50) | (cmf_20_1h_gt_neg_0_25) | (rsi_3_1d_gt_10)": "15m up bias, 1h outflow, 1d oversold",
  "(rsi_3_15m_gt_35) | (rsi_14_15m_lt_50) | (rsi_3_4h_gt_55)": "15m low, 15m up bias, 4h down move",
  "(aroonu_14_1h_lt_25) | (cmf_20_4h_lt_0_15) | (stochrsi_k_4h_gt_10)": "1h uptrend, 4h inflow, 4h low",
  "(rsi_3_gt_15) | (rsi_3_4h_gt_50) | (roc_9_1d_lt_20)": "5m oversold, 4h down move, 1d up 20%+",
  "(aroonu_14_15m_gt_0) | (stochrsi_k_4h_lt_60) | (aroonu_14_1d_lt_80)": "15m no new high, 4h high, 1d fresh high",
  "(rsi_3_15m_gt_20) | (rsi_3_4h_gt_10) | (roc_9_1d_lt_10)": "15m low, 4h oversold, 1d up 10%+",
  # each blocks a whole move (entry and re-entries), no winner cut, 3 to 5 clauses
  "(stochrsi_k_15m_lt_20) | (stochrsi_k_1h_gt_40) | (cmf_20_4h_lt_0_15) | (aroonu_14_4h_gt_30) | (aroonu_14_1d_gt_30)": "15m not low, 1h not high, 4h inflow, 4h & 1d downtrend",
  "(stochrsi_k_15m_lt_30) | (aroonu_14_1h_gt_40) | (aroonu_14_4h_lt_75) | (stochrsi_k_4h_lt_60) | (cmf_20_1d_lt_0_10)": "15m not low, 1h not high, 4h uptrend, 4h high, 1d inflow",
  "(rsi_3_15m_lt_85) | (aroonu_14_1h_gt_20) | (aroond_14_4h_lt_80) | (stochrsi_k_4h_lt_60)": "15m overbought, 1h downtrend, 4h fresh low, 4h high",
  "(aroonu_14_4h_gt_30) | (stochrsi_k_4h_lt_50) | (stochrsi_k_1d_lt_90)": "4h downtrend, 4h not low, 1d overbought",
  "(aroonu_14_1h_lt_60) | (stochrsi_k_1h_gt_10) | (rsi_3_4h_lt_40) | (rsi_3_change_pct_1d_gt_neg_20) | (aroonu_14_1d_gt_0)": "1h uptrend, 1h low, 4h up move, 1d RSI down 20%+, 1d no new high",
  "(cmf_20_4h_gt_neg_0_20) | (stochrsi_k_4h_lt_50) | (rsi_3_1d_gt_25) | (stochrsi_k_1d_lt_50)": "4h outflow, 4h & 1d not low, 1d low",
  "(aroonu_14_1h_lt_20) | (rsi_3_4h_gt_15) | (aroonu_14_4h_lt_40) | (rsi_3_1d_gt_20) | (stochrsi_k_1d_lt_30)": "1h & 4h uptrend, 4h oversold, 1d low, 1d not low",
  "(rsi_3_15m_lt_50) | (rsi_3_1h_gt_45) | (top_wick_pct_1d_lt_15)": "15m up move, 1h down move, 1d top wick 15%+",
  "(aroonu_14_1h_lt_60) | (cci_20_change_pct_1h_lt_0) | (rsi_3_1d_gt_15) | (aroonu_14_1d_gt_0)": "1h uptrend, 1h CCI rising, 1d oversold, 1d no new high",
  "(cmf_20_4h_gt_neg_0_0) | (stochrsi_k_4h_lt_40) | (cmf_20_1d_lt_0_10) | (aroonu_14_1d_lt_40) | (stochrsi_k_1d_gt_10)": "4h outflow, 4h not low, 1d inflow, 1d uptrend, 1d low",
  "(aroond_14_lt_25) | (aroonu_14_1h_lt_50) | (stochrsi_k_1h_lt_70) | (cmf_20_4h_gt_neg_0_10) | (cmf_20_1d_gt_neg_0_0)": "5m fresh low, 1h uptrend, 1h high, 4h & 1d outflow",
  "(aroond_14_15m_lt_70) | (aroonu_14_1h_lt_20) | (stochrsi_k_1h_lt_70) | (aroonu_14_4h_lt_30) | (aroonu_14_1d_gt_0)": "15m fresh low, 1h & 4h uptrend, 1h high, 1d no new high",
  "(rsi_3_15m_lt_50) | (aroonu_14_15m_gt_50) | (rsi_3_1d_gt_30) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_lt_60)": "15m up move, 15m not high, 1d low, 1d inflow, 1d high",
  "(aroond_14_15m_lt_25) | (rsi_3_4h_gt_30) | (stochrsi_k_4h_lt_70) | (stochrsi_k_1d_lt_60)": "15m fresh low, 4h low, 4h & 1d high",
  "(rsi_3_15m_lt_75) | (aroonu_14_15m_gt_40) | (cmf_20_1h_lt_0_10) | (cci_20_change_pct_1h_lt_0)": "15m overbought, 15m not high, 1h inflow, 1h CCI rising",
  "(rsi_3_1h_gt_35) | (aroonu_14_1h_lt_20) | (stochrsi_k_1h_lt_60) | (rsi_3_4h_gt_3)": "1h low, 1h uptrend, 1h high, 4h oversold",
  "(aroonu_14_4h_lt_70) | (stochrsi_k_4h_lt_20) | (cci_20_change_pct_4h_lt_0) | (rsi_3_1d_gt_60) | (stochrsi_k_1d_lt_60)": "4h uptrend, 4h not low, 4h CCI rising, 1d down move, 1d high",
  "(stochrsi_k_15m_lt_60) | (rsi_3_1h_gt_55) | (cmf_20_1h_lt_0_10) | (rsi_3_4h_gt_40) | (aroonu_14_4h_lt_80)": "15m high, 1h & 4h down move, 1h inflow, 4h fresh high",
  "(rsi_3_1h_lt_40) | (rsi_3_4h_gt_35) | (stochrsi_k_4h_lt_40) | (rsi_3_1d_gt_50) | (stochrsi_k_1d_lt_60)": "1h up move, 4h low, 4h not low, 1d down move, 1d high",
  "(cmf_20_1h_gt_neg_0_20) | (stochrsi_k_1h_gt_10) | (aroonu_14_4h_gt_20) | (aroonu_14_1d_lt_80)": "1h outflow, 1h low, 4h downtrend, 1d fresh high",
  "(rsi_3_1h_gt_20) | (aroonu_14_1h_gt_0) | (aroonu_14_4h_lt_70) | (aroond_14_4h_lt_70) | (stochrsi_k_4h_lt_40)": "1h low, 1h no new high, 4h uptrend, 4h fresh low, 4h not low",
  "(rsi_3_15m_lt_75) | (aroonu_14_15m_gt_0) | (aroond_14_15m_lt_25) | (stochrsi_k_1h_lt_70)": "15m overbought, 15m no new high, 15m fresh low, 1h high",
  "(aroonu_14_1h_lt_30) | (aroonu_14_4h_lt_40) | (rsi_3_1d_gt_25) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_lt_30)": "1h & 4h uptrend, 1d low, 1d no new high, 1d not low",
  "(rsi_3_15m_gt_35) | (aroonu_14_15m_gt_0) | (aroonu_14_1h_gt_0) | (aroonu_14_4h_gt_0) | (aroonu_14_1d_lt_80)": "15m low, 15m & 1h & 4h no new high, 1d fresh high",
  "(rsi_3_1h_lt_50) | (cmf_20_4h_lt_0_15) | (stochrsi_k_4h_gt_10) | (aroonu_14_1d_gt_0)": "1h up move, 4h inflow, 4h low, 1d no new high",
  "(rsi_14_15m_lt_40) | (aroond_14_4h_lt_70) | (stochrsi_k_4h_lt_30) | (aroonu_14_1d_lt_80)": "15m up bias, 4h fresh low, 4h not low, 1d fresh high",
  "(stochrsi_k_1h_lt_90) | (rsi_3_4h_gt_45) | (aroond_14_4h_lt_70) | (roc_9_1d_gt_neg_20)": "1h overbought, 4h down move, 4h fresh low, 1d down 20%+",
  "(rsi_3_15m_lt_70) | (rsi_3_1h_lt_70) | (cmf_20_1d_gt_neg_0_0) | (aroonu_14_1d_lt_40) | (stochrsi_k_1d_gt_10)": "15m & 1h overbought, 1d outflow, 1d uptrend, 1d low",
  "(aroonu_14_lt_30) | (aroonu_14_1h_lt_60) | (roc_9_4h_gt_neg_10) | (roc_9_1d_gt_neg_20)": "5m & 1h uptrend, 4h down 10%+, 1d down 20%+",
  "(rsi_3_15m_lt_50) | (cmf_20_1h_gt_neg_0_20) | (stochrsi_k_1h_lt_50) | (aroonu_14_4h_lt_30) | (aroonu_14_1d_lt_30)": "15m up move, 1h outflow, 1h not low, 4h & 1d uptrend",
  "(stochrsi_k_15m_lt_20) | (rsi_3_4h_gt_30) | (aroonu_14_4h_lt_80) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_lt_90)": "15m not low, 4h low, 4h fresh high, 1d inflow, 1d overbought",
  "(cmf_20_1h_gt_neg_0_20) | (cmf_20_4h_lt_0_15) | (aroonu_14_4h_lt_30)": "1h outflow, 4h inflow, 4h uptrend",
  "(cmf_20_15m_gt_neg_0_10) | (cmf_20_1h_gt_neg_0_20) | (aroonu_14_1h_gt_30) | (rsi_3_1d_gt_10) | (aroonu_14_1d_lt_20)": "15m & 1h outflow, 1h downtrend, 1d oversold, 1d uptrend",
  "(aroond_14_15m_lt_80) | (stochrsi_k_15m_lt_20) | (rsi_3_4h_gt_15) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_lt_70)": "15m fresh low, 15m not low, 4h oversold, 1d inflow, 1d high",
  "(aroonu_14_15m_lt_60) | (aroonu_14_1h_lt_30) | (aroond_14_4h_lt_80) | (roc_9_4h_gt_neg_10) | (aroonu_14_1d_gt_0)": "15m & 1h uptrend, 4h fresh low, 4h down 10%+, 1d no new high",
  "(stochrsi_k_15m_lt_80) | (aroonu_14_4h_lt_60) | (rsi_3_1d_gt_40) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_lt_70)": "15m overbought, 4h uptrend, 1d down move, 1d no new high, 1d high",
  "(rsi_3_15m_gt_40) | (stochrsi_k_1h_lt_70) | (rsi_3_4h_gt_15) | (aroonu_14_4h_gt_0) | (stochrsi_k_1d_gt_10)": "15m down move, 1h high, 4h oversold, 4h no new high, 1d low",
  "(rsi_3_1h_gt_50) | (rsi_3_4h_gt_20) | (rsi_3_1d_gt_60) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_lt_90)": "1h & 1d down move, 4h low, 1d inflow, 1d overbought",
  "(aroonu_14_4h_lt_20) | (stochrsi_k_4h_lt_30) | (rsi_3_1d_gt_50) | (cmf_20_1d_gt_neg_0_10) | (aroonu_14_1d_lt_75)": "4h & 1d uptrend, 4h not low, 1d down move, 1d outflow",
  "(stochrsi_k_15m_lt_80) | (cmf_20_1h_gt_neg_0_25) | (aroonu_14_1h_gt_30) | (cmf_20_4h_gt_neg_0_25)": "15m overbought, 1h & 4h outflow, 1h downtrend",
  "(rsi_3_15m_lt_70) | (rsi_14_15m_lt_50) | (cmf_20_15m_gt_neg_0_10) | (rsi_3_1d_gt_25) | (aroonu_14_1d_gt_0)": "15m overbought, 15m up bias, 15m outflow, 1d low, 1d no new high",
  "(aroonu_14_15m_gt_10) | (cmf_20_1h_gt_neg_0_10) | (aroonu_14_1h_lt_30) | (aroonu_14_4h_lt_30) | (cmf_20_1d_gt_neg_0_25)": "15m downtrend, 1h & 1d outflow, 1h & 4h uptrend",
  "(cmf_20_1h_gt_neg_0_10) | (cci_20_change_pct_1h_lt_0) | (stochrsi_k_4h_lt_30) | (rsi_14_1d_gt_45) | (aroonu_14_1d_lt_75)": "1h outflow, 1h CCI rising, 4h not low, 1d deeply oversold, 1d uptrend",
  "(aroonu_14_1h_lt_60) | (stochrsi_k_1h_lt_70) | (rsi_3_4h_gt_35) | (rsi_3_1d_gt_15) | (stochrsi_k_1d_gt_10)": "1h uptrend, 1h high, 4h & 1d low, 1d oversold",
  "(aroonu_14_15m_gt_40) | (stochrsi_k_15m_lt_80) | (stochrsi_k_1h_lt_50) | (cmf_20_4h_gt_neg_0_20) | (aroonu_14_1d_lt_30)": "15m not high, 15m overbought, 1h not low, 4h outflow, 1d uptrend",
  "(rsi_3_15m_lt_75) | (cmf_20_15m_gt_neg_0_20) | (rsi_3_1h_gt_45) | (aroonu_14_4h_lt_80)": "15m overbought, 15m outflow, 1h down move, 4h fresh high",
  "(aroonu_14_15m_lt_50) | (stochrsi_k_4h_lt_70) | (rsi_3_1d_gt_25) | (aroonu_14_1d_lt_40) | (stochrsi_k_1d_lt_20)": "15m & 1d uptrend, 4h high, 1d low, 1d not low",
  "(rsi_3_15m_lt_60) | (stochrsi_k_15m_lt_80) | (stochrsi_k_1h_gt_10) | (rsi_3_change_pct_1d_gt_neg_20) | (cmf_20_1d_lt_0_10)": "15m up move, 15m overbought, 1h low, 1d RSI down 20%+, 1d inflow",
  "(rsi_3_1h_lt_60) | (aroonu_14_1h_lt_20) | (rsi_3_4h_gt_35) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_gt_40)": "1h up move, 1h uptrend, 4h low, 1d no new high, 1d not high",
  "(cmf_20_15m_lt_0_10) | (stochrsi_k_1h_lt_70) | (cci_20_change_pct_1h_lt_0) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_gt_30)": "15m inflow, 1h high, 1h CCI rising, 1d no new high, 1d low",
  "(aroonu_14_1h_lt_40) | (stochrsi_k_1h_lt_20) | (aroonu_14_4h_lt_40) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_gt_10)": "1h & 4h uptrend, 1h not low, 1d inflow, 1d low",
  "(rsi_3_15m_lt_75) | (rsi_3_1h_gt_40) | (cci_20_change_pct_1h_lt_0) | (roc_9_4h_gt_neg_10)": "15m overbought, 1h low, 1h CCI rising, 4h down 10%+",
  "(stochrsi_k_15m_gt_40) | (stochrsi_k_1h_lt_70) | (rsi_3_1d_gt_15) | (aroonu_14_1d_gt_0)": "15m not high, 1h high, 1d oversold, 1d no new high",
  "(aroonu_14_15m_lt_20) | (cmf_20_1h_lt_0_10) | (rsi_3_4h_gt_25) | (aroonu_14_1d_lt_70)": "15m & 1d uptrend, 1h inflow, 4h low",
  "(rsi_3_4h_gt_35) | (cmf_20_4h_lt_0_15) | (aroonu_14_4h_lt_30) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_lt_70)": "4h low, 4h inflow, 4h uptrend, 1d no new high, 1d high",
  "(rsi_14_15m_lt_35) | (rsi_3_1h_gt_45) | (stochrsi_k_1h_lt_70) | (rsi_14_1d_gt_50) | (cmf_20_1d_lt_0_10)": "15m not oversold, 1h down move, 1h high, 1d deeply oversold, 1d inflow",
  "(stochrsi_k_15m_lt_80) | (rsi_3_1d_gt_10) | (aroonu_14_1d_gt_0) | (roc_9_1d_gt_neg_15)": "15m overbought, 1d oversold, 1d no new high, 1d down 15%+",
  "(cmf_20_15m_gt_neg_0_10) | (aroonu_14_15m_lt_80) | (stochrsi_k_4h_lt_50) | (stochrsi_k_1d_lt_40)": "15m outflow, 15m fresh high, 4h & 1d not low",
  "(aroonu_14_15m_gt_30) | (aroonu_14_4h_gt_0) | (rsi_14_1d_gt_45) | (cmf_20_1d_lt_0_10) | (roc_9_1d_gt_neg_20)": "15m downtrend, 4h no new high, 1d deeply oversold, 1d inflow, 1d down 20%+",
  "(rsi_14_15m_lt_30) | (aroonu_14_4h_lt_20) | (rsi_3_1d_gt_65) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_lt_90)": "15m not oversold, 4h uptrend, 1d down move, 1d inflow, 1d overbought",
  "(cmf_20_15m_gt_neg_0_10) | (aroonu_14_15m_lt_100) | (rsi_3_1h_lt_55) | (rsi_14_4h_lt_30) | (aroonu_14_4h_gt_20)": "15m outflow, 15m fresh high, 1h up move, 4h not oversold, 4h downtrend",
  "(stochrsi_k_15m_lt_80) | (stochrsi_k_4h_lt_60) | (stochrsi_k_1d_lt_30) | (roc_9_1d_gt_neg_15)": "15m overbought, 4h high, 1d not low, 1d down 15%+",
  "(rsi_14_4h_gt_20) | (aroonu_14_4h_gt_0) | (stochrsi_k_4h_gt_30) | (cmf_20_1d_gt_neg_0_10) | (stochrsi_k_1d_gt_10)": "4h deeply oversold, 4h no new high, 4h & 1d low, 1d outflow",
  "(cmf_20_4h_gt_neg_0_20) | (stochrsi_k_4h_lt_40) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_gt_10)": "4h outflow, 4h not low, 1d inflow, 1d low",
  "(aroonu_14_1h_lt_80) | (aroonu_14_4h_lt_100) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_gt_40)": "1h & 4h fresh high, 1d no new high, 1d not high",
  "(stochrsi_k_1h_lt_50) | (rsi_3_4h_gt_20) | (aroonu_14_4h_gt_0) | (cmf_20_1d_lt_0_10)": "1h not low, 4h low, 4h no new high, 1d inflow",
  "(stochrsi_k_1h_lt_30) | (rsi_3_4h_gt_35) | (stochrsi_k_4h_lt_50) | (aroonu_14_1d_lt_40) | (stochrsi_k_1d_gt_10)": "1h & 4h not low, 4h & 1d low, 1d uptrend",
  "(aroonu_14_15m_lt_60) | (stochrsi_k_15m_gt_50) | (rsi_3_4h_gt_10) | (rsi_3_1d_gt_20) | (aroonu_14_1d_gt_0)": "15m uptrend, 15m not high, 4h oversold, 1d low, 1d no new high",
  "(rsi_3_1h_gt_45) | (rsi_3_4h_gt_10) | (roc_9_1d_lt_10)": "1h down move, 4h oversold, 1d up 10%+",
  "(stochrsi_k_15m_lt_80) | (roc_9_4h_lt_5) | (stochrsi_k_1d_gt_50) | (top_wick_pct_1d_lt_8)": "15m overbought, 4h up 5%+, 1d not high, 1d top wick 8%+",
  "(stochrsi_k_15m_lt_20) | (aroond_14_1h_lt_70) | (cmf_20_1d_gt_neg_0_20) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_lt_70)": "15m not low, 1h fresh low, 1d outflow, 1d no new high, 1d high",
  "(stochrsi_k_15m_lt_80) | (aroonu_14_1h_gt_0) | (aroond_14_1h_lt_50) | (cmf_20_1d_lt_0_10) | (aroonu_14_1d_gt_0)": "15m overbought, 1h & 1d no new high, 1h fresh low, 1d inflow",
  "(rsi_3_15m_gt_45) | (aroonu_14_1h_lt_30) | (stochrsi_k_4h_lt_50) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_lt_90)": "15m down move, 1h uptrend, 4h not low, 1d inflow, 1d overbought",
  "(aroonu_14_15m_gt_0) | (stochrsi_k_15m_lt_80) | (rsi_3_1d_gt_50) | (cmf_20_1d_lt_0_10) | (aroonu_14_1d_gt_0)": "15m & 1d no new high, 15m overbought, 1d down move, 1d inflow",
  "(cmf_20_15m_gt_neg_0_10) | (stochrsi_k_15m_lt_80) | (aroonu_14_1h_gt_0) | (rsi_3_1d_gt_15) | (aroonu_14_1d_lt_40)": "15m outflow, 15m overbought, 1h no new high, 1d oversold, 1d uptrend",
  "(stochrsi_k_1h_lt_80) | (rsi_3_4h_gt_35) | (stochrsi_k_4h_lt_20)": "1h overbought, 4h low, 4h not low",
  "(rsi_14_15m_lt_35) | (aroond_14_4h_lt_25) | (stochrsi_k_4h_lt_60) | (stochrsi_k_1d_lt_90)": "15m not oversold, 4h fresh low, 4h high, 1d overbought",
  "(rsi_3_1h_gt_40) | (aroonu_14_1h_gt_20) | (cmf_20_4h_gt_neg_0_30) | (aroonu_14_4h_gt_0) | (stochrsi_k_1d_gt_10)": "1h & 1d low, 1h downtrend, 4h heavy outflow, 4h no new high",
  "(cmf_20_15m_lt_0_10) | (aroonu_14_1h_lt_30) | (rsi_14_1d_lt_40) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_gt_10)": "15m inflow, 1h uptrend, 1d up bias, 1d no new high, 1d low",
  "(cmf_20_4h_gt_neg_0_20) | (rsi_3_1d_gt_25) | (top_wick_pct_1d_lt_8)": "4h outflow, 1d low, 1d top wick 8%+",
  "(rsi_3_1h_gt_20) | (aroonu_14_4h_lt_70) | (rsi_14_1d_gt_45) | (stochrsi_k_1d_lt_90)": "1h low, 4h uptrend, 1d deeply oversold, 1d overbought",
  "(cmf_20_1h_gt_neg_0_20) | (rsi_3_1d_gt_40) | (aroonu_14_1d_lt_100)": "1h outflow, 1d down move, 1d fresh high",
  "(aroond_14_15m_lt_25) | (stochrsi_k_1h_lt_90) | (aroonu_14_1d_lt_80)": "15m fresh low, 1h overbought, 1d fresh high",
  "(cmf_20_1h_gt_neg_0_40) | (aroonu_14_1h_lt_60) | (rsi_3_1d_gt_45)": "1h heavy outflow, 1h uptrend, 1d down move",
  "(aroonu_14_1h_lt_70) | (stochrsi_k_1h_gt_20) | (rsi_14_4h_lt_40) | (stochrsi_k_4h_lt_60) | (aroonu_14_1d_lt_60)": "1h & 1d uptrend, 1h low, 4h up bias, 4h high",
  "(rsi_3_15m_lt_75) | (stochrsi_k_1h_gt_10) | (cmf_20_4h_gt_neg_0_20) | (rsi_3_1d_gt_20)": "15m overbought, 1h & 1d low, 4h outflow",
  "(aroond_14_lt_25) | (rsi_3_1h_lt_50) | (cmf_20_1d_gt_neg_0_25) | (roc_9_1d_gt_neg_20)": "5m fresh low, 1h up move, 1d outflow, 1d down 20%+",
  "(aroonu_14_15m_gt_0) | (aroonu_14_1h_lt_30) | (rsi_3_change_pct_1d_gt_neg_20) | (aroonu_14_1d_gt_0) | (roc_9_1d_gt_neg_20)": "15m & 1d no new high, 1h uptrend, 1d RSI down 20%+, 1d down 20%+",
  "(aroonu_14_4h_lt_40) | (rsi_3_1d_gt_35) | (cmf_20_1d_gt_neg_0_25) | (change_pct_1d_gt_neg_5)": "4h uptrend, 1d low, 1d outflow, 1d red",
  "(aroond_14_15m_lt_25) | (aroonu_14_4h_lt_80) | (cmf_20_1d_gt_neg_0_25) | (stochrsi_k_1d_gt_10)": "15m fresh low, 4h fresh high, 1d outflow, 1d low",
  "(stochrsi_k_15m_lt_80) | (cmf_20_1h_gt_neg_0_25) | (rsi_3_1d_gt_45) | (aroonu_14_1d_lt_80)": "15m overbought, 1h outflow, 1d down move, 1d fresh high",
  "(stochrsi_k_4h_lt_30) | (rsi_3_1d_gt_20) | (aroonu_14_1d_lt_80)": "4h not low, 1d low, 1d fresh high",
  "(aroonu_14_15m_lt_80) | (aroonu_14_4h_lt_50) | (rsi_3_1d_gt_35) | (roc_9_1d_gt_neg_20)": "15m fresh high, 4h uptrend, 1d low, 1d down 20%+",
  "(rsi_14_15m_lt_50) | (aroond_14_1h_lt_70) | (stochrsi_k_1h_lt_70) | (roc_9_1d_gt_neg_20) | (change_pct_1d_gt_neg_10)": "15m up bias, 1h fresh low, 1h high, 1d down 20%+, 1d red",
  "(cmf_20_15m_gt_neg_0_30) | (aroonu_14_1h_gt_0) | (stochrsi_k_4h_gt_10) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_gt_50)": "15m heavy outflow, 1h & 1d no new high, 4h low, 1d not high",
  "(rsi_14_15m_lt_30) | (stochrsi_k_1h_lt_40) | (rsi_3_1d_gt_40) | (cmf_20_1d_lt_0_10) | (stochrsi_k_1d_lt_70)": "15m not oversold, 1h not low, 1d down move, 1d inflow, 1d high",
  "(cmf_20_15m_gt_neg_0_10) | (stochrsi_k_15m_lt_80) | (aroonu_14_1h_gt_0) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_lt_60)": "15m outflow, 15m overbought, 1h & 1d no new high, 1d high",
  "(aroonu_14_15m_gt_40) | (rsi_3_4h_lt_50) | (aroonu_14_4h_gt_0) | (stochrsi_k_1d_lt_40)": "15m not high, 4h up move, 4h no new high, 1d not low",
  "(aroonu_14_1h_lt_70) | (stochrsi_k_1h_gt_10) | (stochrsi_k_4h_gt_10) | (stochrsi_k_1d_lt_20)": "1h uptrend, 1h & 4h low, 1d not low",
  "(rsi_3_4h_gt_25) | (stochrsi_k_1d_lt_80) | (top_wick_pct_1d_lt_10)": "4h low, 1d overbought, 1d top wick 10%+",
  "(aroonu_14_4h_lt_100) | (rsi_3_1d_gt_60) | (stochrsi_k_1d_lt_50)": "4h fresh high, 1d down move, 1d not low",
  "(aroonu_14_1h_lt_70) | (stochrsi_k_4h_lt_50) | (rsi_3_change_pct_1d_gt_neg_20) | (cmf_20_1d_gt_neg_0_25)": "1h uptrend, 4h not low, 1d RSI down 20%+, 1d outflow",
  "(rsi_3_1h_lt_40) | (rsi_3_4h_gt_3) | (cmf_20_4h_gt_neg_0_25)": "1h up move, 4h oversold, 4h outflow",
  "(rsi_3_15m_gt_45) | (rsi_3_1h_lt_50) | (roc_9_1d_gt_neg_25)": "15m down move, 1h up move, 1d down 25%+",
  "(stochrsi_k_15m_lt_80) | (cmf_20_4h_lt_0_15) | (aroonu_14_1d_gt_0)": "15m overbought, 4h inflow, 1d no new high",
  "(rsi_3_15m_gt_50) | (stochrsi_k_1h_lt_90) | (aroonu_14_4h_lt_20)": "15m down move, 1h overbought, 4h uptrend",
  "(rsi_3_15m_lt_50) | (cmf_20_15m_gt_neg_0_30) | (roc_9_4h_gt_neg_10)": "15m up move, 15m heavy outflow, 4h down 10%+",
  "(rsi_3_lt_40) | (stochrsi_k_15m_gt_30) | (rsi_14_1h_gt_20)": "5m up move, 15m low, 1h deeply oversold",
  "(rsi_3_gt_15) | (cmf_20_15m_lt_0_10) | (aroonu_14_1h_gt_0)": "5m oversold, 15m inflow, 1h no new high",
  "(rsi_3_gt_15) | (cmf_20_15m_lt_0_10) | (cmf_20_1h_gt_neg_0_20)": "5m oversold, 15m inflow, 1h outflow",
  "(aroonu_14_15m_gt_0) | (cmf_20_4h_lt_0_15) | (rsi_3_1d_gt_30)": "15m no new high, 4h inflow, 1d low",
  "(rsi_3_15m_gt_55) | (stochrsi_k_15m_lt_80) | (stochrsi_k_1h_lt_90)": "15m down move, 15m & 1h overbought",
  "(aroonu_14_4h_lt_70) | (rsi_3_1d_gt_35) | (cmf_20_1d_lt_0_10)": "4h uptrend, 1d low, 1d inflow",
  "(aroonu_14_15m_lt_100) | (stochrsi_k_1h_gt_30) | (roc_9_4h_gt_neg_10)": "15m fresh high, 1h low, 4h down 10%+",
  "(aroonu_14_15m_gt_20) | (rsi_3_4h_gt_15) | (cmf_20_4h_lt_0_15)": "15m downtrend, 4h oversold, 4h inflow",
  "(cmf_20_15m_gt_neg_0_30) | (roc_9_1h_gt_neg_10) | (rsi_3_1d_gt_15)": "15m heavy outflow, 1h down 10%+, 1d oversold",
  "(cci_20_change_pct_1h_lt_0) | (rsi_3_change_pct_1d_gt_neg_20) | (top_wick_pct_1d_lt_8)": "1h CCI rising, 1d RSI down 20%+, 1d top wick 8%+",
  "(stochrsi_k_1h_lt_30) | (aroonu_14_4h_lt_100) | (stochrsi_k_1d_lt_30)": "1h & 1d not low, 4h fresh high",
  "(rsi_3_15m_gt_50) | (cmf_20_15m_lt_0_30) | (aroonu_14_4h_lt_20)": "15m down move, 15m strong inflow, 4h uptrend",
  "(aroonu_14_15m_gt_60) | (stochrsi_k_1h_lt_90) | (aroonu_14_1d_gt_0)": "15m not high, 1h overbought, 1d no new high",
  "(stochrsi_k_15m_gt_80) | (rsi_3_1h_lt_65) | (aroonu_14_4h_lt_20)": "15m not high, 1h up move, 4h uptrend",
  "(aroonu_14_lt_30) | (aroond_14_gt_75) | (aroonu_14_1h_lt_80)": "5m uptrend, 5m no fresh low, 1h fresh high",
  "(rsi_3_15m_gt_20) | (cmf_20_15m_lt_0_10) | (aroonu_14_1h_gt_0)": "15m low, 15m inflow, 1h no new high",
  "(rsi_3_15m_lt_55) | (aroond_14_15m_lt_80) | (aroonu_14_1h_lt_70)": "15m up move, 15m fresh low, 1h uptrend",
  "(rsi_3_15m_gt_10) | (cmf_20_1h_gt_neg_0_25) | (roc_9_1d_gt_neg_15)": "15m oversold, 1h outflow, 1d down 15%+",
  "(cmf_20_15m_lt_0_10) | (aroonu_14_1h_gt_0) | (stochrsi_k_4h_lt_50)": "15m inflow, 1h no new high, 4h not low",
  "(rsi_3_15m_gt_30) | (cmf_20_15m_lt_0_10) | (aroonu_14_1h_gt_0)": "15m low, 15m inflow, 1h no new high",
  "(cmf_20_15m_gt_neg_0_30) | (stochrsi_k_15m_gt_10) | (rsi_3_1h_gt_3)": "15m heavy outflow, 15m low, 1h oversold",
  "(rsi_3_gt_10) | (cmf_20_1d_gt_neg_0_10) | (stochrsi_k_1d_gt_10)": "5m oversold, 1d outflow, 1d low",
  "(aroonu_14_1h_gt_0) | (stochrsi_k_1h_lt_60) | (stochrsi_k_4h_lt_40)": "1h no new high, 1h high, 4h not low",
  "(aroonu_14_lt_30) | (cmf_20_15m_gt_neg_0_30) | (aroonu_14_15m_lt_50)": "5m & 15m uptrend, 15m heavy outflow",
  "(cmf_20_15m_gt_neg_0_30) | (stochrsi_k_4h_gt_10) | (cmf_20_1d_lt_0_10)": "15m heavy outflow, 4h low, 1d inflow",
  "(rsi_3_lt_40) | (aroonu_14_1h_lt_80) | (cmf_20_4h_gt_neg_0_10)": "5m up move, 1h fresh high, 4h outflow",
  "(rsi_3_15m_lt_60) | (cmf_20_1h_gt_neg_0_25) | (aroonu_14_1h_lt_40)": "15m up move, 1h outflow, 1h uptrend",
  "(aroond_14_15m_lt_80) | (rsi_3_1d_gt_25) | (stochrsi_k_1d_lt_70)": "15m fresh low, 1d low, 1d high",
  "(cmf_20_15m_gt_neg_0_20) | (stochrsi_k_1h_gt_10) | (rsi_3_4h_gt_3)": "15m outflow, 1h low, 4h oversold",
  "(rsi_3_15m_gt_3) | (aroonu_14_15m_lt_40) | (stochrsi_k_4h_lt_40)": "15m oversold, 15m uptrend, 4h not low",
  "(rsi_14_15m_lt_50) | (rsi_3_1h_gt_40) | (stochrsi_k_1d_gt_10)": "15m up bias, 1h & 1d low",
  "(stochrsi_k_gt_80) | (rsi_3_15m_lt_60) | (aroonu_14_1d_lt_80)": "5m not high, 15m up move, 1d fresh high",
  "(stochrsi_k_15m_lt_60) | (roc_9_1d_lt_10) | (change_pct_1d_lt_10)": "15m high, 1d up 10%+, 1d green",
  "(aroonu_14_15m_gt_0) | (stochrsi_k_1h_gt_10) | (rsi_3_4h_gt_3)": "15m no new high, 1h low, 4h oversold",
  "(rsi_3_lt_95) | (rsi_3_1h_gt_20) | (roc_9_1d_gt_neg_10)": "5m overbought, 1h low, 1d down 10%+",
  "(aroonu_14_15m_gt_20) | (stochrsi_k_15m_gt_10) | (stochrsi_k_1h_lt_60)": "15m downtrend, 15m low, 1h high",
  "(rsi_3_15m_gt_50) | (aroonu_14_15m_lt_80) | (rsi_3_1h_lt_55)": "15m down move, 15m fresh high, 1h up move",
  "(rsi_14_15m_lt_50) | (aroond_14_15m_lt_80) | (aroonu_14_1h_gt_0)": "15m up bias, 15m fresh low, 1h no new high",
  "(aroonu_14_1h_lt_80) | (cci_20_change_pct_4h_lt_0) | (aroonu_14_1d_gt_20)": "1h fresh high, 4h CCI rising, 1d downtrend",
  "(aroonu_14_15m_lt_40) | (stochrsi_k_1d_gt_60) | (roc_9_1d_lt_10)": "15m uptrend, 1d not high, 1d up 10%+",
  "(aroonu_14_gt_75) | (aroond_14_15m_lt_25) | (rsi_3_1h_lt_70)": "5m not high, 15m fresh low, 1h overbought",
  "(stochrsi_k_lt_30) | (rsi_3_15m_gt_20) | (stochrsi_k_15m_lt_40)": "5m & 15m not low, 15m low",
  "(rsi_3_15m_gt_35) | (stochrsi_k_15m_lt_80) | (stochrsi_k_1d_lt_70)": "15m low, 15m overbought, 1d high",
  "(rsi_3_15m_gt_55) | (rsi_14_15m_lt_50) | (aroonu_14_1h_lt_30)": "15m down move, 15m up bias, 1h uptrend",
  "(rsi_3_gt_15) | (stochrsi_k_15m_lt_50) | (roc_9_1d_gt_neg_15)": "5m oversold, 15m not low, 1d down 15%+",
  "(cmf_20_1h_gt_neg_0_25) | (aroonu_14_1h_gt_0) | (aroonu_14_4h_gt_0)": "1h outflow, 1h & 4h no new high",
  "(rsi_3_15m_lt_50) | (cmf_20_1h_gt_neg_0_25) | (stochrsi_k_1d_lt_70)": "15m up move, 1h outflow, 1d high",
  "(stochrsi_k_lt_30) | (aroonu_14_1h_lt_60) | (stochrsi_k_1h_lt_70)": "5m not low, 1h uptrend, 1h high",
  "(rsi_3_4h_gt_20) | (stochrsi_k_4h_lt_50) | (rsi_3_change_pct_1d_gt_neg_20)": "4h low, 4h not low, 1d RSI down 20%+",
  "(aroonu_14_1h_gt_20) | (stochrsi_k_1h_lt_30) | (stochrsi_k_4h_lt_60)": "1h downtrend, 1h not low, 4h high",
  "(rsi_3_lt_46) | (stochrsi_k_15m_gt_10) | (aroonu_14_4h_gt_20)": "5m up move, 15m low, 4h downtrend",
  "(rsi_3_15m_gt_20) | (rsi_3_1h_lt_40) | (cmf_20_4h_lt_0_15)": "15m low, 1h up move, 4h inflow",
  "(rsi_3_gt_3) | (rsi_3_1h_lt_40) | (aroond_14_4h_lt_85)": "5m oversold, 1h up move, 4h fresh low",
  "(rsi_3_lt_98) | (rsi_3_1d_gt_15) | (aroonu_14_1d_gt_50)": "5m overbought, 1d oversold, 1d not high",
  "(aroonu_14_gt_75) | (aroonu_14_15m_lt_85) | (cmf_20_4h_lt_0_15)": "5m not high, 15m fresh high, 4h inflow",
  "(aroond_14_lt_25) | (stochrsi_k_1h_lt_90) | (aroonu_14_4h_lt_30)": "5m fresh low, 1h overbought, 4h uptrend",
  "(rsi_3_15m_gt_35) | (stochrsi_k_1h_lt_90) | (stochrsi_k_4h_gt_10)": "15m & 4h low, 1h overbought",
  "(aroonu_14_15m_gt_0) | (stochrsi_k_15m_gt_40) | (stochrsi_k_1h_lt_70)": "15m no new high, 15m not high, 1h high",
  "(aroonu_14_gt_75) | (aroonu_14_15m_lt_80) | (rsi_3_4h_gt_3)": "5m not high, 15m fresh high, 4h oversold",
  "(aroond_14_lt_25) | (cmf_20_15m_lt_0_30) | (rsi_3_1h_gt_50)": "5m fresh low, 15m strong inflow, 1h down move",
  "(rsi_3_15m_gt_50) | (rsi_14_15m_lt_50) | (stochrsi_k_1d_gt_10)": "15m down move, 15m up bias, 1d low",
  "(rsi_3_15m_gt_40) | (rsi_3_1h_lt_40) | (cmf_20_4h_lt_0_15)": "15m down move, 1h up move, 4h inflow",
  "(rsi_3_15m_gt_20) | (aroonu_14_15m_lt_80) | (aroonu_14_1d_gt_0)": "15m low, 15m fresh high, 1d no new high",
  "(rsi_3_gt_10) | (rsi_3_4h_gt_55) | (stochrsi_k_4h_lt_90)": "5m oversold, 4h down move, 4h overbought",
  "(rsi_3_15m_gt_55) | (aroonu_14_15m_lt_70) | (cmf_20_1h_gt_neg_0_40)": "15m down move, 15m uptrend, 1h heavy outflow",
  "(aroonu_14_15m_lt_80) | (cmf_20_1h_gt_neg_0_25) | (stochrsi_k_1d_lt_70)": "15m fresh high, 1h outflow, 1d high",
  "(rsi_3_15m_lt_70) | (stochrsi_k_15m_gt_40) | (stochrsi_k_4h_lt_40)": "15m overbought, 15m not high, 4h not low",
  "(aroonu_14_4h_lt_100) | (aroonu_14_1d_gt_0) | (stochrsi_k_1d_gt_60)": "4h fresh high, 1d no new high, 1d not high",
  "(rsi_3_lt_46) | (stochrsi_k_15m_gt_10) | (stochrsi_k_1h_lt_60)": "5m up move, 15m low, 1h high",
  "(aroonu_14_15m_gt_20) | (aroonu_14_1h_lt_80) | (aroonu_14_1d_gt_20)": "15m & 1d downtrend, 1h fresh high",
  "(stochrsi_k_1h_gt_40) | (rsi_3_4h_gt_15) | (cmf_20_4h_lt_0_15)": "1h not high, 4h oversold, 4h inflow",
  "(rsi_3_1h_lt_65) | (rsi_3_1d_gt_15) | (cmf_20_1d_lt_0_10)": "1h up move, 1d oversold, 1d inflow",
  "(rsi_3_gt_15) | (rsi_3_15m_gt_35) | (rsi_3_1h_lt_50)": "5m oversold, 15m low, 1h up move",
  "(stochrsi_k_lt_30) | (cmf_20_15m_gt_neg_0_30) | (aroonu_14_15m_lt_50)": "5m not low, 15m heavy outflow, 15m uptrend",
  "(rsi_3_15m_lt_75) | (stochrsi_k_1h_lt_50) | (cci_20_change_pct_1h_lt_0)": "15m overbought, 1h not low, 1h CCI rising",
  "(rsi_3_15m_gt_25) | (cmf_20_15m_lt_0_10) | (cmf_20_1h_gt_neg_0_20)": "15m low, 15m inflow, 1h outflow",
  "(aroonu_14_1h_gt_30) | (cmf_20_4h_lt_0_15) | (aroonu_14_4h_lt_80)": "1h downtrend, 4h inflow, 4h fresh high",
  "(rsi_3_gt_15) | (roc_9_4h_lt_5) | (aroonu_14_1d_gt_0)": "5m oversold, 4h up 5%+, 1d no new high",
  "(rsi_3_gt_3) | (stochrsi_k_4h_lt_40) | (aroonu_14_1d_gt_0)": "5m oversold, 4h not low, 1d no new high",
  "(stochrsi_k_15m_gt_10) | (stochrsi_k_1h_lt_60) | (rsi_3_1d_gt_15)": "15m low, 1h high, 1d oversold",
  "(rsi_14_15m_lt_50) | (rsi_3_1h_gt_50) | (stochrsi_k_1d_gt_10)": "15m up bias, 1h down move, 1d low",
  "(rsi_3_15m_gt_50) | (rsi_3_1h_lt_55) | (stochrsi_k_1h_gt_70)": "15m down move, 1h up move, 1h not high",
  "(stochrsi_k_gt_80) | (rsi_3_15m_lt_75) | (rsi_3_4h_gt_10)": "5m not high, 15m overbought, 4h oversold",
  "(stochrsi_k_15m_gt_10) | (aroonu_14_4h_gt_0) | (aroonu_14_1d_gt_20)": "15m low, 4h no new high, 1d downtrend",
  "(aroonu_14_15m_lt_30) | (cmf_20_4h_gt_neg_0_20) | (cmf_20_1d_lt_0_10)": "15m uptrend, 4h outflow, 1d inflow",
  "(stochrsi_k_4h_lt_70) | (stochrsi_k_1d_lt_30) | (change_pct_1d_gt_neg_5)": "4h high, 1d not low, 1d red",
  "(aroonu_14_15m_lt_70) | (aroonu_14_4h_lt_70) | (stochrsi_k_1d_lt_60)": "15m & 4h uptrend, 1d high",
  "(rsi_14_15m_lt_50) | (rsi_3_1d_gt_15) | (aroonu_14_1d_lt_60)": "15m up bias, 1d oversold, 1d uptrend",
  "(aroonu_14_15m_gt_0) | (stochrsi_k_1h_lt_70) | (aroonu_14_4h_gt_0)": "15m & 4h no new high, 1h high",
  "(rsi_3_15m_gt_30) | (aroonu_14_15m_gt_40) | (stochrsi_k_1h_lt_70)": "15m low, 15m not high, 1h high",
  "(stochrsi_k_15m_gt_70) | (stochrsi_k_1h_lt_90) | (aroonu_14_4h_lt_30)": "15m not high, 1h overbought, 4h uptrend",
  "(rsi_3_15m_gt_15) | (stochrsi_k_4h_lt_90) | (cci_20_change_pct_4h_lt_0)": "15m oversold, 4h overbought, 4h CCI rising",
  "(rsi_3_1h_lt_55) | (rsi_3_4h_gt_15) | (cmf_20_4h_lt_0_15)": "1h up move, 4h oversold, 4h inflow",
  "(aroonu_14_15m_gt_0) | (stochrsi_k_1h_lt_70) | (stochrsi_k_1d_gt_10)": "15m no new high, 1h high, 1d low",
  "(stochrsi_k_15m_gt_60) | (rsi_3_1h_lt_50) | (cmf_20_4h_lt_0_15)": "15m not high, 1h up move, 4h inflow",
  "(rsi_3_gt_15) | (stochrsi_k_15m_lt_60) | (aroonu_14_1d_lt_80)": "5m oversold, 15m high, 1d fresh high",
  "(rsi_3_15m_lt_70) | (aroond_14_15m_lt_80) | (rsi_3_4h_gt_3)": "15m overbought, 15m fresh low, 4h oversold",
  "(cmf_20_4h_lt_0_15) | (rsi_3_1d_gt_40) | (aroonu_14_1d_gt_0)": "4h inflow, 1d down move, 1d no new high",
  "(rsi_14_15m_lt_50) | (aroonu_14_15m_gt_0) | (cmf_20_1h_gt_neg_0_20)": "15m up bias, 15m no new high, 1h outflow",
  "(cmf_20_15m_lt_0_10) | (cmf_20_1h_gt_neg_0_20) | (stochrsi_k_1d_gt_10)": "15m inflow, 1h outflow, 1d low",
  "(aroonu_14_1h_lt_70) | (rsi_3_1d_gt_25) | (aroonu_14_1d_gt_0)": "1h uptrend, 1d low, 1d no new high",
  "(aroonu_14_4h_lt_30) | (stochrsi_k_4h_lt_50) | (rsi_3_1d_gt_15)": "4h uptrend, 4h not low, 1d oversold",
  "(rsi_3_15m_gt_20) | (stochrsi_k_1d_gt_60) | (roc_9_1d_lt_10)": "15m low, 1d not high, 1d up 10%+",
  "(cmf_20_15m_gt_neg_0_10) | (stochrsi_k_1h_lt_60) | (stochrsi_k_1d_gt_10)": "15m outflow, 1h high, 1d low",
  "(rsi_14_15m_lt_50) | (stochrsi_k_15m_gt_50) | (aroond_14_1h_lt_70)": "15m up bias, 15m not high, 1h fresh low",
  "(rsi_14_15m_lt_50) | (stochrsi_k_15m_gt_60) | (aroond_14_1h_lt_70)": "15m up bias, 15m not high, 1h fresh low",
  "(cmf_20_1h_gt_neg_0_20) | (stochrsi_k_1h_lt_60) | (roc_9_1d_gt_neg_10)": "1h outflow, 1h high, 1d down 10%+",
  "(aroonu_14_15m_lt_70) | (stochrsi_k_15m_gt_70) | (cmf_20_1h_gt_neg_0_25)": "15m uptrend, 15m not high, 1h outflow",
  "(aroonu_14_1h_lt_70) | (aroonu_14_4h_gt_0) | (aroonu_14_1d_gt_0)": "1h uptrend, 4h & 1d no new high",
  "(cmf_20_15m_lt_0_10) | (aroonu_14_15m_gt_0) | (stochrsi_k_1h_lt_60)": "15m inflow, 15m no new high, 1h high",
  "(stochrsi_k_4h_lt_60) | (rsi_3_1d_gt_45) | (stochrsi_k_1d_lt_70)": "4h & 1d high, 1d down move",
  "(aroonu_14_1h_gt_40) | (cmf_20_4h_gt_neg_0_0) | (stochrsi_k_4h_lt_90)": "1h not high, 4h outflow, 4h overbought",
  "(rsi_3_1h_gt_25) | (aroonu_14_1h_lt_80) | (aroonu_14_4h_gt_0)": "1h low, 1h fresh high, 4h no new high",
  "(aroonu_14_15m_gt_40) | (rsi_3_1h_lt_55) | (cci_20_change_pct_1h_lt_0)": "15m not high, 1h up move, 1h CCI rising",
  "(rsi_3_gt_3) | (rsi_14_15m_lt_30) | (rsi_3_4h_gt_25)": "5m oversold, 15m not oversold, 4h low",
  "(rsi_3_15m_lt_50) | (roc_9_4h_lt_5) | (roc_9_1d_lt_10)": "15m up move, 4h up 5%+, 1d up 10%+",
  "(stochrsi_k_4h_lt_40) | (rsi_3_1d_gt_25) | (aroonu_14_1d_lt_60)": "4h not low, 1d low, 1d uptrend",
  "(stochrsi_k_1h_lt_70) | (rsi_3_4h_gt_25) | (aroonu_14_4h_gt_0) | (rsi_3_change_pct_1d_gt_neg_20) | (aroonu_14_1d_lt_40)": "1h high, 4h low, 4h no new high, 1d RSI down 20%+, 1d uptrend",
  "(aroonu_14_15m_lt_60) | (aroond_14_15m_lt_25) | (stochrsi_k_1h_lt_60) | (rsi_3_1d_gt_20)": "15m uptrend, 15m fresh low, 1h high, 1d low",
  "(rsi_14_15m_lt_30) | (rsi_3_1h_gt_55) | (aroonu_14_1h_gt_0) | (aroonu_14_4h_lt_70) | (rsi_3_1d_gt_40)": "15m not oversold, 1h & 1d down move, 1h no new high, 4h uptrend",
  "(stochrsi_k_15m_lt_20) | (aroonu_14_1h_lt_30) | (rsi_3_4h_gt_20) | (aroonu_14_4h_lt_40) | (aroonu_14_1d_gt_0)": "15m not low, 1h & 4h uptrend, 4h low, 1d no new high",
  "(stochrsi_k_15m_lt_80) | (rsi_3_4h_gt_10) | (aroonu_14_4h_gt_0) | (rsi_3_1d_gt_15)": "15m overbought, 4h & 1d oversold, 4h no new high",
  "(aroonu_14_1h_gt_30) | (aroonu_14_4h_lt_20) | (roc_9_4h_gt_neg_10) | (roc_9_1d_gt_neg_25)": "1h downtrend, 4h uptrend, 4h down 10%+, 1d down 25%+",
  "(aroond_14_gt_75) | (stochrsi_k_1h_gt_10) | (aroonu_14_4h_lt_80) | (stochrsi_k_1d_lt_60)": "5m no fresh low, 1h low, 4h fresh high, 1d high",
  "(aroonu_14_1h_gt_60) | (aroonu_14_4h_lt_70) | (stochrsi_k_4h_lt_60) | (rsi_3_1d_gt_60) | (stochrsi_k_1d_lt_60)": "1h not high, 4h uptrend, 4h & 1d high, 1d down move",
  "(rsi_14_15m_lt_50) | (aroonu_14_15m_gt_0) | (rsi_3_1h_gt_45)": "15m up bias, 15m no new high, 1h down move",
}
TF_RANK = {"5m": 0, "15m": 1, "1h": 2, "4h": 3, "1d": 4}
FAMILY = ["rsi_3", "rsi_14", "cmf_20", "mfi_14", "aroonu_14", "aroond_14", "stochrsi_k", "willr_14", "roc_2", "roc_9"]
CLAUSE = re.compile(r"\(([a-z][a-z0-9_]*)\)")


def _src() -> str:
  return STRATEGY.read_text()


def _block() -> str:
  src = _src()
  start = src.index("# Condition #507 - Daily downtrend continuation (Short, experimental).")
  end = src.index("# Condition #", start + 1)
  return src[start:end]


def _flat(text: str) -> str:
  """A chain the formatter wraps over several lines, back on one line as '& ((a) | (b) | ...)'."""
  return re.sub(
    r"& \(\n(.*?)\n\s*\)\n",
    lambda m: "& (" + " ".join(line.strip() for line in m.group(1).splitlines()) + ")\n",
    text,
    flags=re.S,
  )


def _protections() -> str:
  block = _block()
  return _flat(block[block.index("# Protections") : block.index("# Logic")])


def _logic() -> str:
  block = _block()
  return block[block.index("# Logic") :]


def _chains() -> list[str]:
  """Every protection chain of the block, in file order, as '(a) | (b) | (c)'."""
  chains = []
  for line in _protections().splitlines():
    m = re.match(r"^\s*&?\s*\((\(.*\|.*\))\)$", line.strip()) or re.match(r"^\s*(\(.*\|.*\))$", line.strip())
    if m and not m.group(1).startswith("((macdh_12_26_9_1h"):
      chains.append(m.group(1))
  return chains


def _timeframe(name: str) -> str:
  m = re.search(r"_(15m|1h|4h|1d)_(?:gt|lt)_", name)
  return m.group(1) if m else "5m"


def _lead_key(chain: str) -> tuple[int, int]:
  """(timeframe rank, family rank) of a chain's lead clause."""
  name = re.search(r"\(([a-z][a-z0-9_]*?)_(?:gt|lt)_", chain).group(1)
  tf = (re.search(r"_(15m|1h|4h|1d)$", name) or [None, "5m"])[1]
  base = re.sub(r"_(15m|1h|4h|1d)$", "", name)
  family = next((f for f in FAMILY if base.startswith(f)), base)
  return TF_RANK[tf], FAMILY.index(family) if family in FAMILY else len(FAMILY)


def test_the_block_has_its_protection_chains():
  # Then: all 444 chains are there.
  assert len(_chains()) >= 444


def test_the_targeted_chains_live_inside_the_protection_append():
  protections = _protections()
  for chain in CHAINS:
    # Then: they are AND-ed operands of the block's single protection append, not an append of their own.
    assert f"& ({chain})" in protections
    assert f"short_entry_logic.append({chain})" not in protections


def test_each_targeted_chain_carries_the_house_comment_for_the_scene_it_blocks():
  protections = _protections()
  for chain, comment in CHAINS.items():
    # Then: the comment names the blocked state (all three clauses false), not its negation.
    assert re.search(rf"# {re.escape(comment)}\n\s+& \({re.escape(chain)}\)", protections), chain


def test_the_targeted_chains_sit_in_their_sorted_position():
  chains = _chains()
  for chain in CHAINS:
    i = chains.index(chain)
    mine = _lead_key(chain)
    # Then: timeframe ascending, and the family clustered within a shared timeframe.
    if i:
      assert _lead_key(chains[i - 1]) <= mine, (chains[i - 1], chain)
    if i + 1 < len(chains):
      assert mine <= _lead_key(chains[i + 1]), (chain, chains[i + 1])


def test_the_targeted_chains_are_three_to_five_clauses_on_two_timeframes_or_more():
  for chain in CHAINS:
    clauses = CLAUSE.findall(chain)
    # Then: three to five cached booleans, at least two frames.
    assert 3 <= len(clauses) <= 5, chain
    assert chain == " | ".join(f"({c})" for c in clauses), chain
    assert len({_timeframe(c) for c in clauses}) >= 2, chain


def test_the_chains_live_inside_one_protection_append():
  protections = _protections()
  # Then: the chains are AND-ed operands of one append, not an append each.
  for chain in _chains():
    assert f"short_entry_logic.append({chain})" not in protections
  assert protections.count("short_entry_logic.append(") == 4


def test_each_chain_carries_a_comment():
  lines = [line.strip() for line in _protections().splitlines()]
  for i, line in enumerate(lines):
    if re.match(r"^&?\s*\(\(.*\|", line):
      # Then: the line above names the state the chain blocks.
      assert lines[i - 1].startswith("# "), line


def test_the_chains_are_pure_disjunctions_so_they_can_only_block():
  for chain in _chains():
    # Then: two or more clauses joined by OR, no AND inside: the line is False only when every clause is.
    assert "&" not in chain, chain
    assert len(chain.split(" | ")) >= 2, chain


def test_every_clause_is_a_cached_boolean():
  src = _src()
  for name in {c for chain in _chains() for c in CLAUSE.findall(chain)}:
    # Then: '<name> = <series> <op> <number>' is defined once, outside the block.
    defs = re.findall(rf"^\s{{2,6}}{re.escape(name)} = [a-z0-9_]+ [<>] -?\d+(?:\.\d+)?$", src, re.M)
    assert len(defs) == 1, name


def test_each_chain_keeps_its_timeframes_in_ascending_order():
  for chain in _chains():
    ranks = [TF_RANK[_timeframe(c)] for c in CLAUSE.findall(chain)]
    # Then: low -> high, as the rest of the file writes them.
    assert ranks == sorted(ranks), chain


@pytest.mark.parametrize(
  "clause",
  [
    # daily downtrend: slow KAMA under the fast one, red 4h heikin-ashi candle under the slow KAMA
    "(kama_153_1d < kama_40_1d)",
    "& (ha_close_4h < ha_open_4h)",
    "& (ha_close_4h < kama_153_1d)",
    # not more than 3 ATR under the slow KAMA
    "& (close_4h > (kama_153_1d - (3.0 * atr_14_4h)))",
    # trending but not exhausted, on rising volume
    "& (adx_13_4h > 10.0)",
    "& (adx_13_4h < 55.0)",
    "& (vol_rel_27_4h > 1.0)",
    # BTC not strong
    "& (btc_rsi_14_1h < 50.0)",
    # not already 15% under the previous 20 candle high, not after a 24h crash
    "& (close >= (dc_high_20 * 0.85))",
    "& (roc_288 > -15.0)",
  ],
)
def test_the_logic_holds_every_trigger_condition(clause):
  # Then: the entry is the one 507 was validated with, condition for condition.
  assert clause in _logic()


def test_the_protections_hold_the_1h_two_of_four_guard():
  block = _block()
  protections = block[block.index("# Protections") : block.index("# Logic")]
  guard = (
    "& (\n"
    "              ((macdh_12_26_9_1h < 0.0) & (minus_di_14_1h > plus_di_14_1h))\n"
    "              | ((macdh_12_26_9_1h < 0.0) & (close_4h < dc_low_10_1h))\n"
    "              | ((macdh_12_26_9_1h < 0.0) & (rsi_14_1h < 50.0))\n"
    "              | ((minus_di_14_1h > plus_di_14_1h) & (close_4h < dc_low_10_1h))\n"
    "              | ((minus_di_14_1h > plus_di_14_1h) & (rsi_14_1h < 50.0))\n"
    "              | ((close_4h < dc_low_10_1h) & (rsi_14_1h < 50.0))\n"
    "            )\n"
  )
  # Then: 1h agrees, two of four, AND-ed into the protection chain and no longer in the logic.
  assert guard in protections
  assert "macdh_12_26_9_1h" not in _logic()


def test_the_protections_keep_the_empty_candle_global_and_hot_coin_guards():
  protections = _protections()
  # Then: enough candles, the global short guard, and a coin in its own top-third 28 day run is skipped.
  assert "short_entry_logic.append(num_empty_288 <= allowed_empty_candles_288)" in protections
  assert "short_entry_logic.append(protections_short_global == True)" in protections
  assert "short_entry_logic.append(mom_28_hot_1d < 0.5)" in protections


def test_the_signal_is_disabled_by_default():
  assert NostalgiaForInfinityX8.short_entry_signal_params["short_entry_condition_507_enable"] is False
  assert "507" in NostalgiaForInfinityX8.short_normal_mode_tags


@pytest.fixture
def daily_frame():
  rng = np.random.default_rng(507)
  close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.03, 800)))
  # a strong 28 day run at the end of the series
  close[-28:] = close[-29] * np.exp(np.linspace(0.02, 0.9, 28))
  return pd.DataFrame(
    {
      "date": pd.date_range("2022-01-01", periods=len(close), freq="D", tz="UTC"),
      "open": close,
      "high": close * 1.02,
      "low": close * 0.98,
      "close": close,
      "volume": 1000.0,
    }
  )


def _daily(frame: pd.DataFrame) -> pd.DataFrame:
  strategy = NostalgiaForInfinityX8.__new__(NostalgiaForInfinityX8)
  strategy.dp = SimpleNamespace(get_pair_dataframe=lambda **kwargs: frame.copy())
  return strategy.informative_1d_indicators({"pair": "ETH/USDT:USDT"}, "1d")


def test_the_daily_columns_do_not_read_future_candles(daily_frame):
  # Given: the same series, once whole and once cut 100 days short.
  full, cut = _daily(daily_frame), _daily(daily_frame.iloc[:-100].reset_index(drop=True))
  # Then: every row the cut series has is identical in the whole one.
  for col in ("KAMA_40", "KAMA_153", "MOM_28_HOT"):
    np.testing.assert_allclose(cut[col].to_numpy(), full[col].to_numpy()[: len(cut)], equal_nan=True, err_msg=col)


def test_a_coin_in_its_top_third_run_is_hot_and_stays_hot(daily_frame):
  hot = _daily(daily_frame)["MOM_28_HOT"].to_numpy()
  # Then: the run at the end is in the coin's own top third, and a hot flag holds for five days.
  assert hot[-1] == 1.0
  starts = np.where((hot[1:] == 1.0) & (hot[:-1] == 0.0))[0] + 1
  for s in starts[starts + 5 <= len(hot)]:
    assert (hot[s : s + 5] == 1.0).all()
