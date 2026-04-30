#!/usr/bin/env python3
"""Regression check for the spec profile registry."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
REGISTRY = SKILL_ROOT / "references/spec_profiles/index.json"


def temp_parent() -> Path:
    path = SKILL_ROOT / ".hyptest_skill_tmp"
    path.mkdir(parents=True, exist_ok=True)
    return path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    expected_default = str(registry.get("default_profile", "")).strip()
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "check_spec_profile_registry.py"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    failures: list[str] = []
    if completed.returncode != 0:
        failures.append("registry check should pass")
    else:
        payload = json.loads(completed.stdout)
        if payload.get("default_profile") != expected_default:
            failures.append(f"default_profile should be {expected_default}")
        if int(payload.get("profile_count", 0)) < 2:
            failures.append("registry should include active profile and template")

    generic = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "check_spec_profile_registry.py"),
            "--policy",
            "generic-docs",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if generic.returncode != 0:
        failures.append("generic-docs policy should pass")

    with tempfile.TemporaryDirectory(prefix="hyptest_profile_registry_", dir=temp_parent()) as tmpdir:
        tmp = Path(tmpdir)
        profile_dir = tmp / "references/spec_profiles"
        write(profile_dir / "good.md", "# good\n")
        write(profile_dir / "extra.md", "# extra\n")
        bad_registry = profile_dir / "index.json"
        bad_registry.write_text(
            json.dumps(
                {
                    "version": 1,
                    "default_profile": "missing_default",
                    "profiles": [
                        {
                            "name": "wrong_name",
                            "path": "references/spec_profiles/good.md",
                            "status": "active",
                        },
                        {
                            "name": "missing_path",
                            "path": "references/spec_profiles/nope.md",
                            "status": "active",
                        },
                        {
                            "name": "weird_status",
                            "path": "references/spec_profiles/extra.md",
                            "status": "odd",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        bad = subprocess.run(
            [
                sys.executable,
                str(SCRIPT_DIR / "check_spec_profile_registry.py"),
                "--registry",
                str(bad_registry),
                "--profile-dir",
                str(profile_dir),
                "--json",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if bad.returncode == 0:
            failures.append("bad registry fixture should fail")
        else:
            bad_payload = json.loads(bad.stdout)
            joined = "\n".join(bad_payload.get("issues", []) + bad_payload.get("warnings", []))
            for expected in ["default_profile", "path missing", "stem", "unknown status"]:
                if expected not in joined:
                    failures.append(f"bad registry fixture should mention {expected}")

    if failures:
        print("FAIL spec profile registry eval")
        for failure in failures:
            print(f"  - {failure}")
        print(completed.stderr or completed.stdout)
        return 1
    print("PASS spec profile registry eval")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
