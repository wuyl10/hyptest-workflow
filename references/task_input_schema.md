# Task Input Schema

本文是人工和 agent 共用的任务参数规格入口。它描述一次 `hyptest-workflow`
任务建议提供哪些字段、默认值是什么、哪些组合需要先确认。

## Required Fields

| Field | Required When | Value | Notes |
| --- | --- | --- | --- |
| `HYPTEST_HOME` | 需要读写 hyptest 仓库且当前环境没有 `HYPTEST_HOME` 时 | path | 指向 `riscv-hyp-tests` 仓库根目录（具体 fork/分支以团队约定为准）；可直接写路径或写 `$HYPTEST_HOME`。脚本 CLI 内部仍使用 `--repo-root`。 |
| `spec_profile` | 可省略 | profile name/path | 规格/平台口径名称；用于判断 Spike gate、模型边界和分层。默认 profile registry 的 `default_profile`；可显式指定 `references/spec_profiles/<name>.md`。 |
| `platform` | 需要编译/运行/环境检查时 | `spike` / `linknan` | hyptest 平台名只使用这两个值。 |
| `test_point_file` | 新增/回填测试点时 | path | `test_point` 容器文件；每个 `### PnX` 才是独立测试点。 |
| `task_mode` | 新增/修改 case 时 | enum | 常用值见下表。 |

路径字段支持 shell 风格的 `$VAR` 展开，便于复用团队已有变量。统一规则是：当前执行环境已经能读到，就可以在 prompt 里省略；读不到、但本轮必需的变量才在 prompt 里显式写。对外 prompt 统一用 `HYPTEST_HOME` 表示 `riscv-hyp-tests` 仓库位置；脚本 CLI 内部的 `--repo-root` 是同一含义的参数名。

如果这些变量写在 `~/.bashrc`，应放在非交互 shell 提前 `return` 的保护之前。很多自动化命令不是从你当前 VS Code 终端进程继承环境，而是另起 shell；变量放在交互式保护之后时，终端里看起来正常，`check_env.py` / `get_result.py` 仍可能读不到。

缺失处理：

- 会编译/运行/落地的任务，只需要补当前进程看不到的必需环境变量；与本轮平台无关的组件可以省略。
- 需要 hyptest 仓库但 prompt 没写 `HYPTEST_HOME`、当前环境也没有 `HYPTEST_HOME`：先提醒调用者补 `HYPTEST_HOME: <riscv-hyp-tests 仓库根目录>` 或设置 `HYPTEST_HOME`。
- `platform=spike` 且本轮会运行 `get_result.py`，但 prompt 没写 `HYPTEST_SPIKE_BIN`、当前环境也没有 `HYPTEST_SPIKE_BIN`：先提醒调用者补 `HYPTEST_SPIKE_BIN: <community/upstream Spike 可执行文件>` 或设置 `HYPTEST_SPIKE_BIN`。
- `platform=linknan` 且本轮会运行 `get_result.py`，但缺 `HYPTEST_LINKNAN_HOME` 或 `HYPTEST_DIFFTEST_REF_SO`：先提醒调用者补缺失字段。
- 需要 Nanhu RTL/source 证据时，workflow 固定从 `HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main` 推导；如果路径不存在，提醒初始化 LinkNan 的 `dependencies/nanhu` submodule 或修正 `HYPTEST_LINKNAN_HOME`。
- 无关组件直接省略。
- prompt 显式写的路径优先于环境变量；执行 hyptest runner 相关脚本时，运行环境字段映射成 `--env KEY=VALUE`。`HYPTEST_WORKFLOW_SKILL_HOME` 只用于定位 workflow skill 自带脚本，不映射成 runner `--env`。
- prompt 写成 `$VAR` 但当前执行环境无法展开时，视为缺失，而不是有效路径。

## Optional Fields

| Field | Default | Value | Notes |
| --- | --- | --- | --- |
| `case_name` | none | string | 单 case 编译/运行/定位时建议提供。 |
| `new_case_count` | `1` | integer/range | `new-case-only` 时建议提供，例如 `1-3`。 |
| `coverage_scope` | auto | `file` / `repo` | 一般不用填；workflow 根据任务目的推导。补已有点默认 `file`；新增测试点或跨文件排重默认 `repo`。 |
| `target_policy` | `default-first` | enum | 可选 `default-first`、`manual-ok`、`compile-only-ok`。 |
| `reason_code` | none | catalog code | 已有结论时可指定；否则由日志/profile 推断。 |
| `failure_log` | none | path/text | 失败归因或分层初判时提供。 |

## Optional Waveform Handoff Fields

这些字段只用于 workflow 生成 workflow-to-triage handoff，不代表 workflow 直接做波形分析。若任务是 hyptest 失败闭环，即使已经有 FSDB，也先把这些字段交给 `hyptest-failure-triage`，由它决定是否调用 `waveform-debug` 并最终收口。

| Field | Default | Value | Notes |
| --- | --- | --- | --- |
| `waveform_path` | none | path | FSDB/VCD/FST 路径；用于 `make_triage_handoff.py --waveform-path`。 |
| `rtl_root` | none | path | RTL/source 根目录；常见值是 `$HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main`。 |
| `top_module` | none | string | waveform-debug 需要的 top module 名。 |
| `debug_target` | none | text | first-bad-cycle、握手、协议或具体信号问题。 |
| `time_window` | none | text | 已知失败时间窗或 cycle 范围。 |
| `expected_behavior` | none | text | 预期行为，用于后续波形报告对照。 |
| `observed_behavior` | none | text | 当前日志/现象中观察到的行为。 |
| `waveform_report` | none | path | 已有或建议产出的 waveform-debug `report.md` 路径。 |

