import argparse

import pytest

from tools.benchmark_merge_informative_pair import build_merge_specs
from tools.benchmark_merge_informative_pair import build_report
from tools.benchmark_merge_informative_pair import format_text_report
from tools.benchmark_merge_informative_pair import informative_rows
from tools.benchmark_merge_informative_pair import parse_timeframes
from tools.benchmark_merge_informative_pair import summarize_runs
from tools.benchmark_merge_informative_pair import timeframe_to_minutes


def test_timeframe_to_minutes():
  assert timeframe_to_minutes("5m") == 5
  assert timeframe_to_minutes("1h") == 60
  assert timeframe_to_minutes("4h") == 240
  assert timeframe_to_minutes("1d") == 1440


def test_build_merge_specs_uses_x7_like_default_shape():
  specs = build_merge_specs(
    btc_timeframes=parse_timeframes("5m,15m,1h,4h,1d"),
    info_timeframes=parse_timeframes("15m,1h,4h,1d"),
    indicator_columns=24,
    btc_indicator_columns=0,
  )

  assert [spec.name for spec in specs] == [
    "btc_5m",
    "btc_15m",
    "btc_1h",
    "btc_4h",
    "btc_1d",
    "informative_15m",
    "informative_1h",
    "informative_4h",
    "informative_1d",
  ]
  assert specs[0].source == "btc"
  assert specs[-1].source == "pair"


def test_informative_rows_covers_base_timerange():
  assert informative_rows(base_rows=1200, base_timeframe="5m", informative_timeframe="5m") == 1202
  assert informative_rows(base_rows=1200, base_timeframe="5m", informative_timeframe="1h") == 102


def test_summarize_runs_reports_total_and_step_stats():
  specs = build_merge_specs(("5m",), ("1h",), indicator_columns=24, btc_indicator_columns=0)
  runs = [
    [
      {
        "name": "btc_5m",
        "source": "btc",
        "timeframe": "5m",
        "seconds": 0.10,
        "columns_after": 8,
        "memory_after_bytes": 1024,
      },
      {
        "name": "informative_1h",
        "source": "pair",
        "timeframe": "1h",
        "seconds": 0.20,
        "columns_after": 20,
        "memory_after_bytes": 2048,
      },
    ],
    [
      {
        "name": "btc_5m",
        "source": "btc",
        "timeframe": "5m",
        "seconds": 0.20,
        "columns_after": 8,
        "memory_after_bytes": 1024,
      },
      {
        "name": "informative_1h",
        "source": "pair",
        "timeframe": "1h",
        "seconds": 0.40,
        "columns_after": 20,
        "memory_after_bytes": 2048,
      },
    ],
  ]

  summary = summarize_runs(runs, specs)

  assert summary["total"]["mean_seconds"] == pytest.approx(0.45)
  assert summary["steps"][0]["mean_seconds"] == pytest.approx(0.15)
  assert summary["steps"][1]["max_seconds"] == 0.40


def test_format_text_report_includes_main_numbers():
  args = argparse.Namespace(
    rows=1200,
    repeat=2,
    base_timeframe="5m",
    no_drop_ohlcv=False,
  )
  report = {
    "benchmark": "merge_informative_pair",
    "rows": args.rows,
    "repeat": args.repeat,
    "base_timeframe": args.base_timeframe,
    "drop_ohlcv": not args.no_drop_ohlcv,
    "summary": {
      "total": {
        "mean_seconds": 0.45,
        "median_seconds": 0.45,
      },
      "steps": [
        {
          "name": "btc_5m",
          "mean_seconds": 0.15,
          "median_seconds": 0.15,
          "columns_after": 8,
          "memory_after_bytes": 1024 * 1024,
        }
      ],
    },
  }

  output = format_text_report(report)

  assert "mean_total_seconds=0.450000" in output
  assert "btc_5m" in output
  assert "memory_after_mib" in output


def test_build_report_validates_positive_repeat_before_runtime_imports():
  args = argparse.Namespace(
    rows=1200,
    repeat=0,
    indicator_columns=24,
    btc_indicator_columns=0,
  )

  with pytest.raises(RuntimeError, match="--repeat must be greater than 0"):
    build_report(args)
