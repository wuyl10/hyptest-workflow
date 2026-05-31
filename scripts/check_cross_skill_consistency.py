#!/usr/bin/env python3
"""
Check consistency between hyptest-workflow and hyptest-failure-triage.
"""

from __future__ import annotations

import argparse
import json
import re
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

TRIAGE_OPTIONAL_HANDOFF_TERMS = [
    "waveform_context",
    "waveform_path",
    "rtl_root",
    "top_module",
    "debug_target",
    "time_window",
    "expected_behavior",
    "observed_behavior",
    "suggested_waveform_report",
]

WAVEFORM_DEBUG_REQUIRED_TERMS = [
    "report.md",
    "python3 <WORKDIR>/query_hierarchy.py",
    "WAVEFORM_DEBUG",
]

NONCURRENT_CASE_DIR = "individual" + "_tests"
NONCURRENT_SPIKE_BIN_FIELD = "spike" + "_bin"
NONCURRENT_XIANGSHAN_PLATFORM = "--platform " + "xiangshan"
NONCURRENT_XIANGSHAN_PLAT = "--plat " + "xiangshan"
FIXED_SELFCHECK_LIST = "selfcheck" + "_fail.txt"
FIXED_STUCK_LIST = "stuck" + ".txt"
FIXED_MISMATCH_LIST = "difftest" + "_mismatch.txt"
UNCONDITIONAL_SUBAGENT_PHRASE = "Use a " + "subagent if"
SKILL_LEVEL_QUERY_HELPER_CMD = (
    "python3 "
    + "$"
    + "WAVEFORM_DEBUG"
    + "/scripts/query_hierarchy.py"
)

FORBIDDEN_WORKFLOW_PATTERNS = [
    (NONCURRENT_CASE_DIR, "non-current ELF/ASM artifact directory"),
    (NONCURRENT_SPIKE_BIN_FIELD, "lowercase Spike binary field"),
    (NONCURRENT_XIANGSHAN_PLATFORM, "xiangshan platform value"),
    (NONCURRENT_XIANGSHAN_PLAT, "xiangshan plat value"),
    ("HYPTEST_" + "SKILL_HOME", "ambiguous skill-home environment variable"),
]

FORBIDDEN_TRIAGE_PATTERNS = [
    ("HYPTEST_" + "SKILL_HOME", "ambiguous skill-home environment variable"),
]

FORBIDDEN_TRIAGE_FIXED_LIST_PATTERNS = [
    (FIXED_SELFCHECK_LIST, "fixed selfcheck failure-list filename"),
    (FIXED_STUCK_LIST, "fixed stuck failure-list filename"),
    (FIXED_MISMATCH_LIST, "fixed mismatch failure-list filename"),
]


def read_selected_text(root: Path, rels: list[str]) -> tuple[str, list[str]]:
    chunks: list[str] = []
    missing: list[str] = []
    for rel in rels:
        path = root / rel
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
        else:
            missing.append(f"missing file: {path}")
    return "\n".join(chunks), missing


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
    parser.add_argument(
        "--waveform-skill-root",
        default=str(skill_root().parent / "waveform-debug"),
        help="Path to waveform-debug skill root.",
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
    waveform_root = Path(args.waveform_skill_root).expanduser().resolve()
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
        for field in TRIAGE_OPTIONAL_HANDOFF_TERMS:
            if field not in handoff_text:
                issues.append(f"triage_handoff_schema.md missing optional handoff field `{field}`")
            if field not in triage_text:
                issues.append(f"hyptest-failure-triage docs do not mention optional handoff field `{field}`")

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

    for needle, label in FORBIDDEN_TRIAGE_PATTERNS:
        if needle in triage_text:
            issues.append(f"hyptest-failure-triage docs contain forbidden {label}: {needle}")
    for needle, label in FORBIDDEN_TRIAGE_FIXED_LIST_PATTERNS:
        if needle in triage_text:
            issues.append(f"hyptest-failure-triage docs imply forbidden {label}: {needle}")
    if "Do not infer failure-list paths from default names" not in triage_text:
        issues.append("hyptest-failure-triage docs must forbid default failure-list path inference")

    triage_repo_layout = triage_root / "references/repo_layout.md"
    if triage_repo_layout.is_file():
        triage_layout = triage_repo_layout.read_text(encoding="utf-8", errors="ignore")
        if "case_elf_asm/" not in triage_layout:
            warnings.append("hyptest-failure-triage repo_layout.md should mention current case_elf_asm/")
        if ".tmp/hyptest_compile/" not in triage_layout:
            issues.append("hyptest-failure-triage repo_layout.md missing current .tmp/hyptest_compile/")
        if ".tmp/result_log/" not in triage_layout:
            issues.append("hyptest-failure-triage repo_layout.md missing current .tmp/result_log/")
        if re.search(r"(?m)^\s*result_log/\s*$", triage_layout):
            issues.append("hyptest-failure-triage repo_layout.md still lists removed root result_log/")

    waveform_text, waveform_missing = read_selected_text(
        waveform_root,
        [
            "SKILL.md",
            "lite.md",
            "full.md",
            "references/debug-patterns.md",
            "templates/workflow.lite.md",
            "templates/workflow.full.md",
        ],
    )
    issues.extend(waveform_missing)
    if waveform_text:
        for term in WAVEFORM_DEBUG_REQUIRED_TERMS:
            if term not in waveform_text:
                issues.append(f"waveform-debug docs missing expected term `{term}`")
        if "$HYPTEST_WORKFLOW_SKILL_HOME" in waveform_text:
            issues.append("waveform-debug docs must not use HYPTEST_WORKFLOW_SKILL_HOME")
        if "$HYPTEST_FAILURE_TRIAGE_SKILL_HOME" in waveform_text:
            issues.append("waveform-debug docs must not use HYPTEST_FAILURE_TRIAGE_SKILL_HOME")
        if UNCONDITIONAL_SUBAGENT_PHRASE in waveform_text:
            issues.append("waveform-debug docs contain unconditional subagent wording")
        if SKILL_LEVEL_QUERY_HELPER_CMD in waveform_text:
            warnings.append(
                "waveform-debug still mentions skill-level query_hierarchy.py; ensure it is fallback-only"
            )

    payload = {
        "ok": not issues,
        "workflow_root": str(workflow_root),
        "triage_skill_root": str(triage_root),
        "waveform_skill_root": str(waveform_root),
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
