#!/usr/bin/env python3
"""Summarize timing data from hyptest workflow pack JSON reports."""

from __future__ import annotations

import argparse
import glob
import json
from pathlib import Path
from statistics import mean
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize timing.total_seconds/by_step from workflow JSON reports."
    )
    parser.add_argument(
        "--reports",
        action="append",
        required=True,
        help="Report JSON path or glob; can be repeated.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON summary.")
    parser.add_argument("--md-out", help="Write Markdown summary to this path.")
    parser.add_argument("--json-out", help="Write JSON summary to this path.")
    return parser.parse_args()


def expand_reports(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        matches = glob.glob(str(Path(pattern).expanduser()), recursive=True)
        if not matches:
            candidate = Path(pattern).expanduser()
            if candidate.is_file():
                matches = [str(candidate)]
        for raw in matches:
            path = Path(raw).expanduser().resolve()
            if path.is_file() and path not in seen:
                seen.add(path)
                paths.append(path)
    return sorted(paths)


def load_report(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    payload["_source_path"] = str(path)
    return payload


def report_kind(payload: dict[str, Any]) -> str:
    if "platform_results" in payload:
        return "multi_platform_gate"
    if "evidence_requirements" in payload:
        return "case_gate"
    if "preflight" in payload and "gate" in payload:
        return "submission_card"
    if "target_test_point_excerpt" in payload:
        return "case_preflight"
    if "cases" in payload and "commands" in payload:
        return "case_postcheck"
    return "unknown"


def add_step(samples: dict[str, list[float]], name: str, value: Any) -> None:
    if value is None:
        return
    try:
        seconds = float(value)
    except (TypeError, ValueError):
        return
    samples.setdefault(name, []).append(seconds)


def percentile(values: list[float], ratio: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * ratio))))
    return round(ordered[index], 3)


def summarize_samples(samples: dict[str, list[float]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for name, values in sorted(samples.items()):
        summary[name] = {
            "count": len(values),
            "avg": round(mean(values), 3),
            "min": round(min(values), 3),
            "max": round(max(values), 3),
            "p50": percentile(values, 0.5),
            "p90": percentile(values, 0.9),
        }
    return summary


def collect_timing(payload: dict[str, Any], step_samples: dict[str, list[float]]) -> None:
    timing = payload.get("timing") or {}
    kind = report_kind(payload)
    add_step(step_samples, f"{kind}.total", timing.get("total_seconds"))
    by_step = timing.get("by_step") or {}
    if isinstance(by_step, dict):
        for name, seconds in by_step.items():
            add_step(step_samples, f"{kind}.{name}", seconds)


def collect_cache(payload: dict[str, Any]) -> dict[str, int]:
    cache = payload.get("cache") or payload.get("preflight", {}).get("cache") or {}
    if not isinstance(cache, dict) or "hit" not in cache:
        return {"seen": 0, "hit": 0, "miss": 0}
    hit = bool(cache.get("hit"))
    return {"seen": 1, "hit": int(hit), "miss": int(not hit)}


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    paths = expand_reports(args.reports)
    reports: list[dict[str, Any]] = []
    step_samples: dict[str, list[float]] = {}
    cache_counts = {"seen": 0, "hit": 0, "miss": 0}
    slow_reports: list[dict[str, Any]] = []

    for path in paths:
        payload = load_report(path)
        if payload is None:
            continue
        reports.append(payload)
        collect_timing(payload, step_samples)
        cache = collect_cache(payload)
        for key in cache_counts:
            cache_counts[key] += cache[key]
        total = payload.get("timing", {}).get("total_seconds")
        if total is not None:
            slow_reports.append(
                {
                    "path": str(path),
                    "kind": report_kind(payload),
                    "case": payload.get("case"),
                    "platform": payload.get("platform") or payload.get("platforms"),
                    "total_seconds": total,
                }
            )

    slow_reports.sort(key=lambda item: float(item.get("total_seconds") or 0), reverse=True)
    kind_counts: dict[str, int] = {}
    for payload in reports:
        kind = report_kind(payload)
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    return {
        "report_count": len(reports),
        "input_count": len(paths),
        "kind_counts": kind_counts,
        "timing": summarize_samples(step_samples),
        "cache": {
            **cache_counts,
            "hit_rate": round(cache_counts["hit"] / cache_counts["seen"], 3)
            if cache_counts["seen"]
            else None,
        },
        "slowest_reports": slow_reports[:10],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# hyptest workflow timing summary",
        "",
        f"- report_count: `{summary.get('report_count')}`",
        f"- input_count: `{summary.get('input_count')}`",
        "",
        "## Report Kinds",
        "",
    ]
    for kind, count in sorted((summary.get("kind_counts") or {}).items()):
        lines.append(f"- {kind}: `{count}`")
    cache = summary.get("cache") or {}
    lines.extend(["", "## Cache", ""])
    lines.append(f"- seen: `{cache.get('seen')}`")
    lines.append(f"- hit: `{cache.get('hit')}`")
    lines.append(f"- miss: `{cache.get('miss')}`")
    lines.append(f"- hit_rate: `{cache.get('hit_rate')}`")
    lines.extend(["", "## Timing", ""])
    for name, item in sorted((summary.get("timing") or {}).items()):
        lines.append(
            f"- {name}: count=`{item.get('count')}` avg=`{item.get('avg')}` "
            f"p50=`{item.get('p50')}` p90=`{item.get('p90')}` max=`{item.get('max')}`"
        )
    lines.extend(["", "## Slowest Reports", ""])
    for item in summary.get("slowest_reports", []):
        lines.append(
            f"- `{item.get('total_seconds')}`s {item.get('kind')} "
            f"case=`{item.get('case')}` platform=`{item.get('platform')}` path=`{item.get('path')}`"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(summary: dict[str, Any], args: argparse.Namespace) -> None:
    if args.json_out:
        path = Path(args.json_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.md_out:
        path = Path(args.md_out).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(render_markdown(summary), encoding="utf-8")


def main() -> int:
    args = parse_args()
    summary = build_summary(args)
    write_outputs(summary, args)
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(render_markdown(summary))
    return 0 if summary.get("report_count", 0) > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
