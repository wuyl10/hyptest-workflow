# Maintainer Guide

本文给维护 `hyptest-workflow` skill 时使用。它不是 agent 执行规则入口；执行规则仍从 `SKILL.md` 开始。

## 修改原则

- 通用流程放 `SKILL.md` 或通用 `references/*.md`。
- 项目/规格事实只放 `references/spec_profiles/<profile>.md`。
- 资源清单只维护在 `references/resource_index.md`，`SKILL.md` 只保留精简入口。
- 脚本能机器检查的规则，优先落到 `scripts/check_*.py` 或 `scripts/eval_*.py`。

## 新增或修改 Profile

1. 优先用脚手架生成新 profile：

```bash
python3 scripts/new_spec_profile.py --name <name> --title "<project/core title>" --update-registry
```

也可以手工从 `references/spec_profiles/template.md` 复制新 profile。
2. 在 `references/spec_profiles/index.json` 注册 profile 名、路径、状态和说明。
3. 填写 `hyptest-profile` 机器可读块。
4. 填写 `hyptest-pma-pbmt-matrix` 和 `hyptest-mmio-responder-matrix` JSON fence。
5. 用查询脚本抽查关键窗口、PMA/PBMT 组合和 MMIO responder：

```bash
python3 scripts/query_spec_profile.py --spec-profile <name> --address <pa> --json
python3 scripts/query_spec_profile.py --spec-profile <name> --address <pa> --summary
python3 scripts/query_spec_profile.py --spec-profile <name> --address <pa> --decision-only
python3 scripts/query_spec_profile.py --spec-profile <name> --pma IO --pbmt IO
python3 scripts/query_spec_profile.py --spec-profile <name> --responder-target <target>
```

6. 跑：

```bash
python3 scripts/check_spec_profile_registry.py --policy all
python3 scripts/check_spec_profile.py --spec-profile <name> --strict
python3 scripts/eval_spec_profile_registry.py
python3 scripts/eval_spec_profile.py
python3 scripts/eval_profile_decisions.py
python3 scripts/eval_profile_portability.py
```

不要把 NHV5.1AP 的 no-H、PMP 粒度、PMA/PBMT/MMIO 表直接写入通用文档。

## 新增脚本

1. 新脚本放 `scripts/`。
2. 用 `python3 scripts/update_script_manifest.py --write` 刷新 `assets/script_manifest.json`。
3. 在 `references/resource_index.md` 加一条说明；不确定缺项时先跑 `python3 scripts/update_resource_index.py --suggest`。
4. 如脚本属于维护/门禁检查，确认 `scripts/self_check.py` 会通过 manifest 覆盖它。
5. 若脚本暴露公共行为，补一个轻量 eval 或 smoke fixture。
6. 跑：

```bash
python3 scripts/update_script_manifest.py --check
python3 scripts/check_skill_consistency.py
python3 scripts/check_resource_index.py
python3 scripts/list_skill_commands.py
python3 scripts/skill_summary.py
python3 scripts/self_check.py --quick --spec-profile <spec_profile>
```

## 修改相似检索

相似检索模块拆分如下：

- `scripts/case_extractor.py`：case 提取、注册状态、helper 关系、缓存 builder。
- `scripts/similar_case_terms.py`：term/Markdown 提取和打分基础。
- `scripts/term_aliases.py`：term canonical key、alias 展开、canonical 去重。
- `scripts/markdown_sections.py`：Markdown heading section split/filter/index 选择。
- `scripts/similar_case_ranker.py`：相似度排序、多样性选择、retrieval assessment。
- `scripts/similar_case_render.py`：snippet、match note、reading pack。
- `scripts/similar_case_core.py`：兼容旧 import 的 re-export，不继续堆新逻辑。

修改后至少跑：

```bash
python3 scripts/check_hyptest_cli_contract.py --repo-root <repo_root>
python3 scripts/eval_hyptest_cli_contract.py
python3 scripts/eval_find_similar_cache.py
python3 scripts/eval_workflow_smoke.py
```

有 hyptest 仓库时再跑：

```bash
python3 scripts/eval_find_similar_cases.py --repo-root <repo_root>
python3 scripts/find_similar_cases.py --repo-root <repo_root> --query "<scenario>" --limit 3 --explain-score
```

## 修改 Reason Code

1. 同时更新 `references/reason_code_catalog.md` 和 `assets/reason_codes.json`。
2. JSON 字段必须包含 `code`、`class`、`default_decision`、`meaning`、`typical_followup`、`owner`、`next_required_evidence`。
3. 更新 `scripts/suggest_reason_code.py` 的关键词映射，保证常见现象能返回合理候选。
4. 抽查一个现象：

