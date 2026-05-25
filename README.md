# hyptest-workflow

用户面向入口。`hyptest-workflow` 用于 `riscv-hyp-tests`（`$HYPTEST_HOME` 指向的工作目录）的 hyptest 测试点落地闭环：把 `test_point` 里的测试意图推进到可追踪的 case、注册状态、编译运行证据、分层结论和轻量回填。

Agent 被触发后执行的硬规则和流程步骤在 `SKILL.md`；本文件讲**怎么用**。

## 什么时候使用

触发场景：

- 新增、补充或修复 hyptest case（`ai_test_cases/` 或 `manual_test_cases/`）
- 新增或回填 `test_point/**/*.md` 的 `### PnX` 条目
- 更新 `test_register.c` 注册状态
- 跨 `test_point/**/*.md` 排重、扩点
- 围绕某模块找 suspected bug point 并写新测试点
- 编译单 case、小批量 case
- 跑 Spike / LinkNan 并输出运行日志
- 做 `default/manual/compile-only/blocked` 初判分层

**不触发**（转给其它 skill）：

- 只看 Spike/LinkNan 失败日志不落新 case、FSDB/stuck/50000 cycles no commit/`HIT GOOD TRAP` but `FAILED`/difftest mismatch/suspected RTL bug 深挖 → `hyptest-failure-triage`
- 波形 first-bad-cycle / 握手 / 协议 / X-state 分析 → `waveform-debug`
- 纯 RISC-V 知识问答 / Spike 工具链参数 / 解析 ELF / 通用代码 review → 一般对话

## 怎么用

skill 被触发后会按 `SKILL.md` 自动执行完整流程（repo 级覆盖检查、case 相似检索、函数名唯一性、lint、回填核对、映射表输出等），prompt 里不用复制执行清单。

### 一句话范例

根据给定测试场景编写用例：

```
"帮我新增 1 个 case：
验证 same-page cross-16B sd 在 repair 后再一次 sw 的 boundary image 保持"
```

根据给定测试点新增用例并反标：

```
"给 <某测试点文件路径> 进行测试点的用例编写并反标，
针对未反标的测试点按照测试点描述严格覆盖"
```

围绕模块找 bug 点、补测试点并新增用例反标：

```
"围绕 memblock 找 1 个高价值 suspected bug 点并新增 case，
test_point_file=test_point/suspected/memblock/memblock_suspected_bug_corner_points_15.md"
```

补已有 `### PnX`：

```
"给 test_point/suspected/<module>/<xxx>.md 的 ### P6B 补一个 case，聚焦 boundary preserved 方向"
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
"看一下 test_point/suspected/<module>/<xxx>.md 当前还有没有新增空间，哪些方向值得优先补"
```

交 triage：

```
"ai_micro_foo 批跑挂了 50000 cycles no commit，帮我生成 triage handoff 卡片"
```

### 字段速查

skill 能从 prompt 里自动推断大部分字段。下表按"什么时候写"分两组。

**必写字段**：

| 字段 | 什么时候写 | 取值 |
| --- | --- | --- |
| `test_point_file` | 新增/补点/回填任务 | 测试点容器文件；按 `$HYPTEST_HOME` 解析；例 `test_point/suspected/memblock/memblock_suspected_bug_corner_points_15.md` |
| `target_module` | bug hunt 任务 | 模块名；**拼写必须对**（`memblock` 不是 `mmemblock`）否则 skill 按模块找源码 / 相似 test_point 都会跑偏 |
| `target_test_point` | 补已有条目 | `"### P<id>. <title>"` |
| `case_name` | `run-only` / `fix-case` / 补 assert | 目标 case 名 |
| `failure_log` | `triage-only` | 失败日志路径 `.tmp/result_log/<platform>/<log>` |

**可选覆盖**（不写则用默认值）：

