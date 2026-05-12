# Current Hyptest Repo Layout

Use this reference whenever a task depends on repository structure, source
ownership, generated directories, or platform environment variables.

## Source Layout

```text
src/                 framework C sources
asm/                 framework assembly entry/handlers
inc/                 public headers and test macros
ai_test_cases/       AI or bulk-generated cases
manual_test_cases/   human-maintained cases, grouped by module
test_register.c      single registration/status source
compile_elf.py       single-case and batch compile entry
get_result.py        Spike/LinkNan run entry
Makefile             low-level build recipe
linker.ld            linker script
test_point/          test point documents and mapping notes
```

`manual_test_cases/` is recursive. Keep module-owned manual cases under
`manual_test_cases/<module>/`; do not move them back to the repo root.

## Generated Directories

These directories are generated artifacts and should not drive source decisions:

```text
build/
deploy/
case_elf_asm/
.tmp/
.hyptest_workflow_skill/
```

`case_elf_asm/` stores per-case ELF/ASM exports.

`.hyptest_workflow_skill/` is the unified repo-local workflow state root:

```text
.hyptest_workflow_skill/cache/      rebuildable workflow indexes and preflight packs
.hyptest_workflow_skill/reports/    saved preflight/gate/postcheck/submission/ledger reports
.hyptest_workflow_skill/tmp/        temporary workflow helper files
.hyptest_workflow_skill/memory/     append-only local lessons/failure records; review before deleting
.tmp/hyptest_compile/                compile_elf.py register sources and compiler TMPDIR
.tmp/result_log/                     get_result.py Spike/LinkNan run logs
```

Most helper state under `cache/`, `reports/`, and `tmp/` is safe to delete and
rebuild. Treat `memory/` differently: it is local evidence for repeated failure
patterns and fixes, so mark stale records `obsolete` instead of casually
dropping them.

Use `python3 scripts/clean_generated.py --repo-root $HYPTEST_HOME` to remove
workflow cache/report/tmp directories after confirming no useful logs need to
be kept.

## Platform Names

Use the current hyptest platform names:

```text
spike
linknan
```

Do not use `xiangshan` as a hyptest `--plat` / `--platform` value. Mentions of
`xiangshan` may still be valid RTL package paths inside LinkNan source
references, for example `src/main/scala/xiangshan/...`.

## Environment Variables

Use prompt-scoped `HYPTEST_*` environment variables instead of personal
absolute paths or generic project-wide names:

```text
HYPTEST_CROSS_COMPILE    RISC-V toolchain prefix, default usually riscv64-unknown-elf-
HYPTEST_SPIKE_BIN        community/upstream Spike executable for get_result.py --platform spike
HYPTEST_LINKNAN_HOME     LinkNan workspace root for compile/run on platform linknan
HYPTEST_DIFFTEST_REF_SO  difftest reference shared object for LinkNan runs, often from custom Spike
HYPTEST_TMPDIR           temporary directory when /tmp is too small
```

If a required env var is missing, prefer a clear error over silently falling
back to another user's path.

Keep runner roles separate: use `HYPTEST_SPIKE_BIN` for community/upstream Spike
architecture gate evidence, and use `HYPTEST_DIFFTEST_REF_SO` for LinkNan/project
difftest evidence. Nanhu RTL/source evidence is derived only from the
initialized LinkNan submodule at
`HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main`.

The skill-facing environment uses only `HYPTEST_*` names to avoid collisions
with other projects. When invoking hyptest repo scripts, the skill maps
`HYPTEST_SPIKE_BIN` to the runtime `SPIKE_BIN` that `get_result.py` already
expects.
