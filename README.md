# hyptest-workflow

`hyptest-workflow` 用于 `riscv-hyp-tests-nhv5` 仓库里的 hyptest 落地闭环：从 `test_point` 分析，到 `ai_test_cases/*.c` / `manual_test_cases/**/*.c` 写 case、注册、编译运行、日志归因、分层和轻量回填。

这份 README 只给人工快速入口，不是 agent 执行规则入口。Agent 执行时以 `SKILL.md`、`references/*` 和 `references/spec_profiles/<spec_profile>.md` 为准；维护脚本、清单和 eval 的完整索引看 `references/resource_index.md`。

## 规则入口

- `SKILL.md`：触发条件、硬约束、默认流程。
- `references/repo_layout.md`：仓库结构、平台名、环境变量。
- `references/task_input_schema.md`：任务参数规格和 preflight 校验入口。
- `references/writing_cases.md`：写 case、断言、回填格式。
- `references/build_run_debug.md`：编译、运行、日志定位。
- `references/tiering_decision.md`：`default` / `manual` / `compile-only` / `blocked` 分层。
- `references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md`：规格/profile 边界。
- `references/resource_index.md`：资源完整索引。
- `references/maintainer_guide.md`：维护检查清单。

默认 profile 来自 `references/spec_profiles/index.json` 的 `default_profile`；也可以在 prompt 中显式指定 `spec_profile=<name>`。

## 最短 Prompt

```text
使用hyptest-workflow skill

repo_root: <repo_root>
test_point_file: <test_point_file>
platform: spike
spec_profile: <spec_profile>
task_mode: new-case-only
new_case_count: 1-3
target_policy: default-first

要求：
- 先分析目标模块和 test_point，再新增 1-3 个 ai_* case
- 非 compile-only 必须单 case 跑目标平台
- 回填 test_point，并与 test_register.c 一致
- 输出新增 case、唯一性证据、编译/运行结果、关键日志路径和最终决策
```

## 常用命令

列出全部常用命令：

```bash
python3 scripts/list_skill_commands.py
```

下面这段由 `python3 scripts/update_readme_commands.py` 从
`scripts/list_skill_commands.py --markdown` 生成。

所有带 `--spec-profile <spec_profile>` 的命令都可以省略该参数；省略时使用
`references/spec_profiles/index.json` 中的 `default_profile`。需要复核实际解析结果时，
先跑 `python3 scripts/resolve_spec_profile.py` 或
`python3 scripts/skill_summary.py --show-resolved-profile`。

<!-- BEGIN GENERATED COMMANDS -->
### self-check

- `quick`: Fast skill checks; no simulator environment required.

  ```bash
  python3 scripts/self_check.py --quick --spec-profile <spec_profile>
  ```

- `repo`: Skill checks plus repo migration, CLI contract, and lint-baseline checks.

  ```bash
  python3 scripts/self_check.py --repo --repo-root <repo_root> --spec-profile <spec_profile>
  ```

- `full`: Full checks including real-repo similar-case eval, with saved reports.

  ```bash
  python3 scripts/self_check.py --full --repo-root <repo_root> --spec-profile <spec_profile> --json --json-out .hyptest_skill_reports/self_check_full.json --md-out .hyptest_skill_reports/self_check_full.md
  ```

### doctor

- `repo-health`: Grouped profile, skill, repo, CLI contract, lint-baseline, env and self-check health report.

  ```bash
  python3 scripts/doctor.py --repo-root <repo_root> --pre-submit --strict --spec-profile <spec_profile>
  ```

- `task-request`: Validate task inputs before editing or running cases.

  ```bash
  python3 scripts/validate_task_request.py --repo-root <repo_root> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1-3
  ```

- `platform-env`: Check Spike and LinkNan environment variables and explain what each one is used for.

  ```bash
  python3 scripts/check_env.py --repo-root <repo_root> --platform all --explain --print-exports
  ```

- `doctor-all`: Run grouped doctor checks including both Spike and LinkNan env checks.

  ```bash
  python3 scripts/doctor.py --repo-root <repo_root> --platform all --pre-submit --spec-profile <spec_profile>
  ```

### case-workflow

- `similar-cases`: Search existing ai/manual case sources before writing a new case.

  ```bash
  python3 scripts/find_similar_cases.py --repo-root <repo_root> --query '<scenario terms>' --limit 5 --explain-score
  ```

