#!/usr/bin/env python3
"""Query RTL bug-fix history from LinkNan and Nanhu git repos.

Use this before writing a suspected-bug case: search real fix commits
under the target module, list the files they touched, and surface
neighbouring paths that haven't been covered yet.

Results are heuristics. Commits are tagged as fix candidates when their
subject matches bug-fix keywords (fix/bug/issue/error/wrong/...).
Final judgement about relevance is still up to the caller.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from skill_config import process_env_value, resolve_path


FIX_KEYWORD_PATTERN = re.compile(
    r"\b(fix|fixes|fixed|fixing|bug|bugfix|issue|error|wrong|incorrect|broken|"
    r"regression|revert|workaround|patch|miscompil|hang|deadlock|corruption|stale|leak)\b",
    re.IGNORECASE,
)

# Very common non-bug subjects we want to filter out even if they contain
# a trigger word (e.g. "fix typo in docs" — not an RTL bug).
NON_BUG_SUBJECT_PATTERN = re.compile(
    r"\b(typo|doc|docs|readme|comment|log|logging|print|format|lint|style|rename)\b",
    re.IGNORECASE,
)

SCALA_EXTENSION = ".scala"


@dataclass
class RepoSpec:
    label: str
    path: Path


@dataclass
class BugCommit:
    repo: str
    sha: str
    short_sha: str
    author_date: str
    subject: str
    files: list[str] = field(default_factory=list)
    scala_hits: list[str] = field(default_factory=list)  # file:line ranges from hunks
    match_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "repo": self.repo,
            "sha": self.sha,
            "short_sha": self.short_sha,
            "author_date": self.author_date,
            "subject": self.subject,
            "files": self.files,
            "scala_hits": self.scala_hits,
            "match_reasons": self.match_reasons,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Query RTL bug-fix history across LinkNan and Nanhu git repos.",
    )
    parser.add_argument(
        "--linknan-home",
        default=None,
        help="LinkNan repo root. Defaults to HYPTEST_LINKNAN_HOME env.",
    )
    parser.add_argument(
        "--nanhu-rel",
        default="dependencies/nanhu",
        help="Nanhu submodule path relative to LinkNan root (default: dependencies/nanhu).",
    )
    parser.add_argument(
        "--scope",
        choices=("both", "linknan", "nanhu"),
        default="both",
        help="Which repo(s) to search (default: both).",
    )
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        help=(
            "Module name to filter commits by touched path. Maps to common Chisel layout"
            " like src/main/scala/<xiangshan>/<module>/**/*.scala. Repeatable."
        ),
    )
    parser.add_argument(
        "--path",
        action="append",
        default=[],
        help="Extra pathspec to include in git log, e.g. 'src/main/scala/xiangshan/mem/**'.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Specific file path (relative to repo root) to filter by. Repeatable.",
    )
    parser.add_argument(
        "--keyword",
        action="append",
        default=[],
        help="Extra keyword(s) to AND-match against commit subject/body.",
    )
    parser.add_argument(
        "--since",
        default=None,
        help="Only commits after this date. Passed to `git log --since=` (e.g. '2024-01-01', '6 months ago').",
    )
    parser.add_argument(
        "--until",
        default=None,
        help="Only commits before this date. Passed to `git log --until=`.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=25,
        help="Max commits per repo (default: 25).",
    )
    parser.add_argument(
        "--include-non-scala",
        action="store_true",
        help="Keep commits that only touch non-.scala files (default: require at least one .scala file).",
    )
    parser.add_argument(
        "--no-filter-heuristic",
        action="store_true",
        help="Don't filter by bug-fix keyword heuristic; return all commits matching path filters.",
    )
    parser.add_argument(
        "--show-neighbors",
        action="store_true",
        help="Group results by touched directory to show neighbouring files not yet in the provided --file list.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON.",
    )
    parser.add_argument(
        "--markdown",
        action="store_true",
        help="Emit Markdown table.",
    )
    return parser.parse_args()


def resolve_linknan_root(arg_value: str | None) -> Path:
    if arg_value and arg_value.strip():
        return resolve_path(arg_value)
    env_value = process_env_value("HYPTEST_LINKNAN_HOME")
    if not env_value:
        raise SystemExit(
            "HYPTEST_LINKNAN_HOME is not set and --linknan-home was not provided. "
            "Set `export HYPTEST_LINKNAN_HOME=<LinkNan repo root>` or pass --linknan-home."
        )
    return resolve_path(env_value)


def build_repo_specs(args: argparse.Namespace) -> list[RepoSpec]:
    linknan_root = resolve_linknan_root(args.linknan_home)
    nanhu_root = (linknan_root / args.nanhu_rel).resolve()
    specs: list[RepoSpec] = []
    if args.scope in ("both", "linknan"):
        specs.append(RepoSpec("linknan", linknan_root))
    if args.scope in ("both", "nanhu"):
        if nanhu_root.exists() and (nanhu_root / ".git").exists():
            specs.append(RepoSpec("nanhu", nanhu_root))
        else:
            # Nanhu submodule not initialised; warn only, don't abort.
            sys.stderr.write(
                f"[warn] Nanhu submodule not found at {nanhu_root}; skipping nanhu scope.\n"
            )
    return specs


def run_git(repo: Path, args: list[str]) -> str:
    cmd = ["git", "-C", str(repo), *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise SystemExit("`git` not found on PATH.")
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        raise SystemExit(f"git failed in {repo}: {stderr or exc}")
    return result.stdout


def module_pathspecs(modules: Iterable[str]) -> list[str]:
    """Turn module names into loose pathspec patterns.

    We don't know ahead whether the module lives under xiangshan/<mod> or
    some other namespace. Be liberal and return a set of patterns the git
    cli accepts via `-- <pathspec>`.
    """
    patterns: list[str] = []
    for mod in modules:
        mod_clean = mod.strip().strip("/")
        if not mod_clean:
            continue
        patterns.append(f"*{mod_clean}*")
        patterns.append(f"src/main/scala/**/{mod_clean}/**")
        patterns.append(f"src/main/scala/**/{mod_clean}*")
    # De-dup, preserve order.
    return list(dict.fromkeys(patterns))


def build_git_log_cmd(args: argparse.Namespace, repo: Path) -> list[str]:
    cmd = [
        "log",
        f"-{max(1, args.limit)}",
        "--no-merges",
        "--date=short",
        "--pretty=format:%H%x1f%h%x1f%ad%x1f%s",
        "--name-only",
    ]
    if args.since:
        cmd.append(f"--since={args.since}")
    if args.until:
        cmd.append(f"--until={args.until}")
    for kw in args.keyword:
        cmd.append(f"--grep={kw}")
        cmd.append("--regexp-ignore-case")
    # path filters: if user passed --file, prefer those; otherwise fall back
    # to --module / --path patterns. Git pathspecs come after `--`.
    pathspecs: list[str] = []
    for f in args.file:
        pathspecs.append(f)
    pathspecs.extend(module_pathspecs(args.module))
    for p in args.path:
        pathspecs.append(p)
    if pathspecs:
        cmd.append("--")
        cmd.extend(pathspecs)
    return cmd


def parse_git_log_output(output: str, repo_label: str) -> list[BugCommit]:
    """Parse `%H\\x1f%h\\x1f%ad\\x1f%s` + `--name-only` blocks."""
    commits: list[BugCommit] = []
    blocks = re.split(r"\n\n+", output.strip())
    for block in blocks:
        if not block.strip():
            continue
        lines = block.splitlines()
        header = lines[0]
        file_lines = [ln.strip() for ln in lines[1:] if ln.strip()]
        parts = header.split("\x1f")
        if len(parts) != 4:
            continue
        sha, short_sha, date, subject = parts
        commits.append(
            BugCommit(
                repo=repo_label,
                sha=sha,
                short_sha=short_sha,
                author_date=date,
                subject=subject,
                files=file_lines,
            )
        )
    return commits


def apply_fix_heuristic(commits: list[BugCommit], disable: bool) -> list[BugCommit]:
    if disable:
        for c in commits:
            c.match_reasons.append("heuristic disabled")
        return commits
    kept: list[BugCommit] = []
    for c in commits:
        if NON_BUG_SUBJECT_PATTERN.search(c.subject):
            continue
        if FIX_KEYWORD_PATTERN.search(c.subject):
            c.match_reasons.append("subject matches fix keyword")
            kept.append(c)
    return kept


def filter_scala_only(commits: list[BugCommit], require_scala: bool) -> list[BugCommit]:
    kept: list[BugCommit] = []
    for c in commits:
        scala_files = [f for f in c.files if f.endswith(SCALA_EXTENSION)]
        if require_scala and not scala_files:
            continue
        kept.append(c)
    return kept


HUNK_HEADER_RE = re.compile(r"^@@ .* @@")
DIFF_HEADER_RE = re.compile(r"^diff --git a/(\S+) b/(\S+)$")
HUNK_LINE_INFO_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def collect_scala_hits(repo: Path, commit: BugCommit) -> list[str]:
    """For a commit, run `git show` with unified=0 and collect scala file:line hits."""
    if not any(f.endswith(SCALA_EXTENSION) for f in commit.files):
        return []
    output = run_git(
        repo,
        [
            "show",
            "--no-color",
            "--unified=0",
            "--pretty=format:",
            commit.sha,
        ],
    )
    hits: list[str] = []
    current_file: str | None = None
    for line in output.splitlines():
        m = DIFF_HEADER_RE.match(line)
        if m:
            current_file = m.group(2)
            continue
        if current_file and current_file.endswith(SCALA_EXTENSION):
            hm = HUNK_LINE_INFO_RE.match(line)
            if hm:
                new_start = int(hm.group(3))
                new_count = int(hm.group(4)) if hm.group(4) else 1
                if new_count <= 0:
                    hits.append(f"{current_file}:{new_start}")
                elif new_count == 1:
                    hits.append(f"{current_file}:{new_start}")
                else:
                    hits.append(f"{current_file}:{new_start}-{new_start + new_count - 1}")
    # Limit noise; keep first 8 ranges per commit.
    return hits[:8]


def query_repo(args: argparse.Namespace, spec: RepoSpec) -> list[BugCommit]:
    log_output = run_git(spec.path, build_git_log_cmd(args, spec.path))
    if not log_output.strip():
        return []
    commits = parse_git_log_output(log_output, spec.label)
    commits = apply_fix_heuristic(commits, args.no_filter_heuristic)
    commits = filter_scala_only(commits, require_scala=not args.include_non_scala)
    for c in commits:
        c.scala_hits = collect_scala_hits(spec.path, c)
    return commits


def group_by_dir(commits: list[BugCommit]) -> dict[str, list[BugCommit]]:
    groups: dict[str, list[BugCommit]] = {}
    for c in commits:
        dirs = set()
        for f in c.files:
            if "/" in f:
                dirs.add(f.rsplit("/", 1)[0])
        if not dirs:
            dirs.add("<root>")
        for d in dirs:
            groups.setdefault(d, []).append(c)
    return dict(sorted(groups.items()))


def emit_markdown(commits: list[BugCommit], show_neighbors: bool) -> str:
    if not commits:
        return "_No matching commits._\n"
    lines: list[str] = []
    lines.append("| repo | date | sha | subject | scala hits |")
    lines.append("| --- | --- | --- | --- | --- |")
    for c in commits:
        hits = "; ".join(c.scala_hits) if c.scala_hits else "-"
        subject = c.subject.replace("|", "\\|")
        lines.append(f"| {c.repo} | {c.author_date} | `{c.short_sha}` | {subject} | {hits} |")
    if show_neighbors:
        lines.append("")
        lines.append("### Neighbouring directories")
        for directory, dcommits in group_by_dir(commits).items():
            lines.append(f"- `{directory}` — {len(dcommits)} fix commit(s)")
            for c in dcommits[:5]:
                lines.append(f"  - `{c.short_sha}` {c.author_date} — {c.subject}")
    return "\n".join(lines) + "\n"


def emit_json(commits: list[BugCommit], args: argparse.Namespace) -> str:
    payload = {
        "filters": {
            "scope": args.scope,
            "modules": args.module,
            "paths": args.path,
            "files": args.file,
            "keywords": args.keyword,
            "since": args.since,
            "until": args.until,
            "limit_per_repo": args.limit,
            "heuristic_disabled": args.no_filter_heuristic,
            "include_non_scala": args.include_non_scala,
        },
        "commits": [c.to_dict() for c in commits],
    }
    if args.show_neighbors:
        payload["neighbors"] = {
            d: [c.short_sha for c in clist]
            for d, clist in group_by_dir(commits).items()
        }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def main() -> int:
    args = parse_args()
    specs = build_repo_specs(args)
    if not specs:
        sys.stderr.write("No repo to search.\n")
        return 2
    all_commits: list[BugCommit] = []
    for spec in specs:
        all_commits.extend(query_repo(args, spec))
    # Sort: most recent first, stable across repos.
    all_commits.sort(key=lambda c: (c.author_date, c.repo, c.short_sha), reverse=True)

    if args.json:
        sys.stdout.write(emit_json(all_commits, args) + "\n")
    elif args.markdown:
        sys.stdout.write(emit_markdown(all_commits, args.show_neighbors))
    else:
        # Default: compact human-readable text
        if not all_commits:
            sys.stdout.write("No matching commits.\n")
            return 0
        for c in all_commits:
            hits = ", ".join(c.scala_hits) if c.scala_hits else "(no scala hunks)"
            sys.stdout.write(f"[{c.repo}] {c.short_sha} {c.author_date}  {c.subject}\n")
            sys.stdout.write(f"    hits: {hits}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