| 字段 | 默认 | 什么时候显式写 |
| --- | --- | --- |
| `platform` | `spike` | 要跑 `linknan` |
| `spec_profile` | profile registry 的 `default_profile`（查 `references/spec_profiles/index.json`）| 正式任务建议显式写；切项目时改 `references/spec_profiles/index.json` 的 `default_profile` |
| `task_mode` | 按自然语言推断 | 推断可能有歧义时显式声明：`new-case-only` / `supplement-existing-point` / `fix-case` / `run-only` / `preflight-only` / `triage-only` / `writeback-only` |
| `new_case_count` | `1` | 想同时新增多个 case（必须说明每个覆盖差异）|
| `target_policy` | `default-first` | `manual-ok` / `compile-only-ok` |
| `bug_hunt_focus` | 无 | bug hunt 时给方向先验，例 `"CMO / LRSC / fence"` |

**`spec_profile` 具体值**：当前项目默认是 profile registry 里的 `default_profile`；不写则用默认值，正式任务建议显式写。示例：

```text
spec_profile: nhv5_1_ap
```

**环境变量字段**（`HYPTEST_HOME` / `HYPTEST_SPIKE_BIN` / `HYPTEST_LINKNAN_HOME` / `HYPTEST_DIFFTEST_REF_SO` / `HYPTEST_TMPDIR`）只在当前进程看不到时补写；shell 已 export 就不用写。`HYPTEST_SKILL_HOME` 仅在手动运行本 skill 自带 `scripts/*.py` 时需要。详细口径见 `references/task_input_schema.md`。

### 两种执行档：快速版 vs 完整 pack

**什么是 pack**：一组把 workflow 各阶段（写前准备 / 编译运行 / 写后核对 / 最终证据卡）**聚合成标准 JSON + Markdown 报告**的脚本（`case_preflight_pack` / `case_gate_pack` / `case_postcheck_pack` / `make_case_submission_card` / `case_workflow_ledger`）。产物落在 `$HYPTEST_HOME/.hyptest_workflow_skill/reports/`，可审计、可复盘、可批量处理。

skill 有两档执行路径，默认走**快速版**。需要切到**完整 pack** 时在 prompt 里加一句即可。

**快速版（默认）**——约 2-3 分钟，单次新增 case 推荐：

- 预热 `repo_evidence_index` 缓存
- 直接跑 `find_similar_cases` + `check_case_uniqueness` + `compile_elf` + `get_result`
- lint / 失败分类 / 回填核对照跑（质量工具不省）
- **不跑** pack 聚合脚本，不生成标准 JSON/Markdown 报告
- 摘要直接写到对话里

普通个人开发 case、改 case、补 assert 都用这档，不需要在 prompt 里特别声明。

**完整 pack**——多 30-90 秒，产出标准证据卡，适合以下场景：

- 多人协作、要交标准证据卡片
- 复盘耗时（看每步花多久、返工信号）
- 连续多个 case 批量处理（`case_batch_gate_pack` 每条独立证据）
- 同一 case 多平台对比（`case_multi_platform_gate_pack`）
- 正式提交要 submission card

切到完整 pack 在 prompt 里加一句明示即可：

- `"跑完整 pack"` / `"输出 submission card"` / `"记录 timing 和 ledger"` / `"用 case_gate_pack"`

skill 会切到：`case_preflight_pack` → 写 case → `case_gate_pack` → `make_case_submission_card` →（可选）`case_workflow_ledger`。

pack 每个脚本的功能见 `references/resource_index.md` 的 Public Scripts 段。

### 反例（常见坑）

- **`target_module` 拼错**（`mmemblock` / `strorequeue`）→ skill 按模块找源码 / 相似 test_point 都跑偏，让你以为没 bug
- **只写"帮我补几个 case"**，不带 `test_point_file` / `task_mode` → skill 要停下来问（或随意推导错方向）
- **`new_case_count: 1-3` 却不说每个 case 的覆盖差异** → agent 容易写出相似 3 个，重复且浪费
- **把 SKILL.md 的"执行步骤 / 质量门禁"整段复制到 prompt 里** → 冗余，且容易和 SKILL.md 漂移
- **bug hunt 任务不给 `target_module`** → skill 没法聚焦到目标模块的源码/profile 分析，退化成无头苍蝇式 speculation
- **把大量审计证据写回 `test_point`**（Gate 结果 / 分层结论 / 编译统计）→ `test_point` 是意图描述不是审计日志；证据应放最终交付摘要或 pack 报告
- **要求"全量编译 / 全量跑"作为单 case 流程** → 显著拖慢，且单 case 任务本来不需要
- **task_mode=new-case-only 但 prompt 暗示"只是改一下"** → 模式判定摇摆；明确写目标"新增测试点和新 case"或改成 `supplement-existing-point`

