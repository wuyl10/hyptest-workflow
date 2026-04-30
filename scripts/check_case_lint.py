#!/usr/bin/env python3
"""
Lightweight structural lint for hyptest case sources.

This is intentionally conservative: it checks harness-shape mistakes that are
cheap to detect before compile/run, while leaving semantic judgment to the
profile and the real simulator logs.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


CASE_NAME_RE = r"[A-Za-z_][A-Za-z0-9_]*"
FUNC_RE = re.compile(
    rf"^\s*(?:static\s+)?bool\s+({CASE_NAME_RE})\s*\(",
    re.MULTILINE,
)
REGISTER_RE = re.compile(rf"TEST_REGISTER\s*\(\s*({CASE_NAME_RE})\s*\)")
EMPTY_ASSERT_MESSAGE_RE = re.compile(r'TEST_ASSERT\s*\(\s*(?:""|NULL)\s*,')
ASSERT_MESSAGE_RE = re.compile(r'TEST_ASSERT\s*\(\s*"([^"]*)"\s*,')
TEST_END_NAME_RE = re.compile(r'TEST_END\s*\(\s*"([^"]+)"')
CASE_SOURCE_DIRS = ("ai_test_cases", "manual_test_cases")
WEAK_ASSERT_MESSAGES = {
    "fail",
    "failed",
    "error",
    "bad",
    "wrong",
    "check",
    "test",
    "assert",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lint hyptest case source structure.")
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Specific C source file to lint; can be repeated. Defaults to all case sources.",
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help="Lint only changed/untracked case source files under git, relative to repo-root.",
    )
    parser.add_argument(
        "--strict-case-end",
        action="store_true",
        help="Require every case-like bool function to contain exactly one TEST_END(...).",
    )
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Treat warnings as errors for stricter pre-submit checks.",
    )
    parser.add_argument(
        "--baseline",
        help=(
            "Optional JSON baseline of known issues. Baseline-matched issues are reported "
            "but do not affect ok/effective counts."
        ),
    )
    parser.add_argument(
        "--write-baseline",
        help="Write all currently found issues as a JSON baseline at this path.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def issue_key(issue: dict[str, object]) -> str:
    path = str(issue.get("path", ""))
    case = str(issue.get("case", ""))
    severity = str(issue.get("severity", ""))
    message = str(issue.get("message", ""))
    return f"{path}|{case}|{severity}|{message}"


def load_baseline(path: str | None) -> set[str]:
    if not path:
        return set()
    baseline_path = Path(path).expanduser()
    if not baseline_path.is_file():
        raise RuntimeError(f"baseline not found: {baseline_path}")
    payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    issue_keys = payload.get("issue_keys")
    if not isinstance(issue_keys, list):
        raise RuntimeError(f"baseline missing list field `issue_keys`: {baseline_path}")
    return {str(item) for item in issue_keys}


def write_baseline(path: str, issues: list[dict[str, object]]) -> None:
    baseline_path = Path(path).expanduser()
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    issue_keys = sorted({issue_key(issue) for issue in issues})
    payload = {
        "version": 1,
        "description": "Known check_case_lint issues. Regenerate intentionally after triage.",
        "issue_key_format": "path|case|severity|message",
        "issue_count": len(issue_keys),
        "issue_keys": issue_keys,
    }
    baseline_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def line_number(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def load_registration_status(repo_root: Path) -> dict[str, str]:
    status: dict[str, str] = {}
    register_path = repo_root / "test_register.c"
    if not register_path.is_file():
        return status

    for line in read_text(register_path).splitlines():
        match = REGISTER_RE.search(line)
        if not match:
            continue
        stripped = line.strip()
        status[match.group(1)] = "commented" if stripped.startswith("//") else "enabled"
    return status


def changed_case_files(repo_root: Path) -> list[Path]:
    git_dir = repo_root / ".git"
    if not git_dir.exists():
        raise RuntimeError("--changed-only requires repo-root to be a git worktree")

    commands = [
        ["git", "-C", str(repo_root), "diff", "--name-only", "--diff-filter=ACMRT"],
        ["git", "-C", str(repo_root), "diff", "--name-only", "--cached", "--diff-filter=ACMRT"],
        ["git", "-C", str(repo_root), "ls-files", "--others", "--exclude-standard"],
    ]
    rels: list[str] = []
    for command in commands:
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
        rels.extend(line.strip() for line in completed.stdout.splitlines() if line.strip())

    paths: list[Path] = []
    seen = set()
    for rel in rels:
        if not rel.endswith(".c"):
            continue
        if not rel.startswith("ai_test_cases/") and not rel.startswith("manual_test_cases/"):
            continue
        path = (repo_root / rel).resolve()
        if path.is_file() and path not in seen:
            seen.add(path)
            paths.append(path)
    return sorted(paths)


def source_files(repo_root: Path, files: list[str], *, changed_only: bool = False) -> list[Path]:
    if files:
        return [Path(raw).expanduser().resolve() for raw in files]

    if changed_only:
        return changed_case_files(repo_root)

    paths: list[Path] = []
    for rel in CASE_SOURCE_DIRS:
        root = repo_root / rel
        if root.is_dir():
            paths.extend(sorted(root.rglob("*.c")))
    return paths


def is_static_function(text: str, start: int, end: int) -> bool:
    return "static" in text[start:end]


def is_case_like(name: str, body: str, register_status: str) -> bool:
    return (
        register_status != "unregistered"
        or name.startswith(("ai_", "addr_", "csr_", "ebreak_", "stateen_", "vec_", "wfi_"))
        or "TEST_START(" in body
        or "TEST_END(" in body
    )


def is_weak_assert_message(message: str) -> bool:
    normalized = re.sub(r"[^a-z0-9_]+", " ", message.lower()).strip()
    if not normalized:
        return True
    if normalized in WEAK_ASSERT_MESSAGES:
        return True
    words = normalized.split()
    return len(words) == 1 and len(words[0]) <= 4


def lint_function(
    *,
    repo_root: Path,
    path: Path,
    text: str,
    match: re.Match[str],
    next_start: int,
    register_status: dict[str, str],
    strict_case_end: bool,
) -> list[dict[str, object]]:
    issues: list[dict[str, object]] = []
    name = match.group(1)
    body = text[match.start() : next_start]
    rel = str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path)
    line = line_number(text, match.start())
    static = is_static_function(text, match.start(), match.end())
    status = register_status.get(name, "unregistered")
    case_like = is_case_like(name, body, status)

    if static and "TEST_END(" not in body and "TEST_START(" not in body:
        return issues

    if strict_case_end and case_like and not static:
        test_end_count = body.count("TEST_END(")
        if test_end_count != 1:
            issues.append(
                {
                    "severity": "error",
                    "path": rel,
                    "line": line,
                    "case": name,
                    "message": f"case-like bool function should contain exactly one TEST_END(...), found {test_end_count}",
                }
            )
        test_start_count = body.count("TEST_START(")
        if test_start_count != 1:
            issues.append(
                {
                    "severity": "error",
                    "path": rel,
                    "line": line,
                    "case": name,
                    "message": f"case-like bool function should contain exactly one TEST_START(), found {test_start_count}",
                }
            )
        end_name_matches = TEST_END_NAME_RE.findall(body)
        if len(end_name_matches) == 1 and end_name_matches[0] != name:
            issues.append(
                {
                    "severity": "error",
                    "path": rel,
                    "line": line,
                    "case": name,
                    "message": f'TEST_END name "{end_name_matches[0]}" does not match function name "{name}"',
                }
            )

    if "excpt." in body and "TEST_SETUP_EXCEPT(" not in body:
        issues.append(
            {
                "severity": "warning",
                "path": rel,
                "line": line,
                "case": name,
                "message": "function reads excpt.* without a local TEST_SETUP_EXCEPT()",
            }
        )

    if case_like and not static and "TEST_ASSERT(" not in body:
        issues.append(
            {
                "severity": "warning",
                "path": rel,
                "line": line,
                "case": name,
                "message": "case-like bool function contains no TEST_ASSERT(...)",
            }
        )

    for assert_match in EMPTY_ASSERT_MESSAGE_RE.finditer(body):
        issues.append(
            {
                "severity": "error",
                "path": rel,
                "line": line_number(text, match.start() + assert_match.start()),
                "case": name,
                "message": "TEST_ASSERT message is empty or NULL",
            }
        )

    for assert_match in ASSERT_MESSAGE_RE.finditer(body):
        message = assert_match.group(1)
        if is_weak_assert_message(message):
            issues.append(
                {
                    "severity": "warning",
                    "path": rel,
                    "line": line_number(text, match.start() + assert_match.start()),
                    "case": name,
                    "message": f'TEST_ASSERT message "{message}" is too generic',
                }
            )

    return issues


def lint_source(
    repo_root: Path,
    path: Path,
    register_status: dict[str, str],
    *,
    strict_case_end: bool,
) -> dict[str, object]:
    text = read_text(path)
    rel = str(path.relative_to(repo_root)) if path.is_relative_to(repo_root) else str(path)
    issues: list[dict[str, object]] = []

    for register_match in REGISTER_RE.finditer(text):
        issues.append(
            {
                "severity": "error",
                "path": rel,
                "line": line_number(text, register_match.start()),
                "case": register_match.group(1),
                "message": "TEST_REGISTER belongs in test_register.c, not in a case source file",
            }
        )

    matches = list(FUNC_RE.finditer(text))
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        issues.extend(
            lint_function(
                repo_root=repo_root,
                path=path,
                text=text,
                match=match,
                next_start=next_start,
                register_status=register_status,
                strict_case_end=strict_case_end,
            )
        )

    return {
        "path": rel,
        "ok": not any(issue["severity"] == "error" for issue in issues),
        "issue_count": len(issues),
        "issues": issues,
    }


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).expanduser().resolve()
    try:
        baseline_keys = load_baseline(args.baseline)
    except (OSError, RuntimeError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    register_status = load_registration_status(repo_root)
    try:
        paths = source_files(repo_root, args.file, changed_only=args.changed_only)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    results = [
        lint_source(
            repo_root,
            path,
            register_status,
            strict_case_end=args.strict_case_end,
        )
        for path in paths
        if path.is_file()
    ]
    issues = [issue for result in results for issue in result["issues"]]
    if args.write_baseline:
        write_baseline(args.write_baseline, issues)

    baseline_ignored_count = 0
    for issue in issues:
        ignored = issue_key(issue) in baseline_keys
        issue["baseline_ignored"] = ignored
        if ignored:
            baseline_ignored_count += 1

    active_issues = [issue for issue in issues if not issue.get("baseline_ignored")]
    error_count = sum(1 for issue in active_issues if issue["severity"] == "error")
    warning_count = len(active_issues) - error_count
    effective_error_count = error_count + warning_count if args.warnings_as_errors else error_count

    for result in results:
        result_active_issues = [
            issue for issue in result["issues"] if not issue.get("baseline_ignored")
        ]
        result["active_issue_count"] = len(result_active_issues)
        result["baseline_ignored_count"] = sum(
            1 for issue in result["issues"] if issue.get("baseline_ignored")
        )
        result["ok"] = not any(issue["severity"] == "error" for issue in result_active_issues)

    payload = {
        "ok": effective_error_count == 0,
        "checked_file_count": len(results),
        "changed_only": args.changed_only,
        "warnings_as_errors": args.warnings_as_errors,
        "baseline": str(Path(args.baseline).expanduser()) if args.baseline else None,
        "baseline_ignored_count": baseline_ignored_count,
        "issue_count": len(issues),
        "active_issue_count": len(active_issues),
        "error_count": error_count,
        "warning_count": warning_count,
        "effective_error_count": effective_error_count,
        "results": results,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(("PASS" if payload["ok"] else "FAIL") + " case lint")
        print(
            f"checked_files={payload['checked_file_count']} "
            f"active_errors={error_count} active_warnings={payload['warning_count']} "
            f"baseline_ignored={baseline_ignored_count} "
            f"warnings_as_errors={args.warnings_as_errors}"
        )
        for issue in active_issues[:80]:
            print(
                f"  - {issue['severity']}: {issue['path']}:{issue['line']} "
                f"{issue.get('case', '-')}: {issue['message']}"
            )
        if len(active_issues) > 80:
            print(f"  ... {len(active_issues) - 80} more active issue(s)")
    return 0 if effective_error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
