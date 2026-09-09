#!/usr/bin/env python3
"""Validate all #450 evidence inputs and atomically publish the final manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_PATHS = sorted(
  [
    ".github/workflows/unit-tests.yml",
    "NostalgiaForInfinityX7.py",
    "tests/differential/test_NFIX7_informative_equivalence.py",
    "tests/differential/verify_nfix7_evidence.py",
    "tests/unit/test_NFIX7_informative_indicators.py",
  ]
)
NEW_TEST_SOURCES = [
  REPO_ROOT / "tests/unit/test_NFIX7_informative_indicators.py",
  REPO_ROOT / "tests/differential/test_NFIX7_informative_equivalence.py",
]


def fail(message: str) -> None:
  raise SystemExit(f"nfix7 evidence verification failed: {message}")


def sha256_bytes(data: bytes) -> str:
  return hashlib.sha256(data).hexdigest()


def source_sha(path: Path) -> str:
  if not path.is_file():
    fail(f"missing file: {path}")
  return sha256_bytes(path.read_bytes())


def bundle_sha(paths: list[str]) -> str:
  digest = hashlib.sha256()
  for raw_path in sorted(paths):
    path = REPO_ROOT / raw_path
    if not path.is_file():
      fail(f"bundle file missing: {raw_path}")
    data = path.read_bytes()
    name = raw_path.encode("utf-8")
    digest.update(len(name).to_bytes(8, "big"))
    digest.update(name)
    digest.update(len(data).to_bytes(8, "big"))
    digest.update(data)
  return digest.hexdigest()


def junit_stats(path: Path, *, allow_skips: bool) -> dict[str, int]:
  if not path.is_file():
    fail(f"JUnit file missing: {path}")
  try:
    root = ET.parse(path).getroot()
  except ET.ParseError as error:
    fail(f"invalid JUnit XML {path}: {error}")
  suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
  if not suites:
    fail(f"no testsuite in {path}")
  stats = {key: sum(int(s.get(key, "0")) for s in suites) for key in ("tests", "failures", "errors", "skipped")}
  if stats["tests"] <= 0:
    fail(f"no tests recorded in {path}")
  if stats["failures"] or stats["errors"]:
    fail(f"failed JUnit gate {path}: {stats}")
  if not allow_skips and stats["skipped"]:
    fail(f"focused/differential skips or xfails forbidden in {path}: {stats}")
  return stats


def assert_no_expected_failure_markers() -> None:
  forbidden = ("pytest.mark.xfail", "pytest.xfail(", "@pytest.mark.skip", "pytest.skip(")
  for path in NEW_TEST_SOURCES:
    text = path.read_text()
    hits = [token for token in forbidden if token in text]
    if hits:
      fail(f"forbidden skip/xfail markers in {path}: {hits}")


def require_equal(actual: Any, expected: Any, label: str) -> None:
  if actual != expected:
    fail(f"{label} mismatch: expected={expected!r}, actual={actual!r}")


def validate_raw(raw: dict[str, Any], args, changed_paths: list[str]) -> None:
  require_equal(raw.get("result"), "passed", "raw result")
  manifest = raw.get("manifest")
  if not isinstance(manifest, dict):
    fail("raw manifest is absent")
  expected = {
    "mode": args.mode,
    "base_sha": args.base_sha,
    "head_sha": args.head_sha,
    "base_source_sha256": args.base_source_sha256,
    "feature_source_sha256": args.feature_source_sha256,
    "feature_bundle_sha256": args.feature_bundle_sha256,
    "changed_paths": changed_paths,
    "changed_paths_sha256": args.changed_paths_sha256,
    "image_id": args.image_id,
    "pre_commit_version": args.pre_commit_version,
  }
  for key, value in expected.items():
    require_equal(manifest.get(key), value, f"raw manifest {key}")
  for package in ("python", "freqtrade", "pandas", "numpy", "ta_lib"):
    if not isinstance(manifest.get(package), str) or not manifest[package]:
      fail(f"missing package version: {package}")

  matrix = raw.get("matrix", {})
  require_equal(len(matrix), 40, "fixture/profile matrix size")
  if any(value != "passed" for value in matrix.values()):
    fail("matrix contains a failed entry")
  expected_profiles = {"1d", "4h", "1h", "15m"}
  calls = raw.get("call_fingerprints", {})
  debug = raw.get("debug_instrumentation", {})
  require_equal(set(calls), expected_profiles, "call fingerprint profiles")
  require_equal(set(debug), expected_profiles, "debug profiles")
  if any(not value.get("passed") for value in calls.values()):
    fail("call fingerprint result is not passed")
  if any(not value.get("passed") for value in debug.values()):
    fail("debug instrumentation result is not passed")
  runtime = raw.get("runtime_instrumentation", {})
  require_equal(len(runtime), 8, "runtime instrumentation matrix")
  callers = raw.get("caller_source_gate", {})
  require_equal(set(callers), {"info_switcher", "populate_indicators"}, "caller source gate")
  for name, value in callers.items():
    if not value.get("passed") or value.get("baseline") != value.get("feature"):
      fail(f"caller AST gate failed: {name}")
  structural = raw.get("structural_ast", {})
  require_equal(structural.get("signatures"), "passed", "structural signatures")
  require_equal(structural.get("ownership"), "passed", "structural ownership")


def parse_args(argv=None):
  parser = argparse.ArgumentParser()
  parser.add_argument("--focused", required=True, type=Path)
  parser.add_argument("--full-unit", required=True, type=Path)
  parser.add_argument("--differential", required=True, type=Path)
  parser.add_argument("--raw", required=True, type=Path)
  parser.add_argument("--output", required=True, type=Path)
  parser.add_argument("--mode", required=True, choices=("local-precommit", "pull-request"))
  parser.add_argument("--base-sha", required=True)
  parser.add_argument("--head-sha", required=True)
  parser.add_argument("--base-source-sha256", required=True)
  parser.add_argument("--feature-source-sha256", required=True)
  parser.add_argument("--feature-bundle-sha256", required=True)
  parser.add_argument("--changed-paths-json", required=True)
  parser.add_argument("--changed-paths-sha256", required=True)
  parser.add_argument("--image-id", required=True)
  parser.add_argument("--pre-commit-version", required=True)
  return parser.parse_args(argv)


def main(argv=None) -> int:
  args = parse_args(argv)
  output = args.output.resolve()
  # A failed verifier may never leave a stale final artifact behind.
  output.unlink(missing_ok=True)

  if args.mode == "pull-request" and args.base_sha == args.head_sha:
    fail("pull-request BASE_SHA equals HEAD_SHA")
  if args.base_source_sha256 == args.feature_source_sha256:
    fail("baseline and feature source identities are equal")
  try:
    changed_paths = json.loads(args.changed_paths_json)
  except json.JSONDecodeError as error:
    fail(f"invalid changed-path JSON: {error}")
  require_equal(changed_paths, ALLOWED_PATHS, "changed path allowlist")
  require_equal(sha256_bytes("\0".join(changed_paths).encode()), args.changed_paths_sha256, "changed path hash")
  require_equal(
    source_sha(REPO_ROOT / "NostalgiaForInfinityX7.py"), args.feature_source_sha256, "current feature source hash"
  )
  require_equal(bundle_sha(changed_paths), args.feature_bundle_sha256, "current feature bundle hash")

  focused = junit_stats(args.focused, allow_skips=False)
  full_unit = junit_stats(args.full_unit, allow_skips=True)
  differential = junit_stats(args.differential, allow_skips=False)
  assert_no_expected_failure_markers()
  if not args.raw.is_file():
    fail(f"raw evidence missing: {args.raw}")
  try:
    raw = json.loads(args.raw.read_text())
  except json.JSONDecodeError as error:
    fail(f"invalid raw JSON: {error}")
  validate_raw(raw, args, changed_paths)

  final = {
    "schema": 1,
    "result": "passed",
    "mode": args.mode,
    "identity": {
      "base_sha": args.base_sha,
      "head_sha": args.head_sha,
      "base_source_sha256": args.base_source_sha256,
      "feature_source_sha256": args.feature_source_sha256,
      "feature_bundle_sha256": args.feature_bundle_sha256,
      "changed_paths": changed_paths,
      "changed_paths_sha256": args.changed_paths_sha256,
      "image_id": args.image_id,
      "pre_commit_version": args.pre_commit_version,
    },
    "junit": {"focused": focused, "full_unit": full_unit, "differential": differential},
    "packages": {key: raw["manifest"][key] for key in ("python", "freqtrade", "pandas", "numpy", "ta_lib")},
    "differential": {
      "matrix": raw["matrix"],
      "call_fingerprints": raw["call_fingerprints"],
      "debug_instrumentation": raw["debug_instrumentation"],
      "runtime_instrumentation": raw["runtime_instrumentation"],
      "caller_source_gate": raw["caller_source_gate"],
      "structural_ast": raw["structural_ast"],
    },
  }
  output.parent.mkdir(parents=True, exist_ok=True)
  fd, temporary_name = tempfile.mkstemp(prefix=f".{output.name}.", suffix=".tmp", dir=output.parent)
  temporary = Path(temporary_name)
  try:
    with os.fdopen(fd, "w") as handle:
      json.dump(final, handle, indent=2, sort_keys=True)
      handle.write("\n")
      handle.flush()
      os.fsync(handle.fileno())
    os.replace(temporary, output)
  finally:
    temporary.unlink(missing_ok=True)
  if not output.is_file() or output.stat().st_size == 0:
    fail("atomic output creation failed")
  return 0


if __name__ == "__main__":
  sys.exit(main())
