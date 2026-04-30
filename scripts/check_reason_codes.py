#!/usr/bin/env python3
"""
Check that referenced hyptest reason codes are defined and machine-readable.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


CODE_RE = re.compile(r"D-(?:PASS|MANUAL|COMPILE|BLOCK)-[A-Z0-9-]+")
VALID_CLASSES = {"PASS", "MANUAL", "COMPILE", "BLOCK"}


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check reason code references.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def iter_reference_files(root: Path) -> list[Path]:
    paths = list((root / "references").rglob("*.md"))
    paths.append(root / "SKILL.md")
    paths.append(root / "README.md")
    return sorted(path for path in paths if path.is_file())


def load_reason_code_json(root: Path) -> tuple[dict[str, dict[str, object]], list[str]]:
    path = root / "assets/reason_codes.json"
    issues: list[str] = []
    if not path.is_file():
        return {}, ["missing assets/reason_codes.json"]
    try:
        rows = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, [f"assets/reason_codes.json invalid JSON: {exc}"]
    if not isinstance(rows, list):
        return {}, ["assets/reason_codes.json must be a list"]

    by_code: dict[str, dict[str, object]] = {}
    required_fields = {
        "code",
        "class",
        "default_decision",
        "meaning",
        "typical_followup",
        "owner",
        "next_required_evidence",
        "keywords",
    }
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            issues.append(f"assets/reason_codes.json[{index}] must be an object")
            continue
        missing = sorted(required_fields - set(row))
        if missing:
            issues.append(f"{row.get('code', index)} missing fields: {', '.join(missing)}")
            continue
        code = str(row["code"])
        klass = str(row["class"])
        if not CODE_RE.fullmatch(code):
            issues.append(f"{code}: invalid code format")
        if klass not in VALID_CLASSES:
            issues.append(f"{code}: invalid class {klass}")
        if not code.startswith(f"D-{klass}-"):
            issues.append(f"{code}: class field does not match code prefix {klass}")
        if code in by_code:
            issues.append(f"{code}: duplicate entry in assets/reason_codes.json")
        keywords = row.get("keywords")
        if not isinstance(keywords, list) or not all(str(item).strip() for item in keywords):
            issues.append(f"{code}: keywords must be a non-empty list of strings")
        evidence = row.get("next_required_evidence")
        if not isinstance(evidence, list) or not all(str(item).strip() for item in evidence):
            issues.append(f"{code}: next_required_evidence must be a non-empty list of strings")
        if not str(row.get("owner", "")).strip():
            issues.append(f"{code}: owner must be non-empty")
        by_code[code] = row
    return by_code, issues


def main() -> int:
    args = parse_args()
    root = skill_root()
    catalog = root / "references/reason_code_catalog.md"
    catalog_codes = set(CODE_RE.findall(catalog.read_text(encoding="utf-8")))
    json_codes, json_issues = load_reason_code_json(root)
    referenced: dict[str, list[str]] = {}
    issues: list[str] = json_issues[:]

    if json_codes:
        for code in sorted(catalog_codes - set(json_codes)):
            issues.append(f"references/reason_code_catalog.md defines `{code}` but assets/reason_codes.json does not")
        for code in sorted(set(json_codes) - catalog_codes):
            issues.append(f"assets/reason_codes.json defines `{code}` but reason_code_catalog.md does not")

    for path in iter_reference_files(root):
        rel = str(path.relative_to(root))
        codes = sorted(set(CODE_RE.findall(path.read_text(encoding="utf-8", errors="ignore"))))
        if codes:
            referenced[rel] = codes
        for code in codes:
            if code not in catalog_codes:
                issues.append(f"{rel}: undefined reason_code `{code}`")

    payload = {
        "ok": not issues,
        "defined_count": len(catalog_codes),
        "machine_defined_count": len(json_codes),
        "referenced_files": referenced,
        "issues": issues,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " reason codes")
        for issue in issues:
            print(f"  - {issue}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
