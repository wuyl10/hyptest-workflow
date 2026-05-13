#!/usr/bin/env python3
"""Append/query local hyptest-workflow memory records."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from skill_config import default_spec_profile, resolve_path
from workflow_paths import workflow_memory_dir


DEFAULT_MEMORY_FILE = "events.jsonl"
ALLOWED_PHASES = (
    "preflight",
    "case_design",
    "uniqueness",
    "compile",
    "run",
    "postcheck",
    "triage",
    "writeback",
    "submission",
    "cleanup",
)
# Memory status enum.
# New entries should use one of the three current tiers:
#   - "info"     — agent auto-sunk fact observation, usable directly
#   - "fixed"    — human-confirmed experience (promoted from Manual_Reference)
#   - "obsolete" — stale (filtered out on read)
# "open" is kept ONLY for backwards compatibility with historical records;
# new code should never write status=open. Things that are "suspicious and
# pending human confirmation" belong in test_point/Manual_Reference.md, not
# in memory. Read paths (similar_case_render, find_similar_cases) treat
# historical "open" entries the same as "info" so old data stays visible.
ALLOWED_STATUSES = ("info", "fixed", "obsolete", "open")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Record and query local workflow memory. Memory is append-only evidence "
            "for future hints; it is not a tiering decision source."
        )
    )
    parser.add_argument("--repo-root", required=True, help="Path to hyptest repo root.")
    parser.add_argument("--memory-dir", help="Override memory directory. Default: <repo-root>/.hyptest_workflow_skill/memory")
    parser.add_argument("--file", default=DEFAULT_MEMORY_FILE, help=f"Memory JSONL file name. Default: {DEFAULT_MEMORY_FILE}")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    sub = parser.add_subparsers(dest="command", required=True)

    append = sub.add_parser("append", help="Append one memory record.")
    append.add_argument("--case", help="Case name.")
    append.add_argument("--module", help="Target module, e.g. memblock.")
    append.add_argument("--platform", choices=["spike", "linknan", "all"], help="Platform.")
    append.add_argument(
        "--spec-profile",
        default=default_spec_profile(),
        help=f"Spec profile. Defaults to {default_spec_profile()} from the profile registry.",
    )
    append.add_argument("--phase", choices=ALLOWED_PHASES, required=True, help="Workflow phase.")
    append.add_argument(
        "--status",
        choices=ALLOWED_STATUSES,
        default="info",
        help=(
            "Record status. Use 'info' for agent-sunk observations "
            "(default), 'fixed' for human-confirmed experience (promoted "
            "from Manual_Reference), or 'obsolete' to retire. 'open' is "
            "deprecated: suspicious/pending items go in "
            "test_point/Manual_Reference.md instead of memory."
        ),
    )
    append.add_argument("--symptom", required=True, help="Short failure/signal summary.")
    append.add_argument("--reason-code", action="append", default=[], help="Candidate/final reason_code; repeatable.")
    append.add_argument("--tag", action="append", default=[], help="Search tag; repeatable.")
    append.add_argument("--log", action="append", default=[], help="Relevant log/report path; repeatable.")
    append.add_argument("--source", action="append", default=[], help="Evidence source path; repeatable.")
    append.add_argument("--fix", help="Fix or mitigation summary.")
    append.add_argument("--note", help="Extra short note.")

    query = sub.add_parser("query", help="Query memory records.")
    query.add_argument("--case", help="Filter by case substring.")
    query.add_argument("--module", help="Filter by module.")
    query.add_argument("--platform", choices=["spike", "linknan", "all"], help="Filter by platform.")
    query.add_argument("--phase", choices=ALLOWED_PHASES, help="Filter by phase.")
    query.add_argument("--status", choices=ALLOWED_STATUSES, help="Filter by status.")
    query.add_argument("--term", action="append", default=[], help="Substring term to match in symptom/fix/note/tags.")
    query.add_argument("--limit", type=int, default=20, help="Maximum records to return.")

    summary = sub.add_parser("summarize", help="Summarize memory records.")
    summary.add_argument("--limit", type=int, default=10, help="Maximum top values per bucket.")
    return parser.parse_args()


def memory_path(args: argparse.Namespace) -> Path:
    repo_root = resolve_path(args.repo_root)
    name = str(args.file).strip()
    if not name or "/" in name or "\\" in name:
        raise ValueError("--file must be a simple file name")
    if not name.endswith(".jsonl"):
        raise ValueError("--file must end with .jsonl")
    return workflow_memory_dir(repo_root, args.memory_dir) / name


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_paths(paths: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in paths:
        stripped = item.strip()
        if stripped and stripped not in normalized:
            normalized.append(stripped)
    return normalized


def append_record(args: argparse.Namespace) -> dict[str, Any]:
    path = memory_path(args)
    repo_root = resolve_path(args.repo_root)
    record = {
        "version": 1,
        "timestamp": utc_now(),
        "repo_root": str(repo_root),
        "case": args.case or "",
        "module": args.module or "",
        "platform": args.platform or "",
        "spec_profile": args.spec_profile or "",
        "phase": args.phase,
        "status": args.status,
        "symptom": args.symptom.strip(),
        "reason_codes": sorted(dict.fromkeys(args.reason_code)),
        "tags": sorted(dict.fromkeys(args.tag)),
        "logs": normalize_paths(args.log),
        "sources": normalize_paths(args.source),
        "fix": (args.fix or "").strip(),
        "note": (args.note or "").strip(),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return {"ok": True, "path": str(path), "record": record}


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            records.append({"_invalid": True, "line": line_no})
            continue
        if isinstance(payload, dict):
            payload["_line"] = line_no
            records.append(payload)
    return records


def text_blob(record: dict[str, Any]) -> str:
    values: list[str] = []
    for key in ("case", "module", "platform", "phase", "status", "symptom", "fix", "note"):
        values.append(str(record.get(key, "")))
    for key in ("reason_codes", "tags", "logs", "sources"):
        values.extend(str(item) for item in record.get(key, []) if item is not None)
    return "\n".join(values).lower()


def record_matches(record: dict[str, Any], args: argparse.Namespace) -> bool:
    if record.get("_invalid"):
        return False
    if args.case and args.case.lower() not in str(record.get("case", "")).lower():
        return False
    if args.module and str(record.get("module", "")) != args.module:
        return False
    if args.platform and str(record.get("platform", "")) != args.platform:
        return False
    if args.phase and str(record.get("phase", "")) != args.phase:
        return False
    if args.status and str(record.get("status", "")) != args.status:
        return False
    blob = text_blob(record)
    for term in args.term:
        if term.lower() not in blob:
            return False
    return True


def query_records(args: argparse.Namespace) -> dict[str, Any]:
    path = memory_path(args)
    records = [record for record in load_records(path) if record_matches(record, args)]
    records.sort(key=lambda record: str(record.get("timestamp", "")), reverse=True)
    limit = max(1, args.limit)
    return {
        "ok": True,
        "path": str(path),
        "count": len(records),
        "records": records[:limit],
        "limit": limit,
        "quality_boundary": (
            "Memory records are local hints. Re-check current source, logs, spec_profile, "
            "and platform evidence before using them in a decision."
        ),
    }


def top(counter: Counter[str], limit: int) -> list[dict[str, Any]]:
    return [{"value": value, "count": count} for value, count in counter.most_common(limit)]


def summarize_records(args: argparse.Namespace) -> dict[str, Any]:
    path = memory_path(args)
    records = [record for record in load_records(path) if not record.get("_invalid")]
    limit = max(1, args.limit)
    phase_counts = Counter(str(record.get("phase", "")) for record in records if record.get("phase"))
    status_counts = Counter(str(record.get("status", "")) for record in records if record.get("status"))
    module_counts = Counter(str(record.get("module", "")) for record in records if record.get("module"))
    platform_counts = Counter(str(record.get("platform", "")) for record in records if record.get("platform"))
    reason_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    for record in records:
        reason_counts.update(str(item) for item in record.get("reason_codes", []) if item)
        tag_counts.update(str(item) for item in record.get("tags", []) if item)
    return {
        "ok": True,
        "path": str(path),
        "count": len(records),
        "phase_counts": top(phase_counts, limit),
        "status_counts": top(status_counts, limit),
        "module_counts": top(module_counts, limit),
        "platform_counts": top(platform_counts, limit),
        "reason_code_counts": top(reason_counts, limit),
        "tag_counts": top(tag_counts, limit),
        "latest_records": sorted(records, key=lambda record: str(record.get("timestamp", "")), reverse=True)[:limit],
        "quality_boundary": (
            "Memory is append-only local evidence. Mark stale entries obsolete instead of deleting them silently."
        ),
    }


def render_record(record: dict[str, Any]) -> str:
    parts = [
        str(record.get("timestamp", "")),
        f"phase={record.get('phase', '')}",
        f"status={record.get('status', '')}",
    ]
    if record.get("case"):
        parts.append(f"case={record.get('case')}")
    if record.get("platform"):
        parts.append(f"platform={record.get('platform')}")
    if record.get("module"):
        parts.append(f"module={record.get('module')}")
    parts.append(f"symptom={record.get('symptom', '')}")
    if record.get("fix"):
        parts.append(f"fix={record.get('fix')}")
    if record.get("reason_codes"):
        parts.append("reason_codes=" + ",".join(record["reason_codes"]))
    return " | ".join(parts)


def render_text(payload: dict[str, Any]) -> str:
    lines = [f"memory: {payload.get('path')}", f"count: {payload.get('count', 0)}"]
    if "record" in payload:
        lines.append(render_record(payload["record"]))
    for record in payload.get("records", []):
        lines.append("- " + render_record(record))
    for key in ("phase_counts", "status_counts", "module_counts", "platform_counts", "reason_code_counts", "tag_counts"):
        if payload.get(key):
            lines.append(key + ":")
            for item in payload[key]:
                lines.append(f"  - {item['value']}: {item['count']}")
    if payload.get("quality_boundary"):
        lines.append("boundary: " + payload["quality_boundary"])
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        if args.command == "append":
            payload = append_record(args)
        elif args.command == "query":
            payload = query_records(args)
        elif args.command == "summarize":
            payload = summarize_records(args)
        else:
            raise ValueError(f"unknown command: {args.command}")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text(payload))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