```bash
python3 scripts/suggest_reason_code.py --symptom "PMA PBMT MMIO no responder" --json
```

5. 跑：

```bash
python3 scripts/check_reason_codes.py
```

## 修改 Case Lint 或 Writeback Checker

改 `scripts/check_case_lint.py` 后跑：

```bash
python3 scripts/eval_check_case_lint.py
python3 scripts/check_case_lint.py --repo-root <repo_root> --changed-only --strict-case-end
python3 scripts/check_case_lint.py --repo-root <repo_root> --changed-only --strict-case-end --warnings-as-errors
python3 scripts/check_case_lint.py --repo-root <repo_root> --baseline assets/baselines/case_lint_baseline.json --warnings-as-errors
```

若历史 warning 太多，先生成 baseline，再只关注新增问题：

```bash
python3 scripts/check_case_lint.py --repo-root <repo_root> --write-baseline assets/baselines/case_lint_baseline.json
```

改 `scripts/check_writeback_format.py` 后跑：

```bash
python3 scripts/eval_check_writeback_format.py
```

`test_register.c` 注册状态解析在 `scripts/writeback_register.py`，若修改该部分也跑同一个 eval。

对真实仓库做快速增量检查：

```bash
python3 scripts/check_case_lint.py --repo-root <repo_root> --changed-only --strict-case-end
python3 scripts/check_writeback_format.py --repo-root <repo_root> --file <test_point_file> --check-register --spec-profile <spec_profile>
```

## Repo Migration Checks

目录、平台名或生成物命名变更后，检查真实 hyptest 仓库是否还残留旧逻辑：

```bash
python3 scripts/check_hyptest_repo_migration.py --repo-root <repo_root>
python3 scripts/doctor.py --repo-root <repo_root> --check-repo-migration --skip-self-check
```

这个检查只用于重构回归。正常规则入口仍是 `references/repo_layout.md`。

## Generated Cleanup

skill eval 和自检产生的中间文件放在 skill root 下的 `.hyptest_skill_tmp/` / `.hyptest_skill_cache/`。

验证结束后跑：

```bash
python3 scripts/clean_generated.py --repo-root <repo_root>
```

## Cross-Skill Consistency

`hyptest-workflow` 负责写 case、编译运行和分层初判。

`hyptest-failure-triage` 负责 selfcheck/stuck/difftest mismatch/FSDB/疑似 RTL bug 的失败闭环。

修改任一 skill 的触发词、旧路径、平台名或失败分类时，跑：

```bash
python3 scripts/check_cross_skill_consistency.py
python3 scripts/eval_joint_handoff.py
```

若 workflow 交给 triage 的字段变化，同时更新：

```text
references/triage_handoff_schema.md
/nfs/home/wuyuanlong/.agents/skills/hyptest-failure-triage/SKILL.md
```

## 推荐自检顺序

快速：

```bash
python3 scripts/self_check.py --quick --spec-profile <spec_profile>
```

带真实 hyptest 仓库但不依赖仿真器环境：

```bash
python3 scripts/self_check.py --repo --repo-root <repo_root> --spec-profile <spec_profile>
```

检查平台环境变量：

```bash
python3 scripts/self_check.py --platform-check --repo-root <repo_root> --platform spike --spec-profile <spec_profile>
python3 scripts/self_check.py --platform-check --repo-root <repo_root> --platform linknan --spec-profile <spec_profile>
python3 scripts/check_env.py --repo-root <repo_root> --platform all --explain --print-exports
```

完整检查：

```bash
python3 scripts/self_check.py --full --repo-root <repo_root> --spec-profile <spec_profile>
python3 scripts/self_check.py --full --repo-root <repo_root> --spec-profile <spec_profile> --json --json-out .hyptest_skill_reports/self_check_full.json --md-out .hyptest_skill_reports/self_check_full.md
```

综合健康检查：

```bash
python3 scripts/doctor.py --repo-root <repo_root> --pre-submit --strict --platform spike --spec-profile <spec_profile>
```

## 修改 README 命令块

README 的“常用命令”由 `scripts/list_skill_commands.py` 生成。改命令清单后跑：

```bash
python3 scripts/update_readme_commands.py
python3 scripts/list_skill_commands.py --markdown
```

## 修改任务参数或失败日志规则

任务参数规格入口：

```bash
python3 scripts/validate_task_request.py --repo-root <repo_root> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1-3
```

失败日志分类入口：

```bash
python3 scripts/classify_failure_log.py --log-file <log> --json
python3 scripts/eval_failure_log_workflow.py
```