## 常见场景速查

下表是**场景提醒**，不是硬判断。完整规则和 Source Priority 以 `SKILL.md` 为准。

| 场景 | 先查什么 | 初始处理 |
| --- | --- | --- |
| 新增普通架构 case | `references/spec_profiles/<spec_profile>.md` + 相似 case | 按 Gate 跑完后落位；Spike 跑通即 `default` |
| PMA/PBMT/MMIO/cache/TLB/CBO 等 profile-sensitive case | `$HYPTEST_SKILL_HOME/scripts/query_spec_profile.py` + profile 的 Spike gate | 若 `spike_gate_applicable=false`，走 nongate 路由并按环境落 `manual` / `compile-only` / `blocked`；不要先用 Spike/default gate 或改成 Spike-friendly baseline |
| 访问 MMIO/Device 区间 | profile 的 MMIO responder 表 | 先确认 responder；无 responder 或 Spike 不建模时走 manual/compile-only/blocked，不用普通 DRAM/cacheable 近似替代 |
| 只改回填或注册状态 | `test_register.c` + `$HYPTEST_SKILL_HOME/scripts/check_writeback_format.py --check-register` | 保证 `已实现 case` 状态与注册一致 |
| Spike/LinkNan 运行失败 | `references/build_run_debug.md` + `references/tiering_decision.md` | 先定位用例/assert/环境/model gap，再给 `reason_code` |
| 不确定 `reason_code` | `$HYPTEST_SKILL_HOME/scripts/suggest_reason_code.py --symptom "<现象>"` | 把建议当候选，最终仍以日志和 profile 证据为准 |

## 分层口径

| 分层 | 含义 | 注册状态 |
| --- | --- | --- |
| `default` | 编译通过、运行通过、规则一致、Spike gate 适用、证据完整 | `TEST_REGISTER(case_name);` 开启 |
| `manual` | 场景合理，但不适合常规 Spike gate，或需要人工/RTL 环境确认 | 通常注释注册 |
| `compile-only` | 当前只保证可编译，运行 gate 不成立或阶段性不运行 | 通常注释注册 |
| `blocked` | 编译、运行、规则、证据或注册一致性存在阻塞 | 不作为完成落位 |

`default-first` 的意思是普通架构场景优先争取 default，不是无条件放 default。`spike_gate_applicable=false` 是 gate/runner 路由属性，不是测试价值降级信号；manual/nongate 场景不能只凭 official Spike 结果作为 default gate，也不能被更容易跑 Spike 的近似场景替代。若 nongate 场景当前只有编译条件、缺少对应 LinkNan/RTL/special-run runner，则先落 `compile-only`；这仍表示场景应保留，只是本轮运行证据还没闭环。

**非 default 都会生成 submission card**：`manual` / `compile-only` / `blocked` 都需要机器可读交付卡，记录 reason_code、注册状态和证据摘要；`compile-only` 默认只说明 Gate D=`N/A` 与不运行原因，不写 Manual_Reference。

