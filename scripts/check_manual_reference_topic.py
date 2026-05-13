#!/usr/bin/env python3
"""Decide whether a manual/blocked outcome needs a new Manual_Reference entry.

Workflow step 16 (SKILL.md) used to auto-append an entry for every
non-default case that the agent considered "a new model boundary". That
over-triggered: duplicates piled up when the same topic came back
because the agent did not consult memory or check whether the MR
already had an unresolved entry on the same topic.

This script encodes the correct 4-step decision order:

  1. profile_covered       — profile/§5/reason_code_catalog already
                              describes this scenario; no MR action needed
  2. memory_confirmed      — memory/events.jsonl has a `confirmed` entry
                              matching case/module/tags; reuse it, no MR
  3. manual_reference_open — Manual_Reference has an *unresolved* entry
                              (no `> 已解决` line) on this topic; agent
                              should append a short "本轮也碰到" bullet
                              under the existing entry, not open a new one
  4. new_entry_needed       — nothing found; go ahead and auto-append

Output: text summary or JSON with `verdict` in the four values above and
suggested `next_action`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parent

MR_ENTRY_HEADER_RE = re.compile(r"^#### (?P<id>[A-Za-z0-9]+)\.?\s+(?P<title>.+?)$", re.MULTILINE)
MR_RESOLVED_MARKER = re.compile(r"^>\s*已解决[（(]")
MR_CASE_BACKTICK_RE = re.compile(r"`(ai_[A-Za-z_][A-Za-z0-9_]*)`")

PROFILE_NONGATE_BLOCK_HEADER = "hyptest-nongate-keywords"
JSON_FENCE_START = re.compile(r"^```" + PROFILE_NONGATE_BLOCK_HEADER + r"\s*$", re.MULTILINE)
JSON_FENCE_END = re.compile(r"^```\s*$", re.MULTILINE)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", required=True, help="hyptest repo root")
    p.add_argument("--case", help="case name (matches against MR backticks and memory case fields)")
    p.add_argument("--module", help="target module (matches memory module field, MR case hint)")
    p.add_argument("--topic", action="append", default=[], help="free-form keyword; repeatable")
    p.add_argument("--spec-profile", help="profile name to scan hyptest-nongate-keywords")
    p.add_argument("--json", action="store_true", help="emit JSON report")
    return p.parse_args()


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def split_mr_entries(mr_text: str) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    matches = list(MR_ENTRY_HEADER_RE.finditer(mr_text))
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(mr_text)
        body = mr_text[start:end]
        resolved = bool(MR_RESOLVED_MARKER.search(body))
        cases = set(MR_CASE_BACKTICK_RE.findall(body))
        entries.append(
            {
                "id": m.group("id"),
                "title": m.group("title").strip(),
                "resolved": resolved,
                "cases": cases,
                "body": body,
            }
        )
    return entries


def mr_unresolved_match(
    mr_text: str,
    case: str | None,
    module: str | None,
    topics: list[str],
) -> dict[str, Any] | None:
    entries = split_mr_entries(mr_text)
    needles = [t.lower() for t in topics if t.strip()]
    if module:
        needles.append(module.lower())
    for entry in entries:
        if entry["resolved"]:
            continue
        if case and case in entry["cases"]:
            return {"id": entry["id"], "title": entry["title"], "match_reason": f"case `{case}` backticked"}
        body_lower = entry["body"].lower()
        hits = [n for n in needles if n and n in body_lower]
        # Require at least 2 topic hits to declare a match, to avoid fuzzy
        # false positives from common words.
        if len(hits) >= 2:
            return {
                "id": entry["id"],
                "title": entry["title"],
                "match_reason": f"topic hits: {', '.join(hits)}",
            }
    return None


def memory_confirmed_match(
    memory_text: str,
    case: str | None,
    module: str | None,
    topics: list[str],
) -> dict[str, Any] | None:
    needles = [t.lower() for t in topics if t.strip()]
    for line in memory_text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(entry, dict):
            continue
        if entry.get("status") != "confirmed":
            continue
        if case and str(entry.get("case", "")) == case:
            return {"match_reason": f"confirmed entry for case `{case}`", "timestamp": entry.get("timestamp")}
        if module and str(entry.get("module", "")).lower() == module.lower():
            tags_lower = [str(t).lower() for t in (entry.get("tags") or [])]
            symptom = str(entry.get("symptom", "")).lower()
            fix = str(entry.get("fix", "")).lower()
            note = str(entry.get("note", "")).lower()
            haystack = f"{symptom} {fix} {note} {' '.join(tags_lower)}"
            hits = [n for n in needles if n and n in haystack]
            if len(hits) >= 2:
                return {
                    "match_reason": f"confirmed entry matches module={module} + topics {', '.join(hits)}",
                    "timestamp": entry.get("timestamp"),
                }
    return None


def profile_coverage_match(
    profile_text: str,
    module: str | None,
    topics: list[str],
) -> dict[str, Any] | None:
    """Rough match against the profile's hyptest-nongate-keywords JSON block.

    Returns a match if a nongate category's `keywords` (NOT module_hints —
    those are too coarse to stand alone) show >=1 topic hit AND either the
    module hints overlap with the supplied module or an additional topic
    keyword hits. This avoids "module=memblock" alone falsely matching
    every memblock-adjacent nongate category.
    """
    if not profile_text:
        return None
    # Extract the JSON block between the fences.
    start_match = JSON_FENCE_START.search(profile_text)
    if not start_match:
        return None
    end_match = JSON_FENCE_END.search(profile_text, start_match.end())
    if not end_match:
        return None
    block = profile_text[start_match.end() : end_match.start()].strip()
    try:
        entries = json.loads(block)
    except json.JSONDecodeError:
        return None
    if not isinstance(entries, list):
        return None
    topic_needles = [t.lower() for t in topics if t.strip()]
    if not topic_needles:
        # Without topic keywords we cannot confidently claim coverage.
        return None
    module_lc = module.lower() if module else None
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        hints = [str(h).lower() for h in (entry.get("module_hints") or [])]
        kws = [str(k).lower() for k in (entry.get("keywords") or [])]
        category = str(entry.get("category", ""))
        kw_pool = " ".join(kws + [category.lower()])
        # Keyword must hit at least one topic.
        keyword_hits = [n for n in topic_needles if n in kw_pool]
        if not keyword_hits:
            continue
        # Module gating: if module supplied, it must appear in module_hints.
        if module_lc:
            if module_lc not in hints:
                continue
        else:
            # Without module context, require >=2 keyword hits to claim coverage.
            if len(keyword_hits) < 2:
                continue
        return {"category": category, "match_reason": f"profile nongate hits: {', '.join(keyword_hits)}"}
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    repo = Path(args.repo_root).resolve()
    mr_path = repo / "test_point" / "Manual_Reference.md"
    memory_path = repo / ".hyptest_workflow_skill" / "memory" / "events.jsonl"
    profile_text = ""
    if args.spec_profile:
        # Resolve profile via resolve_spec_profile.py to stay consistent
        # with the rest of the toolchain.
        import subprocess as _sub
        try:
            out = _sub.run(
                [sys.executable, str(SCRIPT_DIR / "resolve_spec_profile.py"), "--spec-profile", args.spec_profile],
                capture_output=True, text=True, check=False,
            )
            if out.returncode == 0:
                profile_text = read_text(Path(out.stdout.strip()))
        except OSError:
            profile_text = ""

    mr_text = read_text(mr_path)
    memory_text = read_text(memory_path)

    profile_hit = profile_coverage_match(profile_text, args.module, args.topic)
    memory_hit = memory_confirmed_match(memory_text, args.case, args.module, args.topic)
    mr_hit = mr_unresolved_match(mr_text, args.case, args.module, args.topic)

    if profile_hit:
        verdict = "profile_covered"
        next_action = (
            f"Profile 已覆盖该主题（{profile_hit.get('category')}）；无需新增 Manual_Reference 条目。"
            " 交付摘要里引用 profile §5 对应条目即可。"
        )
    elif memory_hit:
        verdict = "memory_confirmed"
        next_action = (
            "memory 已有 confirmed 条目覆盖该主题；无需新增 Manual_Reference 条目。"
            " 交付摘要里引用 memory 条目时间戳，使用其 fix/reason_code 结论。"
        )
    elif mr_hit:
        verdict = "manual_reference_open"
        next_action = (
            f"Manual_Reference 已有未解决条目 #{mr_hit.get('id')}；**不要新开条目**。"
            " 在该条目末尾追加一行 `- 本轮也碰到：<case_name>，<关键现象>`，"
            " 交付摘要里注明『已叠加到 MR #<id>，仍等人工确认』。"
        )
    else:
        verdict = "new_entry_needed"
        next_action = (
            "profile / memory / Manual_Reference 都没覆盖本主题；按 step 16 正常 auto-append"
            " 新的 `#### <id>.（**自动生成，待人工确认**）` 条目。"
        )

    return {
        "ok": True,
        "case": args.case,
        "module": args.module,
        "topics": list(args.topic),
        "spec_profile": args.spec_profile,
        "verdict": verdict,
        "profile_hit": profile_hit,
        "memory_hit": memory_hit,
        "manual_reference_hit": mr_hit,
        "next_action": next_action,
    }


def render_text(report: dict[str, Any]) -> str:
    lines = [f"verdict: {report['verdict']}"]
    if report.get("profile_hit"):
        lines.append(f"  profile: {report['profile_hit']}")
    if report.get("memory_hit"):
        lines.append(f"  memory:  {report['memory_hit']}")
    if report.get("manual_reference_hit"):
        lines.append(f"  MR:      {report['manual_reference_hit']}")
    lines.append(f"next_action: {report['next_action']}")
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    report = build_report(args)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
