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
result_log/
tmp/
.hyptest_skill_cache/   skill-local helper cache; never use as source evidence
.hyptest_skill_tmp/     skill-local eval/self-check temporary workspace
```

`case_elf_asm/` is the only current per-case ELF/ASM export directory.
Do not introduce the removed legacy name back into scripts or docs.

These helper directories are safe to delete at any time.

Use `python3 scripts/clean_generated.py --repo-root <repo_root>` to remove them.

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

Use explicit environment variables instead of personal absolute paths:

```text
CROSS_COMPILE     RISC-V toolchain prefix, default usually riscv64-unknown-elf-
SPIKE_BIN         official Spike executable for get_result.py --platform spike
LINKNAN_HOME      LinkNan workspace root for compile/run on platform linknan
DIFFTEST_REF_SO   difftest reference shared object for LinkNan runs
```

If a required env var is missing, prefer a clear error over silently falling
back to another user's path.