**`manual` / `blocked` 会按 4 档 verdict 路由到 Manual_Reference**：如果分层落到 `manual` 或 `blocked`，skill 先跑 `$HYPTEST_SKILL_HOME/scripts/check_manual_reference_topic.py` 判 verdict：`profile_covered`（profile §5 已收录 → 引用不新增）/ `memory_confirmed`（memory `confirmed` 已覆盖 → 复用不新增）/ `manual_reference_open`（已有未解决 MR 条目 → 在其下补"本轮也碰到"一行）/ `new_entry_needed`（auto-append 新 `#### <id>.（**自动生成，待人工确认**）`，含涉及文件、涉及用例、怀疑点源码引用、本轮 Spike 观察和 3 条待人工确认问题）。人工 audit 结论会同步回 memory（`--status confirmed`，从 Manual_Reference 迁入）和 Manual_Reference 条目（加 `> 已解决` 行）；判"作废 / 过时"则直接删 MR 整条 + 删同 case memory 行。

## 目标仓库和环境

日常 prompt 不需要写完整环境清单：当前执行环境已经能读到的变量可以省略；读不到、但本轮必需的变量才写进 prompt。对外统一使用 `HYPTEST_HOME` 和 `HYPTEST_*`，不要写个人绝对路径。

常见必需组合：

- Spike 编译/运行 gate：`HYPTEST_HOME` + `HYPTEST_SPIKE_BIN`
- LinkNan / difftest gate：`HYPTEST_HOME` + `HYPTEST_LINKNAN_HOME` + `HYPTEST_DIFFTEST_REF_SO`
- Nanhu 源码：从 `HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main` 推导，无独立环境变量

常见变量含义：

| 变量 | 含义 | 什么时候需要 |
| --- | --- | --- |
| `HYPTEST_HOME` | hyptest 主仓库路径 | 编译、运行、回填、注册核对 |
| `HYPTEST_SPIKE_BIN` | official/community Spike 的 `spike` bin 路径 | Spike gate |
| `HYPTEST_LINKNAN_HOME` | LinkNan 仓库路径 | LinkNan/difftest gate、读取 Nanhu RTL 源码 |
| `HYPTEST_DIFFTEST_REF_SO` | 项目维护的 difftest Spike `.so` 路径 | LinkNan/difftest gate |
| `HYPTEST_TMPDIR` | 临时目录 | 需要控制临时产物位置时 |
| `HYPTEST_SKILL_HOME` | hyptest-workflow skill 目录 | 手动运行本 skill 自带 `scripts/*.py` 时 |

完整字段说明和默认值策略见 `references/task_input_schema.md`。平台名只使用 `spike` 或 `linknan`。

需要检查当前环境时：

```bash
python3 $HYPTEST_SKILL_HOME/scripts/check_env.py --repo-root $HYPTEST_HOME --platform all --explain
```

## 入口文件

你最可能直接看的 5 份：

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | Agent 执行入口（触发、硬规则、Workflow、Bug Hunt Evidence、Output Defaults）|
| `README.md` | 本文件——用法、字段表、场景提醒 |
| `references/task_input_schema.md` | 任务输入字段、task_mode、preflight 完整 schema |
| `references/writing_cases.md` | case 编写、断言、回填格式 |
| `references/cause_code_catalog.md` | `excpt.cause` 断言常量速查表 |

其余 references / scripts / assets / evals 的完整清单见 `references/resource_index.md`。

## 规则和输出指向 SKILL.md

- **硬规则**：真值在 `SKILL.md` 的 `Non-Negotiables`；本文件不维护副本避免漂移
- **交付摘要必含字段**：见 `SKILL.md` 的 `Output Defaults`（默认中文 + 结论具体；想要额外字段/不同格式 prompt 里加一句即可）
- **Source Priority / Workflow / Bug Hunt Evidence**：触发 skill 时以 `SKILL.md` 为准

## 自检

修改本 skill 后运行：

```bash
python3 $HYPTEST_SKILL_HOME/scripts/check_readme_commands.py
python3 $HYPTEST_SKILL_HOME/scripts/check_docs_links.py
python3 $HYPTEST_SKILL_HOME/scripts/check_skill_consistency.py
python3 $HYPTEST_SKILL_HOME/scripts/check_resource_index.py
python3 $HYPTEST_SKILL_HOME/scripts/update_resource_index.py --check
```

完整快速自检：

```bash
python3 $HYPTEST_SKILL_HOME/scripts/self_check.py --quick --spec-profile <spec_profile>
```
