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

- `quick`: 快速检查 skill 本身；不需要模拟器环境。

  ```bash
  python3 scripts/self_check.py --quick --spec-profile <spec_profile>
  ```

- `repo`: 在 quick 基础上检查仓库迁移、CLI 约定和 lint baseline。

  ```bash
  python3 scripts/self_check.py --repo --repo-root <repo_root> --spec-profile <spec_profile>
  ```

- `full`: 完整检查，包含真实仓库相似 case eval，并保存报告。

  ```bash
  python3 scripts/self_check.py --full --repo-root <repo_root> --spec-profile <spec_profile> --json --json-out .hyptest_skill_reports/self_check_full.json --md-out .hyptest_skill_reports/self_check_full.md
  ```

### doctor

- `repo-health`: 按 profile、skill、repo、CLI、lint baseline、环境和 self-check 分组输出健康报告。

  ```bash
  python3 scripts/doctor.py --repo-root <repo_root> --pre-submit --strict --spec-profile <spec_profile>
  ```

- `task-request`: 修改或运行 case 前校验任务输入参数。

  ```bash
  python3 scripts/validate_task_request.py --repo-root <repo_root> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1-3
  ```

- `platform-env`: 检查 Spike 和 LinkNan 环境变量，并说明各变量用途。

  ```bash
  python3 scripts/check_env.py --repo-root <repo_root> --platform all --explain --print-exports
  ```

- `doctor-all`: 运行 doctor 分组检查，包含 Spike 和 LinkNan 环境检查。

  ```bash
  python3 scripts/doctor.py --repo-root <repo_root> --platform all --pre-submit --spec-profile <spec_profile>
  ```

### case-workflow

- `similar-cases`: 写新 case 前搜索已有 ai/manual case 源文件。

  ```bash
  python3 scripts/find_similar_cases.py --repo-root <repo_root> --query '<scenario terms>' --limit 5 --explain-score
  ```

- `case-lint`: 检查已改 case 源文件的测试框架结构问题。

  ```bash
  python3 scripts/check_case_lint.py --repo-root <repo_root> --changed-only --strict-case-end --warnings-as-errors
  ```

- `case-lint-baseline`: 只对不在已知 baseline 内的活跃 lint 问题报错。

  ```bash
  python3 scripts/check_case_lint.py --repo-root <repo_root> --baseline assets/baselines/case_lint_baseline.json --warnings-as-errors
  ```

- `cli-contract`: 检查编译/运行脚本的平台名、case_elf_asm、必需环境变量和个人路径回归。

  ```bash
  python3 scripts/check_hyptest_cli_contract.py --repo-root <repo_root>
  ```

- `repo-snapshot`: 只读汇总 case 源、注册状态、test_point 覆盖、产物和最新日志。

  ```bash
  python3 scripts/repo_snapshot.py --repo-root <repo_root>
  ```

- `baseline-diff`: 接受新 baseline 前查看新增/删除的 lint baseline 问题。

  ```bash
  python3 scripts/case_lint_baseline_diff.py --old <old_baseline.json> --new <new_baseline.json>
  ```

- `writeback-check`: 检查 test_point 轻量回填格式和注册一致性。

  ```bash
  python3 scripts/check_writeback_format.py --repo-root <repo_root> --file <test_point_file> --check-register --spec-profile <spec_profile>
  ```

### profile-and-tiering

- `profile-query`: 按地址汇总 PMA/PBMT/MMIO profile 规则。

  ```bash
  python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --summary
  ```

- `profile-registry`: 检查 profile 注册表和默认 profile 映射。

  ```bash
  python3 scripts/check_spec_profile_registry.py
  ```

- `new-profile`: 基于模板创建新的 spec profile 骨架并写入注册表。

  ```bash
  python3 scripts/new_spec_profile.py --name <profile_name> --title '<project/core title>' --update-registry
  ```

- `profile-decision`: 只输出匹配地址的 profile default_decision。

  ```bash
  python3 scripts/query_spec_profile.py --spec-profile <spec_profile> --address <pa> --decision-only
  ```

- `reason-code`: 根据失败现象给出候选 reason_code。

  ```bash
  python3 scripts/suggest_reason_code.py --symptom '<failure symptom>'
  ```

- `reason-code-eval`: 检查失败现象到 reason_code 建议的 eval 样例。

  ```bash
  python3 scripts/eval_reason_code_suggestions.py
  ```

- `failure-log`: 从失败日志提取场景、错误点、候选 reason_code 和下一步动作。

  ```bash
  python3 scripts/classify_failure_log.py --log-file <log> --json
  ```

- `triage-handoff`: 生成 workflow 交给 failure-triage 深入分析的交接卡片。

  ```bash
  python3 scripts/make_triage_handoff.py --log-file <log> --platform linknan --spec-profile <spec_profile> --json
  ```

### maintenance

- `readme-check`: 检查 README 生成命令块是否同步。

  ```bash
  python3 scripts/check_readme_commands.py
  ```

- `readme-update`: 刷新 README 生成命令块。

  ```bash
  python3 scripts/update_readme_commands.py
  ```

- `resource-index-check`: 检查 resource_index.md 是否覆盖 public scripts 和关键资产。

  ```bash
  python3 scripts/check_resource_index.py
  ```

- `manifest-check`: 检查 assets/script_manifest.json 是否与 scripts/*.py 同步。

  ```bash
  python3 scripts/update_script_manifest.py --check
  ```

- `manifest-update`: 新增或删除脚本后刷新 assets/script_manifest.json。

  ```bash
  python3 scripts/update_script_manifest.py --write
  ```

- `resource-index-update`: 刷新 resource_index.md 中的资源覆盖生成块。

  ```bash
  python3 scripts/update_resource_index.py --write
  ```

- `profile-portability`: 检查通用 skill 入口没有写死具体默认 profile。

  ```bash
  python3 scripts/eval_profile_portability.py
  ```

- `listed-command-help`: 检查 README/命令清单里的脚本仍然支持 --help。

  ```bash
  python3 scripts/eval_listed_commands_help.py
  ```

### cleanup

- `clean-generated`: 删除 skill 本地临时文件和缓存文件。

  ```bash
  python3 scripts/clean_generated.py --repo-root <repo_root>
  ```

### summary

- `skill-summary`: 汇总 profiles、references、scripts、eval assets 和推荐检查命令。

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
