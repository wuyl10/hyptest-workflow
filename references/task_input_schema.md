# Task Input Schema

本文是人工和 agent 共用的任务参数规格入口。它描述一次 `hyptest-workflow`
任务建议提供哪些字段、默认值是什么、哪些组合需要先确认。

## Required Fields

| Field | Required When | Value | Notes |
| --- | --- | --- | --- |
| `repo_root` | 所有需要读写 hyptest 仓库的任务 | path | 指向 `riscv-hyp-tests-nhv5.1` 仓库根目录。 |
| `spec_profile` | 可省略 | profile name/path | 默认 profile registry 的 `default_profile`；可显式指定 `references/spec_profiles/<name>.md`。 |
| `platform` | 需要编译/运行/环境检查时 | `spike` / `linknan` | hyptest 平台名只使用这两个值。 |
| `test_point_file` | 新增/回填测试点时 | path | `test_point` 容器文件；每个 `### PnX` 才是独立测试点。 |
| `task_mode` | 新增/修改 case 时 | enum | 常用值见下表。 |

路径字段支持 shell 风格的 `$VAR` 展开，便于复用团队已有的仓库路径变量。`repo_root` 本身是 workflow 输入，不是 hyptest 平台环境变量；若团队需要变量，建议约定 `HYPTEST_REPO` 作为 `riscv-hyp-tests` 仓库位置的便利别名。`SPIKE_BIN`、`LINKNAN_HOME`、`DIFFTEST_REF_SO`、`CROSS_COMPILE` 等编译/运行变量按 hyptest 仓库环境说明设置。

## Optional Fields

| Field | Default | Value | Notes |
| --- | --- | --- | --- |
| `case_name` | none | string | 单 case 编译/运行/定位时建议提供。 |
| `new_case_count` | `1` | integer/range | `new-case-only` 时建议提供，例如 `1-3`。 |
| `coverage_scope` | auto | `file` / `repo` | 补已有点优先 `file`；新增测试点或跨文件排重用 `repo`。 |
| `target_policy` | `default-first` | enum | 可选 `default-first`、`manual-ok`、`compile-only-ok`。 |
| `reason_code` | none | catalog code | 已有结论时可指定；否则由日志/profile 推断。 |
| `failure_log` | none | path/text | 失败归因或分层初判时提供。 |

## `task_mode`

| Value | Meaning | Required Extra |
| --- | --- | --- |
| `new-case-only` | 新增测试点和新 case。 | `test_point_file`、`new_case_count` |
| `supplement-existing-point` | 给已有 `### PnX` 补 case。 | `test_point_file`、目标 `### PnX` 或明确条目文本 |
| `fix-case` | 修改已有 case。 | `case_name` 或明确文件路径 |
| `run-only` | 只编译/运行，不改代码。 | `platform`、`case_name` |
| `triage-only` | 只分析日志/失败，不改代码。 | `failure_log` 或日志文本 |
| `writeback-only` | 只回填/整理 `test_point`。 | `test_point_file` |

## Defaults

- 未指定 `spec_profile` 时默认使用 profile registry 中的 `default_profile`。
- 未指定 `coverage_scope` 时：
  - 明确已有 `### PnX` 或补已有点，按 `file`。
  - `new-case-only` 或要求跨文件排重，按 `repo`。
- 未指定 `target_policy` 时按 `default-first`。
- `platform=xiangshan` 不是 hyptest 平台名，应改为 `platform=linknan`。

## Preflight

开工前可用：

```bash
python3 scripts/validate_task_request.py \
  --repo-root <repo_root> \
  --test-point-file <test_point_file> \
  --platform spike \
  --spec-profile <spec_profile> \
  --task-mode new-case-only \
  --new-case-count 1-3
```

该脚本只做参数和路径预检；通过不代表 case 质量、编译或仿真一定通过。
