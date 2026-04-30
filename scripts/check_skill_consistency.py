#!/usr/bin/env python3
"""
Check cross-file consistency for hyptest-workflow skill metadata and docs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from skill_config import manifest_scripts


REQUIRED_GITIGNORE_PATTERNS = [
    "__pycache__/",
    "**/__pycache__/",
    "*.py[cod]",
    ".hyptest_skill_cache/",
    "**/.hyptest_skill_cache/",
    ".hyptest_skill_tmp/",
    "**/.hyptest_skill_tmp/",
]

LEGACY_CASE_DIR = "individual" + "_tests"
LEGACY_SPIKE_BIN_FIELD = "spike" + "_bin"
LEGACY_XIANGSHAN_PLATFORM = "--platform " + "xiangshan"
LEGACY_XIANGSHAN_PLAT = "--plat " + "xiangshan"
DEFAULT_PROFILE_LITERAL = "nhv5" + "_1_ap"


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check hyptest-workflow skill consistency.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8", errors="ignore")


def bundled_resources(root: Path, skill_text: str) -> set[str]:
    texts = [skill_text]
    resource_index = root / "references/resource_index.md"
    if resource_index.is_file():
        texts.append(resource_index.read_text(encoding="utf-8", errors="ignore"))
    return set(
        re.findall(
            r"- `(references/[^`]+|scripts/[^`]+|assets/[^`]+)`",
            "\n".join(texts),
        )
    )


def main() -> int:
    args = parse_args()
    root = skill_root()
    issues: list[str] = []

    skill_text = read(root, "SKILL.md")
    readme_text = read(root, "README.md")
    gitignore_text = read(root, ".gitignore")
    repo_layout_text = read(root, "references/repo_layout.md")
    self_check_text = read(root, "scripts/self_check.py")
    resources = bundled_resources(root, skill_text)

    self_check_scripts = manifest_scripts(self_check_only=True)
    public_scripts = manifest_scripts(public_only=True)

    if "assets/script_manifest.json" not in resources:
        issues.append("resource index missing `assets/script_manifest.json`")

    for rel in self_check_scripts:
        if rel not in resources:
            issues.append(f"resource index missing `{rel}`")
        if rel not in self_check_text and rel != "scripts/eval_find_similar_cases.py":
            issues.append(f"self_check.py does not mention `{rel}`")

    for rel in resources:
        if "<" in rel or ">" in rel:
            continue
        if not (root / rel).exists():
            issues.append(f"resource does not exist: `{rel}`")

    for rel in public_scripts:
        if (root / rel).exists() and rel not in resources:
            issues.append(f"public script missing from resource index: `{rel}`")

    manifest_set = set(public_scripts)
    for path in sorted((root / "scripts").glob("*.py")):
        rel = str(path.relative_to(root))
        if rel not in manifest_set:
            issues.append(f"script missing from assets/script_manifest.json: `{rel}`")

    for pattern in REQUIRED_GITIGNORE_PATTERNS:
        if pattern not in gitignore_text:
            issues.append(f".gitignore missing `{pattern}`")

    if "case_elf_asm/" not in repo_layout_text:
        issues.append("repo_layout.md missing generated directory `case_elf_asm/`")
    if "references/task_input_schema.md" not in readme_text + skill_text:
        issues.append("task input schema missing from README/SKILL entry points")
    if "<!-- BEGIN GENERATED COMMANDS -->" not in readme_text:
        issues.append("README missing generated command block markers")
    if LEGACY_CASE_DIR in "\n".join([skill_text, readme_text, repo_layout_text]):
        issues.append(f"skill docs still mention removed legacy directory `{LEGACY_CASE_DIR}`")
    generic_docs = [
        "SKILL.md",
        "README.md",
        "agents/openai.yaml",
        "references/spec_and_model_limits.md",
        "references/task_input_schema.md",
        "references/quality_gate.md",
        "references/quick_execution.md",
        "references/submission_card.md",
        "references/maintainer_guide.md",
        "references/triage_handoff_schema.md",
        "references/resource_index.md",
    ]
    for rel in generic_docs:
        if DEFAULT_PROFILE_LITERAL in read(root, rel):
            issues.append(f"generic skill entry contains concrete default profile `{DEFAULT_PROFILE_LITERAL}`: `{rel}`")

    for platform in ("spike", "linknan"):
        if not re.search(rf"(?m)^({platform})$", repo_layout_text):
            issues.append(f"repo_layout.md missing platform line `{platform}`")

    forbidden_patterns = [
        (LEGACY_CASE_DIR, "removed legacy ELF/ASM directory"),
        (LEGACY_SPIKE_BIN_FIELD, "old lowercase Spike binary field"),
        (LEGACY_XIANGSHAN_PLATFORM, "old xiangshan platform value"),
        (LEGACY_XIANGSHAN_PLAT, "old xiangshan plat value"),
    ]
    for needle, label in forbidden_patterns:
        haystack = "\n".join([skill_text, readme_text, repo_layout_text])
        if needle in haystack:
            issues.append(f"forbidden {label}: {needle}")

    payload = {
        "ok": not issues,
        "issues": issues,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " skill consistency")
        for issue in issues:
            print(f"  - {issue}")
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
