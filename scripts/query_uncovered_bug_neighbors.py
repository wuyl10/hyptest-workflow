#!/usr/bin/env python3
"""Find RTL fix commits whose touched file:line has no nearby test_point coverage.

Use this when doing bug hunt to locate "real-bug neighbourhood that the
repo hasn't covered yet". Runs `query_rtl_bug_history.py` to collect recent
fix commits + scala file:line ranges, then greps `test_point/*.md` to find
which of those paths are already referenced by existing test points.

Uncovered commits (or commits whose referenced file:line is far from any
existing test_point mention within the same file) are flagged as candidate
bug hunt directions.

This is one evidence source, not the only one. It cannot tell you about
unfixed bugs, cross-module issues, or entirely new paths — see
`SKILL.md` Bug Hunt Evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from skill_config import process_env_value, resolve_path


SCRIPT_DIR = Path(__file__).resolve().parent


# Matches <anywhere>/<FileName>.scala:<line> or .scala:<start>-<end>.
SCALA_REF_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_./-]+)\.scala):(?P<start>\d+)(?:-(?P<end>\d+))?",
)


@dataclass
class TestPointReference:
    path: Path
    rel: str
    scala_file: str
    line_start: int
    line_end: int
    context_line: int


@dataclass
class BugCommit:
    repo: str
    short_sha: str
    author_date: str
    subject: str
    scala_hits: list[str]


@dataclass
class Neighbourhood:
    commit: BugCommit
    scala_file: str
    line_start: int
    line_end: int
    covered_by: list[TestPointReference] = field(default_factory=list)
    distance: int | None = None

    def to_dict(self) -> dict:
        return {
            "commit_repo": self.commit.repo,
            "commit_sha": self.commit.short_sha,
            "commit_date": self.commit.author_date,
            "commit_subject": self.commit.subject,
            "scala_file": self.scala_file,
            "fix_line_start": self.line_start,
            "fix_line_end": self.line_end,
            "covered_by": [
                {
                    "test_point_file": ref.rel,
                    "test_point_md_line": ref.context_line,
                    "scala_line_start": ref.line_start,
                    "scala_line_end": ref.line_end,
                }
                for ref in self.covered_by
            ],
            "nearest_distance_lines": self.distance,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Find RTL fix commits with no nearby test_point coverage.",
    )
    parser.add_argument("--repo-root", default=None,
                        help="hyptest repo root. Defaults to $HYPTEST_HOME.")
    parser.add_argument("--linknan-home", default=None,
                        help="LinkNan repo root. Defaults to $HYPTEST_LINKNAN_HOME.")
    parser.add_argument("--module", action="append", default=[],
                        help="Module filter. Repeatable.")
    parser.add_argument("--since", default=None,
                        help="git log --since, e.g. '6 months ago'.")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max commits per repo (default: 20).")
    parser.add_argument("--proximity", type=int, default=50,
                        help="Line distance threshold for 'covered' (default: 50).")
    parser.add_argument("--show-covered", action="store_true",
                        help="Also show commits that ARE covered.")
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    parser.add_argument("--markdown", action="store_true", help="Emit Markdown.")
    return parser.parse_args()


def resolve_hyptest_home(arg_value: str | None) -> Path:
    if arg_value and arg_value.strip():
        return resolve_path(arg_value)
    env_value = process_env_value("HYPTEST_HOME")
    if not env_value:
        raise SystemExit(
            "HYPTEST_HOME is not set and --repo-root was not provided. "
            "Set HYPTEST_HOME or pass --repo-root."
        )
    return resolve_path(env_value)


def normalise_scala_path(raw: str) -> str:
    """Keep the last 3 path components so '.../mem/lsqueue/StoreQueue.scala' and
    'lsqueue/StoreQueue.scala' compare equal."""
    parts = raw.replace("\\", "/").split("/")
    tail = "/".join(parts[-3:]) if len(parts) >= 3 else "/".join(parts)
    return tail


def collect_test_point_references(repo_root: Path) -> list[TestPointReference]:
    tp_dir = repo_root / "test_point"
    if not tp_dir.is_dir():
        return []
    refs: list[TestPointReference] = []
    for md_path in sorted(tp_dir.glob("*.md")):
        try:
            text = md_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(md_path.relative_to(repo_root))
        for m in SCALA_REF_RE.finditer(text):
            path = m.group("path")
            start = int(m.group("start"))
            end = int(m.group("end")) if m.group("end") else start
            norm = normalise_scala_path(path)
            context_line = text.count("\n", 0, m.start()) + 1
            refs.append(
                TestPointReference(
                    path=md_path, rel=rel, scala_file=norm,
                    line_start=start, line_end=end, context_line=context_line,
                )
            )
    return refs


def run_bug_history(args: argparse.Namespace) -> list[BugCommit]:
    cmd = [sys.executable, str(SCRIPT_DIR / "query_rtl_bug_history.py"),
           "--json", "--limit", str(args.limit)]
    if args.linknan_home:
        cmd.extend(["--linknan-home", args.linknan_home])
    if args.since:
        cmd.extend(["--since", args.since])
    for mod in args.module:
        cmd.extend(["--module", mod])
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            f"query_rtl_bug_history.py failed:\n{(exc.stderr or '').strip()}"
        )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"query_rtl_bug_history.py emitted invalid JSON: {exc}")
    return [
        BugCommit(
            repo=item.get("repo", ""), short_sha=item.get("short_sha", ""),
            author_date=item.get("author_date", ""),
            subject=item.get("subject", ""),
            scala_hits=item.get("scala_hits", []),
        )
        for item in payload.get("commits", [])
    ]


def parse_scala_hit(hit: str) -> tuple[str, int, int] | None:
    m = SCALA_REF_RE.search(hit)
    if not m:
        return None
    path = normalise_scala_path(m.group("path"))
    start = int(m.group("start"))
    end = int(m.group("end")) if m.group("end") else start
    return path, start, end


def interval_distance(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    if a_end < b_start:
        return b_start - a_end
    if b_end < a_start:
        return a_start - b_end
    return 0


def build_neighbourhoods(
    commits: Iterable[BugCommit], refs: list[TestPointReference], proximity: int,
) -> list[Neighbourhood]:
    ref_by_file: dict[str, list[TestPointReference]] = {}
    for r in refs:
        ref_by_file.setdefault(r.scala_file, []).append(r)
    result: list[Neighbourhood] = []
    for commit in commits:
        seen: set[tuple[str, int, int]] = set()
        for hit in commit.scala_hits:
            parsed = parse_scala_hit(hit)
            if not parsed or parsed in seen:
                continue
            seen.add(parsed)
            path, start, end = parsed
            file_refs = ref_by_file.get(path, [])
            distance: int | None = None
            covered: list[TestPointReference] = []
            for r in file_refs:
                d = interval_distance(start, end, r.line_start, r.line_end)
                if distance is None or d < distance:
                    distance = d
                if d <= proximity:
                    covered.append(r)
            result.append(Neighbourhood(
                commit=commit, scala_file=path,
                line_start=start, line_end=end,
                covered_by=covered, distance=distance,
            ))
    return result


def emit_text(neighbourhoods: list[Neighbourhood], show_covered: bool) -> str:
    uncovered = [n for n in neighbourhoods if not n.covered_by]
    covered = [n for n in neighbourhoods if n.covered_by]
    lines: list[str] = [f"== Uncovered RTL fix neighbourhoods ({len(uncovered)}) =="]
    if not uncovered:
        lines.append("(none — every fix commit has nearby test_point coverage)")
    for n in uncovered:
        d = f"nearest {n.distance}L away" if n.distance is not None else "no test_point in this file"
        lines.append(
            f"  [{n.commit.repo}] {n.commit.short_sha} {n.commit.author_date} "
            f"{n.scala_file}:{n.line_start}-{n.line_end} ({d})"
        )
        lines.append(f"    subject: {n.commit.subject}")
    if show_covered:
        lines.append("")
        lines.append(f"== Covered fix neighbourhoods ({len(covered)}) ==")
        for n in covered:
            lines.append(
                f"  [{n.commit.repo}] {n.commit.short_sha} "
                f"{n.scala_file}:{n.line_start}-{n.line_end} "
                f"(covered, nearest {n.distance}L)"
            )
            for ref in n.covered_by[:3]:
                lines.append(
                    f"    - {ref.rel} L{ref.context_line} "
                    f"refers to {ref.scala_file}:{ref.line_start}-{ref.line_end}"
                )
    return "\n".join(lines) + "\n"


def emit_markdown(neighbourhoods: list[Neighbourhood], show_covered: bool) -> str:
    uncovered = [n for n in neighbourhoods if not n.covered_by]
    covered = [n for n in neighbourhoods if n.covered_by]
    lines: list[str] = ["## Uncovered RTL fix neighbourhoods"]
    if not uncovered:
        lines.append("")
        lines.append("_(none — every fix commit has nearby test_point coverage)_")
    else:
        lines.append("")
        lines.append("| repo | sha | date | path:line | nearest test_point | subject |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for n in uncovered:
            nearest = (f"{n.distance}L away" if n.distance is not None
                       else "none in file")
            subject = n.commit.subject.replace("|", "\\|")
            lines.append(
                f"| {n.commit.repo} | `{n.commit.short_sha}` | {n.commit.author_date} "
                f"| `{n.scala_file}:{n.line_start}-{n.line_end}` "
                f"| {nearest} | {subject} |"
            )
    if show_covered:
        lines.append("")
        lines.append("## Covered fix neighbourhoods")
        if covered:
            lines.append("")
            lines.append("| repo | sha | path:line | covered by |")
            lines.append("| --- | --- | --- | --- |")
            for n in covered:
                refs_str = "; ".join(
                    f"{r.rel}:L{r.context_line}" for r in n.covered_by[:3]
                )
                lines.append(
                    f"| {n.commit.repo} | `{n.commit.short_sha}` "
                    f"| `{n.scala_file}:{n.line_start}-{n.line_end}` | {refs_str} |"
                )
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    repo_root = resolve_hyptest_home(args.repo_root)
    if not (repo_root / "test_point").is_dir():
        raise SystemExit(
            f"no test_point/ dir under {repo_root}. Is HYPTEST_HOME correct?"
        )
    refs = collect_test_point_references(repo_root)
    commits = run_bug_history(args)
    neighbourhoods = build_neighbourhoods(commits, refs, args.proximity)
    neighbourhoods.sort(key=lambda n: (
        0 if not n.covered_by else 1,
        -(n.line_end - n.line_start),
        n.commit.author_date,
    ))
    if args.json:
        payload = {
            "hyptest_home": str(repo_root),
            "proximity_lines": args.proximity,
            "test_point_refs": len(refs),
            "commits_seen": len(commits),
            "uncovered": [n.to_dict() for n in neighbourhoods if not n.covered_by],
            "covered": (
                [n.to_dict() for n in neighbourhoods if n.covered_by]
                if args.show_covered else None
            ),
        }
        sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    elif args.markdown:
        sys.stdout.write(emit_markdown(neighbourhoods, args.show_covered))
    else:
        sys.stdout.write(emit_text(neighbourhoods, args.show_covered))
    return 0


if __name__ == "__main__":
    sys.exit(main())
