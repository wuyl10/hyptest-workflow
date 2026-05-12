#!/usr/bin/env python3
"""Build a read-only preflight pack before generating a hyptest case."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from skill_config import (
    CANONICAL_ENV_NAMES,
    apply_env_overrides,
    default_spec_profile,
    env_override_args,
    process_env_value,
    resolve_path,
)
from workflow_paths import cache_file


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent
CACHE_VERSION = 1
ENV_FINGERPRINT_KEYS = list(CANONICAL_ENV_NAMES)
SCRIPT_FINGERPRINT_RELS = [
    "case_preflight_pack.py",
    "repo_evidence_index.py",
    "find_similar_cases.py",
    "check_env.py",
    "repo_snapshot.py",
    "resolve_spec_profile.py",
    "validate_task_request.py",
    "similar_case_cache.py",
    "similar_case_ranker.py",
    "similar_case_render.py",
    "similar_case_terms.py",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect task/profile/env/similar-case context before writing a case."
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--test-point-file", required=True, help="Path to test_point markdown file.")
    parser.add_argument("--platform", default="spike", choices=["spike", "linknan"], help="Target platform.")
    default_profile = default_spec_profile()
    parser.add_argument(
        "--spec-profile",
        default=default_profile,
        help=f"Spec profile name/path. Defaults to {default_profile} from the profile registry.",
    )
    parser.add_argument(
        "--task-mode",
        default="new-case-only",
        choices=[
            "fix-case",
            "new-case-only",
            "preflight-only",
            "run-only",
            "supplement-existing-point",
            "triage-only",
            "writeback-only",
        ],
        help="Workflow task mode.",
    )
    parser.add_argument("--new-case-count", default="1", help="New case count or range.")
    parser.add_argument(
        "--coverage-scope",
        choices=["file", "repo"],
        help=(
            "Coverage scope. Defaults from --task-mode: repo for new-case-only, "
            "file for supplement-existing-point, otherwise repo."
        ),
    )
    parser.add_argument("--case-name", help="Optional target case name.")
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="Extra similar-case query term; can be repeated.",
    )
    parser.add_argument(
        "--heading-pattern",
        help="Limit --from-file extraction to matching markdown heading(s).",
    )
    parser.add_argument(
        "--section-index",
        type=int,
        help="Select a specific markdown heading section for term extraction.",
    )
    parser.add_argument("--similar-limit", type=int, default=3, help="Similar cases to keep.")
    parser.add_argument(
        "--no-env",
        action="store_true",
        help="Skip platform environment check.",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help=(
            "Environment override for nested checks, e.g. --env HYPTEST_SPIKE_BIN=/path/to/spike. "
            "Can be repeated."
        ),
    )
    parser.add_argument(
        "--no-pack-cache",
        action="store_true",
        help="Disable the preflight pack cache. The nested similar-case cache remains controlled separately.",
    )
    parser.add_argument(
        "--pack-cache-dir",
        help="Override preflight pack cache directory. Default: <repo-root>/.hyptest_workflow_skill/cache/preflight_pack",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    parser.add_argument("--md-out", help="Write Markdown report to this path.")
    parser.add_argument("--json-out", help="Write JSON report to this path.")
    return parser.parse_args()


def run_json(command: list[str], *, cwd: Path = SKILL_ROOT) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    duration_seconds = round(time.monotonic() - started, 3)
    payload: dict[str, Any]
    try:
        payload = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        payload = {}
    return {
        "ok": completed.returncode == 0,
        "returncode": completed.returncode,
        "duration_seconds": duration_seconds,
        "command": " ".join(command),
        "stdout_summary": summarize_text(completed.stdout),
        "stderr_summary": summarize_text(completed.stderr),
        "payload": compact_payload(Path(command[1]).name if len(command) > 1 else "", payload),
    }


def summarize_text(text: str, limit: int = 1200) -> str:
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[:limit].rstrip() + "\n..."


def compact_payload(script_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        return {}

    if script_name == "find_similar_cases.py":
        compact_results = []
        for item in payload.get("results", [])[:5]:
            compact_results.append(
                {
                    "case_name": item.get("case_name"),
                    "file": item.get("file"),
                    "line": item.get("line"),
                    "register_status": item.get("register_status"),
                    "symbol_kind": item.get("symbol_kind"),
                    "score": item.get("score"),
                    "matched_terms": item.get("matched_terms", [])[:12],
                    "focus_weighted_ratio": item.get("focus_weighted_ratio"),
                    "reference_role": item.get("reference_role"),
                }
            )
        return {
            "repo_root": payload.get("repo_root"),
            "query_terms": payload.get("query_terms", []),
            "focus_terms": payload.get("focus_terms", []),
            "searched_case_count": payload.get("searched_case_count"),
            "result_count": payload.get("result_count"),
            "cache": payload.get("cache"),
            "retrieval_status": payload.get("retrieval_status"),
            "retrieval_reason": payload.get("retrieval_reason"),
            "retrieval_quality": payload.get("retrieval_quality"),
            "fallback_plan": payload.get("fallback_plan", []),
            "top_results": compact_results,
            "reading_pack": payload.get("reading_pack", ""),
        }

    if script_name == "check_env.py":
        return {
            "ok": payload.get("ok"),
            "issues": payload.get("issues", []),
            "warnings": payload.get("warnings", []),
            "env_checks": [
                {
                    "name": item.get("name"),
                    "ok": item.get("ok"),
                    "required_for_task": item.get("required_for_task"),
                    "value": item.get("value"),
                    "gcc": item.get("gcc"),
                    "gcc_path": item.get("gcc_path"),
                }
                for item in payload.get("env_checks", [])
            ],
        }

    return payload


def read_text(path: Path, limit: int = 2400) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n..."


def first_existing_lines(path: Path, patterns: list[str], limit: int = 12) -> list[str]:
    if not path.is_file():
        return []
    lines: list[str] = []
    needles = [pattern.lower() for pattern in patterns if pattern]
    for index, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        lower = line.lower()
        if any(needle in lower for needle in needles):
            lines.append(f"{path.name}:{index}: {line.rstrip()}")
            if len(lines) >= limit:
                break
    return lines


def fingerprint_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    stat = path.stat()
    return {
        "path": str(path),
        "mtime_ns": stat.st_mtime_ns,
        "size": stat.st_size,
    }


def source_fingerprint(repo_root: Path, test_point_file: Path) -> dict[str, Any]:
    paths: list[Path] = []
    for rel in ("ai_test_cases", "manual_test_cases", "test_point"):
        root = repo_root / rel
        if root.is_dir():
            paths.extend(sorted(root.rglob("*.c" if rel != "test_point" else "*.md")))
    for rel in ("test_register.c",):
        path = repo_root / rel
        if path.is_file():
            paths.append(path)
    if test_point_file.is_file() and test_point_file not in paths:
        paths.append(test_point_file)

    digest = hashlib.sha256()
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for path in sorted(paths):
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            rel = str(resolved.relative_to(repo_root))
        except ValueError:
            rel = str(resolved)
        stat = resolved.stat()
        entry = {
            "path": rel,
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
        entries.append(entry)
        digest.update(rel.encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))

    return {
        "version": CACHE_VERSION,
        "digest": digest.hexdigest(),
        "entries": entries,
    }


def files_fingerprint(paths: list[Path]) -> dict[str, Any]:
    digest = hashlib.sha256()
    entries: list[dict[str, Any]] = []
    for path in sorted(path.resolve() for path in paths if path.is_file()):
        stat = path.stat()
        entry = {
            "path": str(path),
            "mtime_ns": stat.st_mtime_ns,
            "size": stat.st_size,
        }
        entries.append(entry)
        digest.update(str(path).encode("utf-8"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
        digest.update(str(stat.st_size).encode("ascii"))
    return {
        "digest": digest.hexdigest(),
        "entries": entries,
    }


def resolve_profile_path(spec_profile: str) -> Path | None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_DIR / "resolve_spec_profile.py"),
            "--spec-profile",
            spec_profile,
            "--json",
        ],
        cwd=str(SKILL_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    raw_path = payload.get("path")
    return resolve_path(raw_path) if raw_path else None


def script_fingerprint(spec_profile: str) -> dict[str, Any]:
    paths = [SCRIPT_DIR / rel for rel in SCRIPT_FINGERPRINT_RELS]
    paths.extend(
        [
            SKILL_ROOT / "references/spec_profiles/index.json",
            SKILL_ROOT / "assets/script_manifest.json",
        ]
    )
    profile_path = resolve_profile_path(spec_profile)
    if profile_path:
        paths.append(profile_path)
    return files_fingerprint(paths)


def env_fingerprint() -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in ENV_FINGERPRINT_KEYS:
        values[key] = process_env_value(key)
    prefix = process_env_value("CROSS_COMPILE") or "riscv64-unknown-elf-"
    values["toolchain_gcc"] = f"{prefix}gcc"
    values["toolchain_gcc_path"] = shutil.which(f"{prefix}gcc") or ""
    values["PATH_digest"] = hashlib.sha256(os.environ.get("PATH", "").encode("utf-8")).hexdigest()
    digest = hashlib.sha256(
        json.dumps(values, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return {
        "digest": digest,
        "values": values,
    }


def infer_coverage_scope(task_mode: str, explicit_scope: str | None) -> str:
    if explicit_scope:
        return explicit_scope
    if task_mode == "supplement-existing-point":
        return "file"
    if task_mode == "preflight-only":
        return "repo"
    return "repo"


def request_fingerprint(
    args: argparse.Namespace,
    repo_root: Path,
    test_point_file: Path,
    coverage_scope: str,
) -> dict[str, Any]:
    return {
        "version": CACHE_VERSION,
        "repo_root": str(repo_root),
        "test_point_file": str(test_point_file),
        "platform": args.platform,
        "spec_profile": args.spec_profile,
        "task_mode": args.task_mode,
        "new_case_count": args.new_case_count,
        "coverage_scope": coverage_scope,
        "case_name": args.case_name,
        "query": list(args.query),
        "heading_pattern": args.heading_pattern,
        "section_index": args.section_index,
        "similar_limit": args.similar_limit,
        "no_env": bool(args.no_env),
        "env_overrides": dict(args.env_overrides),
        "sources": source_fingerprint(repo_root, test_point_file),
        "skill_scripts": script_fingerprint(args.spec_profile),
        "environment": {} if args.no_env else env_fingerprint(),
    }


def pack_cache_path(repo_root: Path, args: argparse.Namespace, fingerprint: dict[str, Any]) -> Path:
    cache_root = (
        Path(args.pack_cache_dir).expanduser().resolve()
        if args.pack_cache_dir
        else cache_file(repo_root, "preflight_pack")
    )
    digest = hashlib.sha256(
        json.dumps(fingerprint, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return cache_root / f"{digest}.json"


def load_pack_cache(path: Path, fingerprint: dict[str, Any]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if payload.get("fingerprint") != fingerprint:
        return None
    report = payload.get("report")
    if not isinstance(report, dict):
        return None
    report["cache"] = {
        "enabled": True,
        "hit": True,
        "path": str(path),
        "fingerprint_digest": fingerprint.get("sources", {}).get("digest"),
        "script_digest": fingerprint.get("skill_scripts", {}).get("digest"),
        "environment_digest": fingerprint.get("environment", {}).get("digest"),
    }
    return report


def write_pack_cache(path: Path, fingerprint: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    cache_info = {
        "enabled": True,
        "hit": False,
        "path": str(path),
        "fingerprint_digest": fingerprint.get("sources", {}).get("digest"),
        "script_digest": fingerprint.get("skill_scripts", {}).get("digest"),
        "environment_digest": fingerprint.get("environment", {}).get("digest"),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        cache_report = json.loads(json.dumps(report, ensure_ascii=False))
        cache_report["cache"] = cache_info
        path.write_text(
            json.dumps(
                {
                    "fingerprint": fingerprint,
                    "report": cache_report,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        cache_info["write_error"] = str(exc)
    return cache_info


def run_commands_parallel(commands: dict[str, list[str]]) -> dict[str, Any]:
    results: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(len(commands), 5))) as executor:
        future_to_name = {
            executor.submit(run_json, command): name
            for name, command in commands.items()
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            results[name] = future.result()
    return {name: results[name] for name in commands}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    started = time.monotonic()
    repo_root = resolve_path(args.repo_root)
    test_point_file = resolve_path(args.test_point_file)
    coverage_scope = infer_coverage_scope(args.task_mode, args.coverage_scope)
    fingerprint = request_fingerprint(args, repo_root, test_point_file, coverage_scope)
    cache_path = pack_cache_path(repo_root, args, fingerprint)
    if not args.no_pack_cache:
        cached = load_pack_cache(cache_path, fingerprint)
        if cached is not None:
            return cached

    validate_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "validate_task_request.py"),
        "--repo-root",
        str(repo_root),
        "--test-point-file",
        str(test_point_file),
        "--platform",
        args.platform,
        "--spec-profile",
        args.spec_profile,
        "--task-mode",
        args.task_mode,
        "--new-case-count",
        args.new_case_count,
        "--coverage-scope",
        coverage_scope,
        "--json",
    ]
    validate_cmd.extend(env_override_args(args.env_overrides))
    if args.case_name:
        validate_cmd.extend(["--case-name", args.case_name])

    similar_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "find_similar_cases.py"),
        "--repo-root",
        str(repo_root),
        "--from-file",
        str(test_point_file),
        "--assert-only",
        "--emit-reading-pack",
        "--explain-score",
        "--limit",
        str(args.similar_limit),
        "--json",
    ]
    for query in args.query:
        similar_cmd.extend(["--query", query])
    if args.heading_pattern:
        similar_cmd.extend(["--heading-pattern", args.heading_pattern])
    if args.section_index is not None:
        similar_cmd.extend(["--section-index", str(args.section_index)])

    env_cmd = [
        sys.executable,
        str(SCRIPT_DIR / "check_env.py"),
        "--repo-root",
        str(repo_root),
        "--platform",
        args.platform,
        "--task-mode",
        args.task_mode,
        "--json",
    ]
    env_cmd.extend(env_override_args(args.env_overrides))

    result: dict[str, Any] = {
        "repo_root": str(repo_root),
        "test_point_file": str(test_point_file),
        "platform": args.platform,
        "spec_profile": args.spec_profile,
        "task_mode": args.task_mode,
        "new_case_count": args.new_case_count,
        "coverage_scope": coverage_scope,
        "case_name": args.case_name,
        "commands": {},
        "target_test_point_excerpt": read_text(test_point_file),
    }

    commands = {
        "task_request": validate_cmd,
        "repo_snapshot": [
            sys.executable,
            str(SCRIPT_DIR / "repo_snapshot.py"),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
        "repo_evidence_index": [
            sys.executable,
            str(SCRIPT_DIR / "repo_evidence_index.py"),
            "--repo-root",
            str(repo_root),
            "--json",
        ],
        "spec_profile": [
            sys.executable,
            str(SCRIPT_DIR / "resolve_spec_profile.py"),
            "--spec-profile",
            args.spec_profile,
            "--json",
        ],
        "similar_cases": similar_cmd,
    }
    for query in args.query:
        commands["repo_evidence_index"].extend(["--query", query])
    if not args.no_env:
        commands["platform_env"] = env_cmd
    result["commands"] = run_commands_parallel(commands)

    query_terms = list(args.query)
    if args.case_name:
        query_terms.append(args.case_name)
    result["test_point_hits"] = first_existing_lines(test_point_file, query_terms)

    critical_steps = [
        "task_request",
        "repo_snapshot",
        "repo_evidence_index",
        "spec_profile",
        "similar_cases",
    ]
    if not args.no_env:
        critical_steps.append("platform_env")
    result["ok"] = all(result["commands"][name]["ok"] for name in critical_steps)
    result["timing"] = build_timing(result["commands"], started)
    result["cache"] = {
        "enabled": not args.no_pack_cache,
        "hit": False,
        "path": str(cache_path),
        "fingerprint_digest": fingerprint.get("sources", {}).get("digest"),
        "script_digest": fingerprint.get("skill_scripts", {}).get("digest"),
        "environment_digest": fingerprint.get("environment", {}).get("digest"),
    }
    result["next_steps"] = [
        "Use the reading_pack from similar_cases as the reference set before writing code.",
        "Keep new_case_count=1 for the fastest high-quality loop unless the task explicitly asks for more.",
        "After editing, run case_postcheck_pack.py to collect lint/writeback/artifact/log evidence.",
    ]
    if not args.no_pack_cache:
        result["cache"] = write_pack_cache(cache_path, fingerprint, result)
    return result


def build_timing(commands: dict[str, Any], started: float) -> dict[str, Any]:
    by_step = {
        name: item.get("duration_seconds")
        for name, item in commands.items()
        if item.get("duration_seconds") is not None
    }
    slowest = sorted(
        by_step.items(),
        key=lambda item: float(item[1] or 0),
        reverse=True,
    )[:5]
    return {
        "total_seconds": round(time.monotonic() - started, 3),
        "by_step": by_step,
        "slowest_steps": [{"name": name, "seconds": seconds} for name, seconds in slowest],
    }


def summarize_command(name: str, item: dict[str, Any]) -> str:
    status = "PASS" if item.get("ok") else "FAIL"
    return f"- {status} `{name}`: `{item.get('command', '')}`"


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# hyptest case preflight pack",
        "",
        f"- HYPTEST_HOME: `{report['repo_root']}`",
        f"- test_point_file: `{report['test_point_file']}`",
        f"- platform: `{report['platform']}`",
        f"- spec_profile: `{report['spec_profile']}`",
        f"- task_mode: `{report['task_mode']}`",
        f"- new_case_count: `{report['new_case_count']}`",
        f"- coverage_scope: `{report['coverage_scope']}`",
        f"- overall: `{'PASS' if report['ok'] else 'FAIL'}`",
        "",
        "## Checks",
        "",
    ]
    for name, item in report["commands"].items():
        lines.append(summarize_command(name, item))
    lines.extend(["", "## Timing", ""])
    timing = report.get("timing", {})
    lines.append(f"- total_seconds: `{timing.get('total_seconds', '-')}`")
    by_step = timing.get("by_step") or {}
    if by_step:
        lines.append("- by_step:")
        for name, seconds in by_step.items():
            lines.append(f"  - {name}: `{seconds}` seconds")
    slowest = timing.get("slowest_steps", [])
    if slowest:
        lines.append("- slowest_steps:")
    for item in timing.get("slowest_steps", []):
        lines.append(f"  - {item['name']}: `{item['seconds']}` seconds")
    cache = report.get("cache", {})
    if cache:
        lines.extend(["", "## Cache", ""])
        lines.append(f"- enabled: `{cache.get('enabled')}`")
        lines.append(f"- hit: `{cache.get('hit')}`")
        lines.append(f"- path: `{cache.get('path')}`")
    lines.extend(["", "## Similar Case Reading Pack", ""])
    similar = report["commands"].get("similar_cases", {}).get("payload", {})
    reading_pack = similar.get("reading_pack")
    if reading_pack:
        lines.append(str(reading_pack))
    else:
        lines.append("_No reading pack generated._")
    repo_index = report["commands"].get("repo_evidence_index", {}).get("payload", {})
    if repo_index:
        lines.extend(["", "## Repo Evidence Index", ""])
        summary = repo_index.get("summary", {})
        cache = repo_index.get("cache", {})
        lines.append(f"- cache_hit: `{cache.get('hit')}`")
        lines.append(f"- case_count: `{summary.get('case_count')}`")
        lines.append(f"- test_point_entry_count: `{summary.get('test_point_entry_count')}`")
        hits = repo_index.get("test_point_hits", [])
        if hits:
            lines.append("- test_point hits:")
            for hit in hits[:10]:
                lines.append(f"  - `{hit.get('file')}:{hit.get('line')}` {hit.get('heading')}")
        else:
            lines.append("- test_point hits: `none`")
    lines.extend(["", "## Target Test Point Excerpt", "", "```text"])
    lines.append(str(report.get("target_test_point_excerpt", "")).rstrip())
    lines.extend(["```", "", "## Next Steps", ""])
    for step in report.get("next_steps", []):
        lines.append(f"- {step}")
    lines.append("")
    return "\n".join(lines)


def write_outputs(report: dict[str, Any], args: argparse.Namespace) -> None:
    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        path = Path(args.md_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(report), encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        args.env_overrides = apply_env_overrides(args.env)
    except ValueError as exc:
        print(f"invalid --env: {exc}", file=sys.stderr)
        return 2
    report = build_report(args)
    write_outputs(report, args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(report))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
