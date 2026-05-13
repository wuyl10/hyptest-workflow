#!/usr/bin/env python3
"""Regression checks for check_target_module.py."""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_checker(module: str, source_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "check_target_module.py"),
            "--module",
            module,
            "--source-root",
            str(source_root),
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )


def make_fixture(tmp: Path) -> Path:
    """Create a minimal fake Nanhu src/main tree for deterministic matching."""
    src = tmp / "src" / "main" / "scala" / "xiangshan"
    (src / "mem").mkdir(parents=True, exist_ok=True)
    (src / "backend").mkdir(parents=True, exist_ok=True)
    for name in (
        "MemBlock.scala",
        "StoreQueue.scala",
        "LoadQueue.scala",
        "AtomicsUnit.scala",
    ):
        (src / "mem" / name).write_text("// fixture\n", encoding="utf-8")
    return tmp / "src" / "main"


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="hyptest_ctm_") as tmpdir:
        root = make_fixture(Path(tmpdir))

        # Case 1: exact match (case-insensitive).
        result = run_checker("MemBlock", root)
        if result.returncode != 0 or '"verdict": "exact"' not in result.stdout:
            failures.append("exact-match: MemBlock should resolve to exact verdict")

        # Case 2: lowercase → exact via case-insensitive match.
        result = run_checker("memblock", root)
        if result.returncode != 0 or '"verdict": "exact"' not in result.stdout:
            failures.append("case-insensitive: memblock should hit exact verdict on MemBlock")

        # Case 3: snake_case expansion → StoreQueue.
        result = run_checker("store_queue", root)
        if result.returncode != 0 or '"verdict": "expansion"' not in result.stdout:
            failures.append("expansion: store_queue should rewrite to StoreQueue via expansion")
        if '"resolved_module": "StoreQueue"' not in result.stdout:
            failures.append("expansion: resolved_module should be StoreQueue")

        # Case 4: typo with edit distance 1 → fuzzy candidates, exit 1.
        result = run_checker("mmemblock", root)
        if result.returncode == 0:
            failures.append("fuzzy: mmemblock should NOT auto-resolve (exit 1 required)")
        if '"verdict": "fuzzy_candidates"' not in result.stdout:
            failures.append("fuzzy: mmemblock should land in fuzzy_candidates verdict")
        if '"MemBlock"' not in result.stdout:
            failures.append("fuzzy: MemBlock should appear in candidate list")

        # Case 5: pure garbage → miss with no candidates.
        result = run_checker("totallyNotAModule", root)
        if result.returncode == 0:
            failures.append("miss: garbage module should exit non-zero")
        if '"verdict": "miss"' not in result.stdout:
            failures.append("miss: garbage module should land in miss verdict")

    if failures:
        print("FAIL check_target_module eval")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("PASS check_target_module eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
