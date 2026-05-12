# hyptest-workflow

用户面向入口。`hyptest-workflow` 用于 `riscv-hyp-tests`（`$HYPTEST_HOME` 指向的工作目录）的 hyptest 测试点落地闭环：把 `test_point` 里的测试意图推进到可追踪的 case、注册状态、编译运行证据、分层结论和轻量回填。

Agent 被触发后执行的硬规则和流程步骤在 `SKILL.md`；本文件只讲**怎么用**。

## 入口文件

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | Agent 执行入口——触发、硬规则、Workflow 流程、Bug Hunt Evidence、输出默认 |
| `README.md` | 你现在看的文件——用法、字段速查、常见场景、环境 |
| `references/command_index.md` | 完整命令索引（由 `scripts/list_skill_commands.py --markdown` 生成）|
| `references/quick_execution.md` | Gate-0..7 快速闭环细节 |
| `references/task_input_schema.md` | 任务输入字段、task_mode、preflight 完整 schema |
| `references/coverage_and_dedupe.md` | 测试点覆盖检查、case 去重和唯一性证据口径 |
| `references/spec_and_model_limits.md` + `references/spec_profiles/` | 规格/profile 路由，PMA/PBMT/MMIO/cache/TLB/CBO 等模型边界 |
| `references/writing_cases.md` | case 编写、断言、回填格式、复用依据 |
| `references/quality_gate.md` / `references/tiering_decision.md` / `references/reason_code_catalog.md` | Gate A-H、分层裁决、原因码目录 |
| `references/cause_code_catalog.md` | `excpt.cause` 断言常量速查表 |
| `references/resource_index.md` | 完整资源索引（含 scripts 和 evals） |
| `references/maintainer_guide.md` | 修改 skill、脚本、profile、eval 后的维护检查 |

## 什么时候使用

以下任务或关键词会触发本 skill：

- 新增、补充或修复 hyptest case（`ai_test_cases/` 或 `manual_test_cases/`）
- 新增或回填 `test_point/*.md` 的 `### PnX` 条目
- 更新 `test_register.c` 注册状态
- 跨 `test_point/*.md` 排重、扩点
- 围绕某模块找 suspected bug point 并写新测试点
- 编译单 case、小批量 case
- 跑 Spike / LinkNan 并输出运行日志
- 做 `default/manual/compile-only/blocked` 初判分层
- 需要把一次 case 交付整理成"新增 case、唯一性证据、编译/运行结果、日志路径和最终决策"

**不触发**（转给其它 skill）：

- 只看 Spike/LinkNan 失败日志不落新 case、FSDB/stuck/50000 cycles no commit/`HIT GOOD TRAP` but `FAILED`/difftest mismatch/suspected RTL bug 深挖 → `hyptest-failure-triage`
- 波形 first-bad-cycle / 握手 / 协议 / X-state 分析 → `waveform-debug`
- 纯 RISC-V 知识问答 / Spike 工具链参数 / 解析 ELF / 通用代码 review → 一般对话

## 目标仓库和环境

日常 prompt 不需要写完整环境清单。规则是：当前执行环境已经能读到的变量可以省略；读不到、但本轮必需的变量才写进 prompt。对外统一使用 `HYPTEST_HOME` 和 `HYPTEST_*`，不要写个人绝对路径或其它项目的通用变量名。

| 变量名 | 路径 |
| --- | --- |
| `HYPTEST_HOME` | `riscv-hyp-tests` 仓库路径 |
| `HYPTEST_SPIKE_BIN` | 单跑 ELF 的 spike bin（建议社区版）|
| `HYPTEST_LINKNAN_HOME` | Linknan 仓库路径 |
| `HYPTEST_DIFFTEST_REF_SO` | Linknan difftest 的 golden ref（Linknan 维护的 riscv64-spike-so）|
| `HYPTEST_TMPDIR` | `/tmp` 不够时的临时目录（可省）|

注：Nanhu 源码不单独设置环境变量，固定从 `HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main` 推导。

常见组合：

| 场景 | 需要当前进程可见 |
| --- | --- |
| Spike 编译/运行 gate | `HYPTEST_HOME` + `HYPTEST_SPIKE_BIN` |
| Spike gate + LinkNan/Nanhu 源码证据 | `HYPTEST_HOME` + `HYPTEST_SPIKE_BIN` + `HYPTEST_LINKNAN_HOME` |
| LinkNan / difftest gate | `HYPTEST_HOME` + `HYPTEST_LINKNAN_HOME` + `HYPTEST_DIFFTEST_REF_SO` |

需要检查环境时运行：

```bash
python3 scripts/check_env.py --repo-root $HYPTEST_HOME --platform all --explain
```

平台名只使用 `spike` 或 `linknan`。

## Repo Anchors（目标仓库结构速查）

完整 layout 见 `references/repo_layout.md`；快速锚点：

