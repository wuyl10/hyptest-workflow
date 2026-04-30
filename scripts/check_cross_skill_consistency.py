#!/usr/bin/env python3
"""
Check consistency between hyptest-workflow and hyptest-failure-triage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from skill_config import TRIAGE_HANDOFF_SCHEMA, load_json_file


TRIAGE_REQUIRED_TERMS = [
    "stuck",
    "timeout",
    "difftest mismatch",
    "HIT GOOD TRAP",
    "FAILED",
    "FSDB",
    "50000 cycles no commit",
    "suspected RTL bug",
]

LEGACY_CASE_DIR = "individual" + "_tests"
LEGACY_SPIKE_BIN_FIELD = "spike" + "_bin"
LEGACY_XIANGSHAN_PLATFORM = "--platform " + "xiangshan"
LEGACY_XIANGSHAN_PLAT = "--plat " + "xiangshan"

FORBIDDEN_WORKFLOW_PATTERNS = [
    (LEGACY_CASE_DIR, "removed legacy ELF/ASM directory"),
    (LEGACY_SPIKE_BIN_FIELD, "old lowercase Spike binary field"),
    (LEGACY_XIANGSHAN_PLATFORM, "old xiangshan platform value"),
    (LEGACY_XIANGSHAN_PLAT, "old xiangshan plat value"),
]


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check cross-skill consistency with hyptest-failure-triage."
    )
    parser.add_argument(
        "--triage-skill-root",
        default=str(skill_root().parent / "hyptest-failure-triage"),
        help="Path to hyptest-failure-triage skill root.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read_all_text(root: Path) -> tuple[str, list[str]]:
    missing: list[str] = []
    chunks: list[str] = []
    if not root.is_dir():
        return "", [f"missing directory: {root}"]

    for rel in ["SKILL.md", "README.md"]:
        path = root / rel
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    references = root / "references"
    if references.is_dir():
        for path in sorted(references.rglob("*.md")):
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    else:
        missing.append(f"missing references directory: {references}")
    return "\n".join(chunks), missing


def main() -> int:
    args = parse_args()
    workflow_root = skill_root()
    triage_root = Path(args.triage_skill_root).expanduser().resolve()
    issues: list[str] = []
    warnings: list[str] = []

    triage_text, triage_missing = read_all_text(triage_root)
    issues.extend(triage_missing)
    lowered_triage = triage_text.lower()
    for term in TRIAGE_REQUIRED_TERMS:
        if term.lower() not in lowered_triage:
            issues.append(f"hyptest-failure-triage missing expected term `{term}`")

    workflow_handoff = workflow_root / "references/triage_handoff_schema.md"
    try:
        handoff_required_fields = [
            str(field)
            for field in load_json_file(TRIAGE_HANDOFF_SCHEMA).get("required_fields", [])
        ]
    except (OSError, json.JSONDecodeError, AttributeError) as exc:
        issues.append(f"failed to read triage handoff schema: {exc}")
        handoff_required_fields = []
    if not workflow_handoff.is_file():
        issues.append("workflow missing references/triage_handoff_schema.md")
    else:
        handoff_text = workflow_handoff.read_text(encoding="utf-8", errors="ignore")
        for field in handoff_required_fields:
            if field not in handoff_text:
                issues.append(f"triage_handoff_schema.md missing field `{field}`")
            if field not in triage_text:
                issues.append(f"hyptest-failure-triage docs do not mention handoff field `{field}`")

    workflow_docs: list[Path] = [workflow_root / "SKILL.md", workflow_root / "README.md"]
    workflow_docs.extend(sorted((workflow_root / "references").rglob("*.md")))
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8", errors="ignore")
        for path in workflow_docs
        if path.is_file()
    )
    for needle, label in FORBIDDEN_WORKFLOW_PATTERNS:
        if needle in workflow_text:
            issues.append(f"workflow docs contain forbidden {label}: {needle}")

    triage_repo_layout = triage_root / "references/repo_layout.md"
    if triage_repo_layout.is_file():
        triage_layout = triage_repo_layout.read_text(encoding="utf-8", errors="ignore")
        if "case_elf_asm/" not in triage_layout:
            warnings.append("hyptest-failure-triage repo_layout.md should mention current case_elf_asm/")
        if "legacy per-case ELF/ASM output" in triage_layout:
            warnings.append("hyptest-failure-triage repo_layout.md still documents removed legacy ELF/ASM directory")

    payload = {
        "ok": not issues,
        "workflow_root": str(workflow_root),
        "triage_skill_root": str(triage_root),
        "issues": issues,
        "warnings": warnings,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " cross-skill consistency")
        for issue in issues:
            print(f"  - {issue}")
        for warning in warnings:
            print(f"  warning: {warning}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