- `case-lint`: Lint changed case sources for harness-shape mistakes.

  ```bash
  python3 scripts/check_case_lint.py --repo-root <repo_root> --changed-only --strict-case-end --warnings-as-errors
  ```

- `case-lint-baseline`: Fail only on active lint issues not covered by the known baseline.

  ```bash
  python3 scripts/check_case_lint.py --repo-root <repo_root> --baseline assets/baselines/case_lint_baseline.json --warnings-as-errors
  ```

- `cli-contract`: Check compile/run script platform names, case_elf_asm, required env vars and personal-path regressions.

  ```bash
  python3 scripts/check_hyptest_cli_contract.py --repo-root <repo_root>
  ```

- `repo-snapshot`: Print a read-only snapshot of case sources, register state, test_point coverage, artifacts and latest logs.

  ```bash
  python3 scripts/repo_snapshot.py --repo-root <repo_root>
  ```

- `baseline-diff`: Review added/removed lint baseline issues before accepting a new baseline.

  ```bash
  python3 scripts/case_lint_baseline_diff.py --old <old_baseline.json> --new <new_baseline.json>
  ```

- `writeback-check`: Validate lightweight test_point writeback and registration consistency.

  ```bash
  python3 scripts/check_writeback_format.py --repo-root <repo_root> --file <test_point_file> --check-register --spec-profile <spec_profile>
  ```

### profile-and-tiering

- `profile-query`: Summarize PMA/PBMT/MMIO profile rules for an address.

  ```bash
  python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --summary
  ```

- `profile-registry`: Check the profile registry and default profile mapping.

  ```bash
  python3 scripts/check_spec_profile_registry.py
  ```

- `new-profile`: Create a new spec profile skeleton from the template and register it.

  ```bash
  python3 scripts/new_spec_profile.py --name <profile_name> --title '<project/core title>' --update-registry
  ```

- `profile-decision`: Print only matching profile default_decision values.

  ```bash
  python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --decision-only
  ```

- `reason-code`: Suggest candidate reason_code values from a failure symptom.

  ```bash
  python3 scripts/suggest_reason_code.py --symptom '<failure symptom>'
  ```

- `reason-code-eval`: Check symptom-to-reason_code suggestion fixtures.

  ```bash
  python3 scripts/eval_reason_code_suggestions.py
  ```

- `failure-log`: Extract scenario, error points, reason_code candidates and next actions from a failure log.

  ```bash
  python3 scripts/classify_failure_log.py --log-file <log> --json
  ```

- `triage-handoff`: Create a workflow-to-triage handoff card for deeper failure analysis.

  ```bash
  python3 scripts/make_triage_handoff.py --log-file <log> --platform linknan --spec-profile <spec_profile> --json
  ```

### maintenance

- `readme-check`: Check README generated command block is in sync.

  ```bash
  python3 scripts/check_readme_commands.py
  ```

- `readme-update`: Refresh README generated command block.

  ```bash
  python3 scripts/update_readme_commands.py
  ```

- `resource-index-check`: Check resource_index.md mentions public scripts and key assets.

  ```bash
  python3 scripts/check_resource_index.py
  ```

- `manifest-check`: Check assets/script_manifest.json is in sync with scripts/*.py.

  ```bash
  python3 scripts/update_script_manifest.py --check
  ```

- `manifest-update`: Refresh assets/script_manifest.json after adding or removing scripts.

  ```bash
  python3 scripts/update_script_manifest.py --write
  ```

- `resource-index-update`: Refresh the generated resource coverage block in resource_index.md.

  ```bash
  python3 scripts/update_resource_index.py --write
  ```

- `profile-portability`: Check generic skill surfaces do not hardcode the concrete default profile.

  ```bash
  python3 scripts/eval_profile_portability.py
  ```

- `listed-command-help`: Check README/listed script commands still expose --help.

  ```bash
  python3 scripts/eval_listed_commands_help.py
  ```

### cleanup

- `clean-generated`: Remove skill-local temporary/cache files.

  ```bash
  python3 scripts/clean_generated.py --repo-root <repo_root>
  ```

### summary

- `skill-summary`: Summarize profiles, references, scripts, eval assets, and recommended checks.

  ```bash
  python3 scripts/skill_summary.py
  ```
<!-- END GENERATED COMMANDS -->

## 目录结构

```text
hyptest-workflow/
├── SKILL.md
├── README.md
├── agents/
├── references/
│   └── spec_profiles/
├── scripts/
└── assets/
```