## Conditional Runner Path Fields

| Field | Required When | Value | Notes |
| --- | --- | --- | --- |
| `HYPTEST_SPIKE_BIN` | `platform=spike` 且当前环境没有 `HYPTEST_SPIKE_BIN` 时 | executable path | 本轮 `platform=spike` 指定社区版/上游 Spike，用于 architecture/default gate；可直接写路径或写 `$HYPTEST_SPIKE_BIN`，脚本参数写作 `--env HYPTEST_SPIKE_BIN=<path>`。 |
| `HYPTEST_LINKNAN_HOME` | `platform=linknan` 或需要读取 LinkNan/Nanhu 源码证据，且当前环境没有 `HYPTEST_LINKNAN_HOME` 时 | path | 本轮 `platform=linknan` 指定 LinkNan workspace；脚本参数写作 `--env HYPTEST_LINKNAN_HOME=<path>`。 |
| `HYPTEST_DIFFTEST_REF_SO` | `platform=linknan` 且当前环境没有 `HYPTEST_DIFFTEST_REF_SO` 时 | file path | 本轮 LinkNan difftest 指定参考模型 so，通常来自项目定制 Spike；脚本参数写作 `--env HYPTEST_DIFFTEST_REF_SO=<path>`。 |
| `HYPTEST_TMPDIR` | 可省略 | path | `/tmp` 空间不足时指定临时目录；脚本参数写作 `--env HYPTEST_TMPDIR=<path>`。 |
| `HYPTEST_WORKFLOW_SKILL_HOME` | 手动运行 workflow 自带脚本时 | path | 指向 `hyptest-workflow` skill 目录；用于 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/<tool>.py`，不传给 hyptest repo runner。 |

这些字段不是长期配置要求。若 shell 环境已经正确设置，prompt 不必填写；若 shell 环境没有对应变量，prompt 必须填写。若 prompt 显式填写，workflow 执行脚本时应把它们映射成重复的 `--env KEY=VALUE` 参数。Nanhu 源码是 LinkNan submodule 检查项，不是 prompt 环境字段。

常见路径组合：

- Spike-only：需要 `HYPTEST_HOME`、`HYPTEST_SPIKE_BIN`；环境已有则 prompt 可全部省略。
- Spike + LinkNan 源码证据：需要 `HYPTEST_HOME`、`HYPTEST_SPIKE_BIN`、`HYPTEST_LINKNAN_HOME`；Nanhu 源码固定从 `HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main` 推导。
- LinkNan gate：需要 `HYPTEST_HOME`、`HYPTEST_LINKNAN_HOME`、`HYPTEST_DIFFTEST_REF_SO`；`HYPTEST_SPIKE_BIN` 与本轮无关时可省略。
- `HYPTEST_CROSS_COMPILE` 是工具链前缀；只有默认 `riscv64-unknown-elf-` 不适用或当前 PATH 找不到工具链时才在 prompt 中显式写。直接调用 hyptest 仓库 `make` 时仍按仓库原接口写 `CROSS_COMPILE=...`。

runner 角色不要混用：`HYPTEST_SPIKE_BIN` 用于社区版/上游 Spike 的 `platform=spike` gate；定制 Spike/difftest 证据走 `HYPTEST_LINKNAN_HOME` + `HYPTEST_DIFFTEST_REF_SO`；Nanhu 源码证据走 LinkNan submodule 的 `dependencies/nanhu/src/main`。

## `task_mode`

| Value | Meaning | Required Extra |
| --- | --- | --- |
| `new-case-only` | 新增测试点和新 case。 | `test_point_file`、`new_case_count` |
| `supplement-existing-point` | 给已有 `### PnX` 补 case。 | `test_point_file`、目标 `### PnX` 或明确条目文本 |
| `fix-case` | 修改已有 case。 | `case_name` 或明确文件路径 |
| `preflight-only` | 只读预检、找新增空间、准备 prompt 或会议演示，不编译运行。 | `test_point_file` |
| `run-only` | 只编译/运行，不改代码。 | `platform`、`case_name` |
| `triage-only` | 只分析日志/失败，不改代码。 | `failure_log` 或日志文本 |
| `writeback-only` | 只回填/整理 `test_point`。 | `test_point_file` |

## Defaults

- 未指定 `spec_profile` 时默认使用 profile registry 中的 `default_profile`。它表示当前项目的规格/平台口径，不是功能开关；正式新增 case 时建议显式写出当前项目 profile。
- 未指定 `coverage_scope` 时：
  - 明确已有 `### PnX` 或补已有点，自动按 `file`。
  - `new-case-only`、`preflight-only`、继续找 suspected bug point 或要求跨文件排重，自动按 `repo`。
  - case 相似检索始终是 repo 级，不随 `coverage_scope=file` 缩小。
- 未指定 `target_policy` 时按 `default-first`。
- `platform=xiangshan` 不是 hyptest 平台名，应改为 `platform=linknan`。

## Preflight

开工前可用：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/validate_task_request.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --platform spike \
  --spec-profile <spec_profile> \
  --task-mode new-case-only \
  --new-case-count 1-3
```

该脚本只做参数和路径预检；通过不代表 case 质量、编译或仿真一定通过。
