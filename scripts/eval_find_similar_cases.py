#!/usr/bin/env python3
"""
Run a small regression suite for find_similar_cases.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, List


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate find_similar_cases.py against fixed fixtures.")
    parser.add_argument("--repo-root", required=True, help="Path to riscv-hyp-tests repo root")
    parser.add_argument(
        "--fixture",
        default=str(
            Path(__file__).resolve().parent.parent / "assets/evals/find_similar_cases_eval.json"
        ),
        help="Path to the evaluation fixture JSON",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first failing eval case",
    )
    parser.add_argument(
        "--case-timeout-seconds",
        type=float,
        default=90.0,
        help="Per-eval timeout in seconds when invoking find_similar_cases.py",
    )
    return parser.parse_args()


def read_fixture(path: Path) -> List[Dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_input_path(raw: str, repo_root: Path, fixture_path: Path) -> Path:
    candidate = Path(raw)
    if candidate.is_absolute() and candidate.exists():
        return candidate

    repo_candidate = repo_root / raw
    if repo_candidate.exists():
        return repo_candidate

    fixture_candidate = fixture_path.parent / raw
    if fixture_candidate.exists():
        return fixture_candidate

    raise FileNotFoundError(f"Unable to resolve fixture path: {raw}")


def run_eval_case(
    script_path: Path,
    repo_root: Path,
    fixture_path: Path,
    case: Dict[str, object],
    timeout_seconds: float,
) -> tuple[List[str], float]:
    command = [
        sys.executable,
        str(script_path),
        "--repo-root",
        str(repo_root),
        "--json",
    ]

    for query in case.get("queries", []):
        command.extend(["--query", str(query)])

    raw_from_file = case.get("from_file")
    if raw_from_file:
        resolved = resolve_input_path(str(raw_from_file), repo_root, fixture_path)
        command.extend(["--from-file", str(resolved)])
    heading_pattern = case.get("heading_pattern")
    if heading_pattern:
        command.extend(["--heading-pattern", str(heading_pattern)])
    section_index = case.get("section_index")
    if section_index is not None:
        command.extend(["--section-index", str(section_index)])

    started_at = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        duration = time.monotonic() - started_at
        return ([f"command timed out after {timeout_seconds:.1f}s"], duration)

    duration = time.monotonic() - started_at
    if completed.returncode != 0:
        return (
            [
                f"command failed with code {completed.returncode}",
                completed.stderr.strip() or completed.stdout.strip() or "no output",
            ],
            duration,
        )

    payload = json.loads(completed.stdout)
    failures: List[str] = []

    expected_status = case.get("expected_status")
    if expected_status and payload.get("retrieval_status") != expected_status:
        failures.append(
            f"expected status {expected_status}, got {payload.get('retrieval_status')}"
        )

    expected_top1 = case.get("expected_top1")
    if expected_top1:
        actual_top1 = payload["results"][0]["case_name"] if payload.get("results") else None
        if actual_top1 != expected_top1:
            failures.append(f"expected top1 {expected_top1}, got {actual_top1}")

    expected_result_count = case.get("expected_result_count")
    if expected_result_count is not None and payload.get("result_count") != expected_result_count:
        failures.append(
            "expected result_count "
            f"{expected_result_count}, got {payload.get('result_count')}"
        )

    return failures, duration


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    fixture_path = Path(args.fixture).expanduser().resolve()
    script_path = Path(__file__).resolve().parent / "find_similar_cases.py"

    eval_cases = read_fixture(fixture_path)
    passed = 0

    total = len(eval_cases)
    for index, case in enumerate(eval_cases, start=1):
        label = str(case.get("id", "unnamed"))
        description = str(case.get("description", "")).strip()
        progress = f"[{index}/{total}]"
        print(f"RUN  {progress} {label}", flush=True)
        if description:
            print(f"  desc: {description}", flush=True)

        failures, duration = run_eval_case(
            script_path,
            repo_root,
            fixture_path,
            case,
            args.case_timeout_seconds,
        )
        if failures:
            print(f"FAIL {progress} {label} ({duration:.2f}s)")
            for failure in failures:
                print(f"  - {failure}")
            if args.fail_fast:
                return 1
            continue

        passed += 1
        print(f"PASS {progress} {label} ({duration:.2f}s)")

    print(f"summary: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
