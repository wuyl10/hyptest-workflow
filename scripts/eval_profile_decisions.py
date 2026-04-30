#!/usr/bin/env python3
"""Evaluate profile-specific decision facts stay profile-local."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
FIXTURE = SKILL_ROOT / "assets/evals/profile_decision_eval.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate profile decision fixtures.")
    parser.add_argument("--fixture", default=str(FIXTURE), help="Fixture JSON path.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def resolve_profile(profile: str) -> Path:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "resolve_spec_profile.py"), "--spec-profile", profile],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    return Path(completed.stdout.strip())


def extract_profile_block(text: str) -> dict[str, str]:
    marker = "```hyptest-profile"
    start = text.find(marker)
    if start < 0:
        return {}
    body_start = text.find("\n", start)
    end = text.find("```", body_start + 1)
    if body_start < 0 or end < 0:
        return {}
    values: dict[str, str] = {}
    for raw_line in text[body_start:end].splitlines():
        if ":" not in raw_line:
            continue
        key, value = raw_line.split(":", 1)
        values[key.strip()] = value.strip()
    return values


def main() -> int:
    args = parse_args()
    fixture = Path(args.fixture).expanduser().resolve()
    cases = json.loads(fixture.read_text(encoding="utf-8"))
    failures: list[str] = []
    results: list[dict[str, object]] = []

    for item in cases:
        case_failures: list[str] = []
        try:
            path = resolve_profile(str(item["profile"]))
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, RuntimeError) as exc:
            failures.append(f"{item.get('id', item.get('profile'))}: {exc}")
            continue
        facts = extract_profile_block(text)
        for key, expected in item.get("expected_facts", {}).items():
            if facts.get(key) != expected:
                case_failures.append(f"{key} expected {expected}, got {facts.get(key)}")
        for term in item.get("expected_terms", []):
            if term not in text:
                case_failures.append(f"missing term {term}")
        if case_failures:
            failures.append(f"{item['id']}: {', '.join(case_failures)}")
        results.append({"id": item["id"], "ok": not case_failures, "path": str(path)})

    payload = {
        "ok": not failures,
        "fixture": str(fixture),
        "case_count": len(cases),
        "failures": failures,
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " profile decision eval")
        for failure in failures:
            print(f"  - {failure}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