- 框架宏与异常结构：`inc/rvh_test.h`
- 框架实现：`src/`
- 全局汇编入口：`asm/`
- 注册表：`test_register.c`
- AI 用例目录：`ai_test_cases/`
- 人工维护用例目录：`manual_test_cases/`
- 编译脚本：`compile_elf.py`
- 批跑脚本：`get_result.py`
- 项目规则：`test_point/Manual_Reference.md`
- 历史线索：`test_point/CRITICAL_ISSUES_LOG.md`
- workflow 生成状态：`.hyptest_workflow_skill/cache/` / `reports/` / `tmp/` / `memory/`（清理/CLI 见 `references/workflow_state.md`）

## 怎么用（自然语言触发）

用**自然语言**就能触发本 skill。skill 被触发后会按 `SKILL.md` 自动执行完整流程（repo 级覆盖检查、case 相似检索、函数名唯一性、lint、回填核对、映射表输出等），**不需要在 prompt 里复制执行清单**。

### 一句话范例

正常新增 case：

```
"帮我给 test_point/memblock_suspected_bug_corner_points_15.md 新增 1 个 case，
验证 same-page cross-16B sd 在 repair 后再一次 sw 的 boundary image 保持"
```

围绕模块找 bug 点：

```
"围绕 memblock 找 1 个高价值 suspected bug 点并新增 case，
test_point_file=test_point/memblock_suspected_bug_corner_points_15.md"
```

补已有 `### PnX`：

```
"给 test_point/<xxx>.md 的 ### P6B 补一个 case，聚焦 boundary preserved 方向"
```

给已有 case 补断言：

```
"给 ai_micro_foo 补一条邻接地址断言，不改函数名也不加新 case"
```

修已有 case：

```
"ai_micro_foo 在 Spike 上 FAILED + cause 断言值对不上，帮我修一下"
```

只跑已有 case：

```
"只跑 ai_micro_foo 这条 case 的 Spike 单测，输出结果和日志路径"
```

开写前摸底：

```
"看一下 test_point/<xxx>.md 当前还有没有新增空间，哪些方向值得优先补"
```

交 triage：

```
"ai_micro_foo 批跑挂了 50000 cycles no commit，帮我生成 triage handoff 卡片"
```

### 字段速查（自然语言不够时再写）

大多数任务自然语言就够了。以下字段在 skill 没正确推断、或你想精准覆盖时可以**在 prompt 里显式写**（`field=value` 或 `field: value` 都行）：

| 字段 | 什么时候写 | 含义 / 取值 |
| --- | --- | --- |
| `test_point_file` | 新增/补点/回填任务必写 | 测试点容器文件；按 `$HYPTEST_HOME` 解析；例 `test_point/memblock_suspected_bug_corner_points_15.md` |
| `platform` | 要编译/运行时写（默认 `spike` 可省） | `spike` / `linknan` |
| `spec_profile` | 正式新增/分层建议写（可省走 registry 默认） | 当前项目规格口径；决定 Spike gate 和模型边界；切项目时改 `references/spec_profiles/index.json` 的 `default_profile` |
| `task_mode` | 建议显式写 | `new-case-only` / `supplement-existing-point` / `fix-case` / `run-only` / `preflight-only` / `triage-only` / `writeback-only` |
| `target_module` | **bug hunt 任务必写** | 模块名；**拼写一定要对**（`memblock` 不是 `mmemblock`）否则 `query_rtl_bug_history` 会空手回 |
| `target_test_point` | 补已有条目时写 | `"### P<id>. <title>"` |
| `case_name` | `run-only` / `fix-case` / 补 assert 时写 | 目标 case 名 |
| `new_case_count` | 新增 case 建议写 | 默认 1；多个 case 要说明每个覆盖差异 |
| `bug_hunt_focus` | bug hunt 建议写 | 关注方向，例 `"CMO / LRSC / fence"` |
| `target_policy` | 可省，默认 `default-first` | `default-first` / `manual-ok` / `compile-only-ok` |
| `failure_log` | `triage-only` | 失败日志路径 `.tmp/result_log/<platform>/<log>` |

**`spec_profile` 具体值**：当前项目默认是 profile registry 里的 `default_profile`。示例（正式任务建议显式写）：

```text
spec_profile: nhv5_1_ap
```

**环境变量字段**（`HYPTEST_HOME` / `HYPTEST_SPIKE_BIN` / `HYPTEST_LINKNAN_HOME` / `HYPTEST_DIFFTEST_REF_SO` / `HYPTEST_TMPDIR`）只在当前进程看不到时补写；shell 已 export 就不用写。详细口径见 `references/task_input_schema.md`。

### 需要完整 pack 报告时

默认不跑 pack 聚合工具（`case_preflight_pack` / `case_gate_pack` / `submission_card` / `ledger`），走预热+轻量直通路径（约 2-3 分钟）。需要标准报告/多人协作/复盘耗时时，prompt 里加一句"跑完整 pack"或"输出 submission card"，skill 会切到 pack 路径。

