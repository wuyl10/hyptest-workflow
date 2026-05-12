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
    ".hyptest_workflow_skill/",
    "**/.hyptest_workflow_skill/",
]

NONCURRENT_CASE_DIR = "individual" + "_tests"
NONCURRENT_SPIKE_BIN_FIELD = "spike" + "_bin"
NONCURRENT_XIANGSHAN_PLATFORM = "--platform " + "xiangshan"
NONCURRENT_XIANGSHAN_PLAT = "--plat " + "xiangshan"
DEFAULT_PROFILE_LITERAL = "nhv5" + "_1_ap"
PUBLIC_ENV_DOCS = [
    "README.md",
    "SKILL.md",
    "references/task_input_schema.md",
    "references/quick_execution.md",
    "references/repo_layout.md",
]
CURRENT_PROMPT_ENV_FORBIDDEN_TERMS = [
    ("HYPTEST_REPO", "repo environment variable"),
    ("HYPTEST_NANHU_HOME", "standalone Nanhu environment variable"),
    ("NANHU_HOME", "standalone Nanhu environment variable"),
    ("ignored legacy", "compatibility warning text"),
    ("accepted for compatibility", "prompt compatibility text"),
]
REMOVED_PROMPT_FIELD_PATTERNS = [
    (re.compile(r"(?mi)^\s*(?:[-*]\s*)?repo_root\s*:"), "prompt field `repo_root:`"),
    (re.compile(r"(?mi)^\s*(?:[-*]\s*)?SPIKE_BIN\s*:"), "bare prompt field `SPIKE_BIN:`"),
    (re.compile(r"(?mi)^\s*(?:[-*]\s*)?LINKNAN_HOME\s*:"), "bare prompt field `LINKNAN_HOME:`"),
    (re.compile(r"(?mi)^\s*(?:[-*]\s*)?DIFFTEST_REF_SO\s*:"), "bare prompt field `DIFFTEST_REF_SO:`"),
]


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
    command_index_text = read(root, "references/command_index.md")
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
    if "<!-- BEGIN GENERATED COMMANDS -->" not in command_index_text:
        issues.append("command_index.md missing generated command block markers")
    if NONCURRENT_CASE_DIR in "\n".join([skill_text, readme_text, repo_layout_text]):
        issues.append(f"skill docs still mention non-current artifact directory `{NONCURRENT_CASE_DIR}`")
    generic_docs = [
        "SKILL.md",
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

    for rel in PUBLIC_ENV_DOCS:
        text = read(root, rel)
        for needle, label in CURRENT_PROMPT_ENV_FORBIDDEN_TERMS:
            if needle in text:
                issues.append(f"public docs still mention {label}: `{needle}` in `{rel}`")
        for pattern, label in REMOVED_PROMPT_FIELD_PATTERNS:
            if pattern.search(text):
                issues.append(f"public docs still contain {label} in `{rel}`")

    profile_lines = re.findall(r"(?m)^\s*spec_profile:\s*(.+?)\s*$", readme_text)
    concrete_default_lines = [line for line in profile_lines if line == DEFAULT_PROFILE_LITERAL]
    if len(concrete_default_lines) != 1:
        issues.append(
            "README.md should keep exactly one concrete default profile example "
            f"`spec_profile: {DEFAULT_PROFILE_LITERAL}`; other occurrences should use "
            "`spec_profile: <当前项目 spec_profile>`"
        )

    for platform in ("spike", "linknan"):
        if not re.search(rf"(?m)^({platform})$", repo_layout_text):
            issues.append(f"repo_layout.md missing platform line `{platform}`")

    forbidden_patterns = [
        (NONCURRENT_CASE_DIR, "non-current ELF/ASM artifact directory"),
        (NONCURRENT_SPIKE_BIN_FIELD, "lowercase Spike binary field"),
        (NONCURRENT_XIANGSHAN_PLATFORM, "xiangshan platform value"),
        (NONCURRENT_XIANGSHAN_PLAT, "xiangshan plat value"),
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
