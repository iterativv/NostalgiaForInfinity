import json
import zipfile

import pytest

from tools.compare_backtest_results import build_report
from tools.compare_backtest_results import main


def result_data(strategy_name="Strategy", trades=None):
  if trades is None:
    trades = [
      {
        "pair": "ETH/USDT",
        "is_short": False,
        "open_date": "2026-01-01 00:00:00+00:00",
        "close_date": "2026-01-01 01:00:00+00:00",
        "enter_tag": "entry_a",
        "exit_reason": "exit_a",
        "profit_ratio": 0.012345678901,
        "profit_abs": 1.23456789012,
      }
    ]
  return {
    "strategy": {
      strategy_name: {
        "trades": trades,
        "total_trades": len(trades),
        "profit_total": 0.012345678901,
        "profit_total_abs": 1.23456789012,
        "profit_factor": 2.0,
        "winrate": 1.0,
        "max_drawdown_abs": 0.0,
      }
    }
  }


def write_json(path, data):
  path.write_text(json.dumps(data), encoding="utf-8")


def write_zip(path, data):
  with zipfile.ZipFile(path, "w") as zip_file:
    zip_file.writestr("backtest-result-2026-01-01.json", json.dumps(data))
    zip_file.writestr("backtest-result-2026-01-01.meta.json", "{}")
    zip_file.writestr("backtest-result-2026-01-01_config.json", "{}")


def test_compare_equal_json_results(tmp_path):
  left = tmp_path / "left.json"
  right = tmp_path / "right.json"
  write_json(left, result_data("Original"))
  write_json(right, result_data("Candidate"))

  report = build_report(left, right, None, None, 10)

  assert report["trade_surface_equal"] is True
  assert report["first_difference"] is None
  assert report["left_strategy"] == "Original"
  assert report["right_strategy"] == "Candidate"


def test_compare_zip_results(tmp_path):
  left = tmp_path / "left.zip"
  right = tmp_path / "right.zip"
  write_zip(left, result_data("Original"))
  write_zip(right, result_data("Candidate"))

  report = build_report(left, right, None, None, 10)

  assert report["trade_surface_equal"] is True


def test_compare_reports_first_trade_difference(tmp_path):
  left = tmp_path / "left.json"
  right = tmp_path / "right.json"
  write_json(left, result_data("Original"))
  right_data = result_data("Candidate")
  right_data["strategy"]["Candidate"]["trades"][0]["exit_reason"] = "different_exit"
  write_json(right, right_data)

  report = build_report(left, right, None, None, 10)

  assert report["trade_surface_equal"] is False
  assert report["first_difference"]["index"] == 0
  assert report["first_difference"]["left"]["exit_reason"] == "exit_a"
  assert report["first_difference"]["right"]["exit_reason"] == "different_exit"


def test_compare_reports_trade_count_difference(tmp_path):
  left = tmp_path / "left.json"
  right = tmp_path / "right.json"
  write_json(left, result_data("Original"))
  write_json(right, result_data("Candidate", trades=[]))

  report = build_report(left, right, None, None, 10)

  assert report["trade_surface_equal"] is False
  assert report["first_difference"] == {"left_count": 1, "right_count": 0}


def test_strategy_name_can_be_selected_when_result_has_multiple_strategies(tmp_path):
  path = tmp_path / "results.json"
  data = result_data("Original")
  data["strategy"]["Candidate"] = result_data("Candidate")["strategy"]["Candidate"]
  write_json(path, data)

  report = build_report(path, path, "Original", "Candidate", 10)

  assert report["left_strategy"] == "Original"
  assert report["right_strategy"] == "Candidate"
  assert report["trade_surface_equal"] is True


def test_cli_returns_nonzero_when_trade_surface_differs(tmp_path):
  left = tmp_path / "left.json"
  right = tmp_path / "right.json"
  write_json(left, result_data("Original"))
  write_json(right, result_data("Candidate", trades=[]))

  assert main([str(left), str(right)]) == 1


def test_multiple_strategy_result_requires_selection(tmp_path):
  path = tmp_path / "results.json"
  data = result_data("Original")
  data["strategy"]["Candidate"] = result_data("Candidate")["strategy"]["Candidate"]
  write_json(path, data)

  with pytest.raises(RuntimeError, match="Use --left-strategy/--right-strategy"):
    build_report(path, path, None, None, 10)