### 反例（常见坑）

- **`target_module` 拼错**（`mmemblock` / `strorequeue`）→ `query_rtl_bug_history` 空手回，让你以为没 bug
- **只写"帮我补几个 case"**，不带 `test_point_file` / `task_mode` → skill 要停下来问（或随意推导错方向）
- **`new_case_count: 1-3` 却不说每个 case 的覆盖差异** → agent 容易写出相似 3 个，重复且浪费
- **把 SKILL.md 的"执行步骤 / 质量门禁"整段复制到 prompt 里** → 冗余，且容易和 SKILL.md 漂移
- **bug hunt 任务不给 `target_module`** → skill 没法跑 `query_rtl_bug_history` / `query_uncovered_bug_neighbors`，退化成纯源码 speculation
- **把大量审计证据写回 `test_point`**（Gate 结果 / 分层结论 / 编译统计）→ `test_point` 是意图描述不是审计日志；证据应放最终交付摘要或 pack 报告
- **要求"全量编译 / 全量跑"作为单 case 流程** → 显著拖慢，且单 case 任务本来不需要
- **task_mode=new-case-only 但 prompt 暗示"只是改一下"** → 模式判定摇摆；明确写目标"新增测试点和新 case"或改成 `supplement-existing-point`

## 常见场景速查

下表是**场景提醒**，不是硬判断。完整规则和 Source Priority 以 `SKILL.md` 为准。

| 场景 | 先查什么 | 初始处理 |
| --- | --- | --- |
| 新增普通架构 case | `references/spec_profiles/<spec_profile>.md` + 相似 case | 按 Gate 跑完后落位；Spike 跑通即 `default` |
| PMA/PBMT/MMIO/cache/TLB/CBO 等 profile-sensitive case | `scripts/query_spec_profile.py` + profile 的 Spike gate | `spike_gate_applicable=false` 属于**提醒**：Gate 先跑；若 RTL/difftest 暴露差异再转 `hyptest-failure-triage` 反向降级 |
| 访问 MMIO/Device 区间 | profile 的 MMIO responder 表 | 同上；若 Spike 无 responder 导致 `FAILED`/`untested`，按运行结果归因 `manual` / `blocked` |
| 只改回填或注册状态 | `test_register.c` + `scripts/check_writeback_format.py --check-register` | 保证 `已实现 case` 状态与注册一致 |
| Spike/LinkNan 运行失败 | `references/build_run_debug.md` + `references/tiering_decision.md` | 先定位用例/assert/环境/model gap，再给 `reason_code` |
| 不确定 `reason_code` | `scripts/suggest_reason_code.py --symptom "<现象>"` | 把建议当候选，最终仍以日志和 profile 证据为准 |

## 分层口径

| 分层 | 含义 | 注册状态 |
| --- | --- | --- |
| `default` | 编译通过、运行通过、规则一致、Spike gate 适用、证据完整 | `TEST_REGISTER(case_name);` 开启 |
| `manual` | 场景合理，但不适合常规 Spike gate，或需要人工/RTL 环境确认 | 通常注释注册 |
| `compile-only` | 当前只保证可编译，运行 gate 不成立或阶段性不运行 | 通常注释注册 |
| `blocked` | 编译、运行、规则、证据或注册一致性存在阻塞 | 不作为完成落位 |

`default-first` 的意思是优先争取 default，不是无条件放 default。PMA/PBMT/MMIO/cache/TLB/CBO 等场景必须先看 profile；如果 `spike_gate_applicable=false`，不能只凭 official Spike 结果作为 default gate。

## 硬规则速记

硬规则的真值在 `SKILL.md` 的 `Non-Negotiables`；本处不再维护副本以避免漂移。触发 skill 时以 `SKILL.md` 为准。

## 自检

修改本 skill 后运行：

```bash
python3 scripts/check_readme_commands.py
python3 scripts/check_docs_links.py
python3 scripts/check_skill_consistency.py
python3 scripts/check_resource_index.py
python3 scripts/update_resource_index.py --check
```

完整快速自检：

```bash
python3 scripts/self_check.py --quick --spec-profile <spec_profile>
```

## 最终答复要求

默认用中文，结论要具体。完成一次 case 工作后至少输出：

- 实际使用的规格/平台口径（`spec_profile`）。
- 新增或修改的 case 名和文件路径。
- 唯一性证据：测试点覆盖检查、相似 case 检索、函数名唯一性检查。
- 编译命令、编译结果、ELF/ASM 路径。
- 运行命令、运行结果、关键日志路径。
- `test_point` 回填位置和 `test_register.c` 注册状态。
- `test_point → case 映射表`：逐条列出 test_point 要求对应到 case 哪一行断言。
- 最终决策：`default` / `manual` / `compile-only` / `blocked`。
- 如果不是 `default`，给出 `reason_code` 和简要原因。
