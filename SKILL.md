---
name: hyptest-workflow
description: hyptest 测试点到用例落地 skill。**必须触发**：新增/改 ai_test_cases 或 manual_test_cases、新增/回填 test_point/**/*.md `### PnX`、更新 test_register.c、跨 test_point 排重或 case 去重、按模块找 suspected bug 并写新测试点、default/manual/compile-only/blocked 初判分层、test_point↔断言映射核对、涉及 hyptest harness (TEST_START/TEST_END/TEST_ASSERT/TEST_SETUP_EXCEPT/TEST_REGISTER) 的 case 编写。spec_profile 路由到 references/spec_profiles/<name>.md；PMA/PBMT/MMIO/Device/no-response case 修改或分层必须做 profile guard。**不触发**：只看 Spike/LinkNan 失败日志不落新 case、FSDB/stuck/50000 cycles/difftest mismatch/suspected RTL bug 深挖 → hyptest-failure-triage；波形协议分析 → waveform-debug；纯 RISC-V 知识问答/Spike 工具链参数/解析 ELF/通用代码 review。
---

# HYPTEST Workflow

Agent 执行入口。触发后按以下优先级执行：

1. **Workflow**（下文）是默认 16 步流程；每步都要遵守 **Non-Negotiables** 的 4 组硬规则
2. 规则冲突按 **Source Priority** 裁决
3. bug hunt 场景在 Workflow 步骤 3 的"选点"环节用 **Bug Hunt Evidence** 的三类资料替代普通相似检索；其它步骤（唯一性 / profile 标记 / 写 case / 编译运行 / 回填）仍按 Workflow 正常执行
4. 输出必满足 **Output Defaults**

用户面向的用法/字段表/触发范例在 `README.md`——agent 不用看 README，只管按本文件执行。

## Cross-Skill Routing

`hyptest-workflow` 是 case/workflow/profile/runner owner，不是失败闭环 owner，也不是波形分析 owner。跨 skill 时按下面边界走，避免 workflow 看到失败或 FSDB 后直接越权下结论。

继续留在 `hyptest-workflow`：

- 新增或修改 `ai_test_cases/*.c` / `manual_test_cases/**/*.c`。
- 调整 `test_register.c`、编译/运行 case、生成 gate/postcheck/submission 证据。
- 做 profile guard、Spike gate applicability、`default` / `manual` / `compile-only` / `blocked` 初判。
- 回填 `test_point/**/*.md`、检查 case 唯一性、相似检索和 test_point↔断言映射。

转 `hyptest-failure-triage`：

- 只看失败日志、批跑失败或失败列表，不新增/修改 case。
- selfcheck `FAILED`、`HIT GOOD TRAP` 但 `FAILED`、stuck/timeout、`50000 cycles no commit`、difftest mismatch、suspected RTL bug。
- 已有 case 的 `FAILED`/selfcheck 修复必须先由 failure-triage 归因；workflow 只在 triage 判定需要改 case/注册/重跑时执行编辑和 runner 动作，随后把证据交回 triage 收口。
- 失败列表清理、是否可删除已修复项、是否要写最终中文 `report.md`。
- hyptest 失败需要波形作为证据时，先生成 workflow-to-triage handoff，交给 failure-triage 负责是否调用 waveform-debug 和最终收口。

只有在**纯波形分析**时才直接转 `waveform-debug`：用户已经给出 waveform 文件、RTL/source、top module、debug target，且目标只是 first-bad-cycle、握手/协议、X-state 或信号事实提取；不涉及 hyptest 分层、失败列表清理、case 修复闭环或 suspected RTL bug 最终归因。

默认路径：

```text
hyptest 失败 + waveform 需求:
  hyptest-workflow 生成 triage handoff
  -> hyptest-failure-triage 判断是否需要 waveform-debug
  -> waveform-debug 产出 report.md（如需）
  -> hyptest-failure-triage 写最终中文 report.md / cleanup 决策
```

## Source Priority

冲突时按以下顺序裁决：

1. `references/spec_profiles/<spec_profile>.md` + `references/spec_and_model_limits.md`（**当前项目规格实现 + Spike 建模边界 + Nanhu 实现约束**——项目真值）
2. `.hyptest_workflow_skill/memory/events.jsonl` 中 `status=confirmed` 的条目（人工 audit 迁入的复用线索）
3. `references/quality_gate.md` + `references/tiering_decision.md` + `references/reason_code_catalog.md` + `references/submission_card.md`（分层/Gate/reason_code/交付口径）
4. `references/writing_cases.md` + `references/framework_usage_pitfalls.md` + `references/build_run_debug.md`（写 case / 环境细节）
5. `references/repo_layout.md`
6. `test_point/CRITICAL_ISSUES_LOG.md`

补充：

- 顺序问题一律以日志和最小复现实验为准，不以视觉顺序经验做硬判断。
- 存量 case 是学习样本，不高于项目规则。
- memory 中 `status=unconfirmed` 的条目仅作辅助线索，不参与冲突裁决。

## Data Sources and Roles

三个可读写文件，各司其职、各有生命周期——**不要混用**：

| 文件 | 定位 | 谁写 | 谁读 | 生命周期 |
|---|---|---|---|---|
| `references/spec_profiles/<profile>.md` | **项目真值**：当前架构 Nanhu 实现了 spec 什么、Spike 建模了 spec 什么、Nanhu 未实现 spec 什么；PMA/PBMT/MMIO 表 | 人工长期维护；audit 后迁入 | agent 分层/选点**必读**（Source Priority §1） | 随项目 + Spike 版本演化 |
| `.hyptest_workflow_skill/memory/events.jsonl` | **可直接复用的事实**：人工确认过的结论 + agent 低风险自动沉淀；原信息不再成立时由人工直接删对应行（无 obsolete 占位） | `workflow_memory.py append`（3 门槛 + status 分档）| agent bug hunt / fix-case / 相似检索查询；`status=confirmed` 进 Source Priority §2，`status=unconfirmed` 仅作辅助 | 长期累积，带 status（unconfirmed / confirmed） |
| `test_point/Manual_Reference.md` | **面向人的收件箱**：agent 跑出来的新 manual/blocked 观察、待人工判决的问题；所有"人工确认后的结论"会被迁出到 profile 或 memory，本文件只承载待办 | skill step 16 auto-append；人工 audit 后迁出 + `> 已解决` 或直接删条目 | 人工 audit；agent 仅在 step 16 `check_manual_reference_topic.py` 查重时读一次 | 短暂——人工审完就流出去（进 profile / memory / 删除） |

### 三文件之间的流转

```
agent 写 case 遇到新 manual/blocked
  → step 16 判断（按顺序）：
    1. profile §5 / reason_code_catalog 已覆盖？     → 是 → 不新增 MR，摘要引用 profile
    2. memory 有 confirmed 条目覆盖本主题？          → 是 → 不新增 MR，复用 memory 条目
    3. Manual_Reference 有未解决同主题条目？         → 是 → 不新增 MR，在已有条目下补"本轮也碰到"一行
    4. 以上都否                                       → auto-append 新的 `#### <id>.（待人工确认）`
  → 同时 step 15 按 3 门槛 append memory（status=unconfirmed）

  [人工 audit Manual_Reference 条目]
  ├─ 判为"规则真值" → 内容迁进 spec_profiles/<profile>.md，MR 该条标 `> 已解决：已进 profile §X`
  ├─ 判为"复用线索" → append memory（status=confirmed），MR 标 `> 已解决：已进 memory`
  └─ 判为"作废 / 过时" → **直接从 Manual_Reference 删除该条目**；相关 memory 行也一并删除

agent 后续执行:
  profile 做分层决策时读
  memory 做相似检索 commented 判据 / bug hunt query 时读（优先 confirmed，unconfirmed 作辅助）
  Manual_Reference 检查是否有本 case 的待确认条目（强信号）
```

判断 1-3 可用脚本辅助：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_manual_reference_topic.py \
  --repo-root $HYPTEST_HOME \
  --case <case_name> --module <m> \
  --topic <kw1> --topic <kw2> \
  --spec-profile <profile>
```

返回 `verdict` ∈ `{profile_covered, memory_confirmed, manual_reference_open, new_entry_needed}` 以及 `next_action`。

### memory status 分档

memory 只存**可以直接参考的事实**，不存"待确认问题"（那属于 Manual_Reference.md）、也不存"过时占位"（过时记录由人工直接编辑 `events.jsonl` 删除对应行）。2 档 status：

| status | 含义 | 读取优先级 |
|---|---|---|
| `unconfirmed` | agent 自动沉淀的**未经人工确认的事实观察**（3 门槛过，可作辅助线索）；`workflow_memory.py append` 的默认值 | 次级参考 |
| `confirmed` | **人工确认过的经验**（从 Manual_Reference 迁入） | **首选** |

过时处理：`events.jsonl` 是 append-only 但手工可编辑；若某条记录因 Spike/RTL 升级不再成立，**人工直接打开文件删除对应行**（Manual_Reference.md 相关条目同时删除）。memory 没有 `obsolete` 占位——保持"memory 里每条都是当前成立的事实"的单一真值。

详细维护 CLI、Manual_Reference → memory 迁入操作见 `references/workflow_state.md`。

## Non-Negotiables

4 组硬规则，按优先级：代码硬约束（违反 = case 无效）> 环境路径 / runner（缺失 = gate 不可信）> 工作流边界（防误判漏去重）> 输出默认值（交付摘要形状）。

### 1. 代码硬约束（违反 = case 无效）

- **单个 case 函数只保留一个 `TEST_END(...)`**。Why: `TEST_END` 走固定收尾路径（回 M 态 + reset + 记录结果），多次触发会撞 linker 重复标签或多次收尾导致状态错乱。提前退出用 `return false;`，不要写第二个 `TEST_END`。
- **断言 `excpt.triggered/cause/tval` 前必须调用 `TEST_SETUP_EXCEPT()`**。Why: `excpt.*` 是全局状态，上个 case 或上段代码的异常会污染本次判定。`TEST_SETUP_EXCEPT()` 显式初始化异常状态，确保读到的是本步骤的结果。`reset_state()` 只重置 CSR，不等价于异常初始化。
- **注册统一放 `test_register.c`，不在 case 源文件末尾注册**。Why: `.test_table` 由链接器收集 + `get_result.py` 扫 `test_register.c` 决定跑哪些 case。散落注册让"这个 case 为什么没跑"极难定位；单真值来源才能保证回归一致。
- **AI/批量生成 case 放 `ai_test_cases/*.c`；人工维护 case 按模块放 `manual_test_cases/<module>/`**。Why: 两类 case 的质量口径、回归策略、review 方式不同。Makefile 按目录收集，混放会让 commit 审查 / ownership 追踪失效。
- **遇到历史大文件或用户明确不想继续堆叠时，必须新建主题明确的 case 文件**。Why: 单文件过大会让 merge conflict 变多、相似检索召回粒度变粗、PR review 成本飙升。新文件名应点出子主题（例如 `*_memblock_followup_cases.c`）。

### 2. 环境路径 / runner 要求（缺失 = gate 不可信，先停 gate）

- **本轮需要的 `HYPTEST_*` 变量缺失时停 gate，不 fallback 到个人路径或 PATH**。Why: 用 PATH 里的 `spike` 可能跑到 LinkNan 定制 difftest Spike 而不是社区版，得到"看起来过了其实不是 architecture gate"的假 default；fallback 到别人绝对路径也会让 CI 和本地行为分叉。必要组合：Spike gate = `HYPTEST_HOME` + `HYPTEST_SPIKE_BIN`；LinkNan gate = `HYPTEST_HOME` + `HYPTEST_LINKNAN_HOME` + `HYPTEST_DIFFTEST_REF_SO`；Nanhu 源码从 `HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main` 推导；详细字段见 `references/task_input_schema.md`。
- **runner 角色不可混用**：`HYPTEST_SPIKE_BIN` 只用于社区版/上游 Spike 的 default gate；LinkNan/difftest 走 `HYPTEST_DIFFTEST_REF_SO`，不要把定制 difftest Spike 当作 `HYPTEST_SPIKE_BIN`。Why: 定制 difftest Spike 为了和 RTL 对齐会刻意复制 RTL quirk，用它当 gate 等于"把 RTL bug 当成规范"——失去架构 gate 意义。两种 runner 职责严格分开才能形成有效交叉验证。
- **prompt 显式给的运行环境字段**（`HYPTEST_SPIKE_BIN` / `HYPTEST_LINKNAN_HOME` / `HYPTEST_DIFFTEST_REF_SO` / `HYPTEST_CROSS_COMPILE` / `HYPTEST_TMPDIR`）**必须映射成 `--env KEY=VALUE`** 传给支持 `--env` 的脚本；`$HYPTEST_WORKFLOW_SKILL_HOME` 由调用者 export，skill 文档不写死个人绝对路径。Why: 脚本子进程不继承 shell 别名和 prompt 字段，不显式传会拿到 OS 默认或旧值；skill 里写死绝对路径会让其他人 clone 后直接报错。
- **路径 / runner 分层必须显式**：skill 自带工具用 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/<tool>.py`；hyptest repo runner 用 `$HYPTEST_HOME/<tool>.py`，例如 `$HYPTEST_HOME/compile_elf.py`、`$HYPTEST_HOME/get_result.py`；`HYPTEST_SPIKE_BIN` 只用于 official/community Spike gate；`HYPTEST_DIFFTEST_REF_SO` 只用于 LinkNan/difftest gate。不要用裸相对路径调用 skill 工具，也不要混用 runner。
- 环境 troubleshooting（`~/.bashrc` 非交互 shell 提前 return、`$VAR` 展开失败、submodule 未初始化、`case $-` 保护位置等）见 `references/build_run_debug.md` §7.2，不在 Non-Negotiables 展开。

### 3. 工作流边界（防误判、漏去重、错误扩点）

- **`test_point_file` 是容器，`### PnX` 才是独立测试点**。去重、扩写、复用、完成判定都按条目级进行；不能把整个文件当单个测试点，也不能因为文件之前改过就停止处理新条目或误把旧条目当新增结果。Why: `test_point_file` 里可能有十几个 `### PnX`，"文件改过"≠"每个条目都处理过"；把旧条目包装成新增是**虚假交付**。
- **两种任务模式**：
  - **新增测试点模式**（`task_mode=new-case-only` 或未指定条目）：默认 `coverage_scope=repo` 做全仓 `test_point/**/*.md` 覆盖检查，必须新增新的 `### PnX` 条目和新的 `ai_*` case。新条目编号沿当前文件前缀继续递增（如 `*_points_7.md` 继续补 `P7D/P7E`）。
  - **补已有测试点模式**（`task_mode=supplement-existing-point` 或用户明确指定 `### PnX`）：默认 `coverage_scope=file` 围绕该条目/文件做局部测试点检查，优先在旧条目下补 case，不强行新增新条目。
- **写新 case 或判断 Spike 结果前必须先确定规格/平台口径 `spec_profile`**（未指定则用 profile registry 中的 `default_profile`），再看 `references/spec_and_model_limits.md` 与 `references/spec_profiles/<spec_profile>.md`，**标记**规格来源、平台模型边界、`spike_gate_applicable` 作为初始分层候选（最终分层按 Gate 证据落位，见 `Source Priority`）。Why: 同一个断言在不同 profile 下的结论可能相反（例如 PMA=IO 非对齐在某些 profile 下走 AF，通用 RISC-V 走 AM）。不定口径就判 Spike 结果会把"profile 限制"误认为"RTL bug"。
- **PMA/PBMT/MMIO/Device profile guard**：新增、修改、修复或分层这类 case 时，先从当前 `spec_profile` matrix 记录 `spec_allowed` / `responder_required` / `spike_gate_applicable`，再用 LinkNan 源码/log/波形记录 `testbench_responder_confirmed`。**禁止**用无返回反推规格不允许，也禁止用规格允许反推 testbench 一定有 response。
- **Nanhu 未实现的 corner 直接不编 case**：若目标 corner 落在当前 profile 的 Nanhu 实现约束之外（例如 `spec_profiles/<profile>.md` §5 "Nanhu NHV5.1AP Debug trigger 实现约束"段、或 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --nongate-summary --match-module <m> --json` 里 `classification=nanhu_not_impl` 的类别——data trigger、3+ 层 chain、本版本未实现的 debug 特性等），**默认禁止直接编写 case**——应先回退到 Nanhu 已实现的等价角度，或停下来请用户确认。**唯一例外**：用户**显式确认**作为"未来 Nanhu 支持后的回归占位"（极罕见）→ 可以标 `D-MANUAL-NANHU-NOT-IMPL`，`$HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_writeback_format.py --check-reason-code` 会抛 `reason_code_nanhu_not_impl` warning 让 reviewer 复核；没有这个显式确认就写 = 违反本规则。Why: 两类 Spike 边界语义截然不同——(a) Nanhu **实现**了 spec、Spike 有 gap（`D-MANUAL-SPIKE-GAP`/`D-MANUAL-NONGATE`）→ **照常编 case 但不以 Spike 为 gate**；(b) Nanhu **未实现**该 spec 场景 → 默认**不该写**，产出的是永远跑不动的僵尸 case，也污染覆盖统计。
- **写新 case 前先检索 2~5 个相似存量 case**；模板只作骨架提醒，不替代存量 case 学习。Why: 模板只给形状，存量 case 含本 repo 的**特权态切换顺序、页表/PMP 处理习惯、断言文案风格**。跳过学习容易写出和仓库风格脱节的 case，review 阶段被打回。
- **写新 case 前必须同时做 repo 级 case 相似检索 + 精确唯一性检索**；"相似检索未命中"和"函数名唯一"不是同一件事，两者都要留证据。命名确定后优先用 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_uniqueness.py --expect absent` 走缓存索引快路径；缓存由 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/repo_evidence_index.py` 预热（见 Workflow 步骤 1），**没预热时脚本会 fallback 到全仓 rg，等于违反此条**。写完后的 postcheck 只作复核，不能替代写前唯一性拦截。`case` 去重始终是 repo 级；`$HYPTEST_WORKFLOW_SKILL_HOME/scripts/find_similar_cases.py` 始终搜索全仓 `ai_test_cases/*.c` 与 `manual_test_cases/**/*.c`。详见 `references/coverage_and_dedupe.md`。
- **新增测试点前必须先做测试点覆盖检查**；默认按全仓 `test_point/**/*.md` 扫描，不能只看当前文件就声称"全仓未覆盖"。Why: test_point 按模块分文件但**同一怀疑点可能散落在多个文件**。只看当前文件就声称"新点"会造成跨文件重复。
- **若扫描后未发现新的高价值测试点，必须明确说明"未发现新的测试点 / 未新增 case"**，不能把旧条目或旧 case 再次作为新增结果交付。Why: LLM 为了"完成任务"有凑数倾向。硬规则强制承认"这次没找到"，避免把旧成果包装成本轮新增污染历史。
- **case 独立性**：新 case 必须能单跑通过（不依赖前面 case 的 CSR/TLB/cache/reservation 残留）。prepare 段应显式清理本 case 会用到的状态（相关 CSR 位、`sfence_vma`、`TEST_SETUP_EXCEPT()` 等）。Why: 批跑顺序会变（新增/移除 case 影响 `test_register.c` 注册位置；全局 `.data`/`.bss` 段 layout 也会变）。默认只要求单跑通过 + prepare 段显式清理状态即可落 `default`；怀疑有顺序依赖时可手工跑一次窄范围 `$HYPTEST_HOME/get_result.py --platform <plat> --range <本 case 前后几条>` 补对比证据，但不作为硬门禁。

### 4. 输出默认值（禁止项；正面清单见 `Output Defaults`）

- **`test_point` 默认只回填正文和 `已实现 case`**；默认只写 `case_name`，必要时才补短状态；**禁止追加 `[新增 case]`、`[质量门禁结果]`、`[分层结论]`、`[编译/运行统计]` 等审计式块**。Why: `test_point` 是测试意图描述，不是审计日志。加运行证据和分层块会让 test_point 膨胀难读，且审计证据在别处（gate pack / submission card / 最终交付摘要）已有。
- **禁止默认输出 `exclude_check`**。Why: 默认输出会让交付摘要携带无意义字段。
- **禁止默认输出全量 Gate A-H**；只有非 pass Gate 或用户明确要求时，才在最终交付摘要里输出 `[质量门禁结果]`。Why: 全 pass 时列八条"Gate X: pass"纯噪声；只在有问题时列出来反而让工程师一眼看到阻塞点。
- **禁止为 `default` case 默认单独输出 `[分层结论]`**；只有 `manual` / `compile-only` / `blocked`，或用户明确要求时，才在最终交付摘要里输出 `decision_prelim` / `decision_final` / `reason_code`。Why: `default` 是"一切正常"的默认分层，需要解释的是**偏离 default 的情况**；给 default case 加分层块是反向信息量。

## Workflow

默认走"**预热 + 轻量直通**"：`repo_evidence_index` 预热 → `find_similar_cases` → `check_case_uniqueness` → 写 case → `check_case_lint` → 调整注册 → `compile_elf` → `get_result` →（失败时）`classify_failure_log` → 回填 → `check_writeback_format --check-register`。**不默认跑 pack 聚合工具**（`case_preflight_pack` / `case_gate_pack` / `case_postcheck_pack` / `case_workflow_ledger`）；只有用户明确要求"跑完整 pack"、"复盘耗时"时才走完整 pipeline。质量工具（lint / 失败分类 / 注册一致性）在轻量路径仍必须保留。**例外**：`$HYPTEST_WORKFLOW_SKILL_HOME/scripts/make_case_submission_card.py` 在 **非 default 分层**（manual / compile-only / blocked）时**必须跑**，作为 reason_code 和交付摘要的机器可读证据；default 分层不跑。`Manual_Reference` 只承载需要人工判决/复核的 `manual` / `blocked` 观察，不承载普通 `compile-only` 阶段性结论。

1. **锁定输入 + 按需预热**：确认 `HYPTEST_HOME`、`test_point_file`、平台、case 名、目标分层和 `spec_profile`（未指定则用 profile registry 中的 `default_profile`）。**`check_env.py` 与 repo evidence 预热分开判断**，不要把“要运行”和“要检索覆盖”绑成同一个门：
   - `check_env.py`：只要本轮会编译/运行，或需要读取 LinkNan/Nanhu source，就必须按目标平台跑。`run-only` 必须跑；`new-case-only` / `supplement-existing-point` / `fix-case` 若会 compile/run 也必须跑；纯日志 `triage-only`、纯回填 `writeback-only` 可跳过。
   - `repo_evidence_index.py`：只要本轮要做覆盖检查、相似 case、函数名唯一性或 bug hunt，就必须预热。`new-case-only` / `supplement-existing-point` / bug hunt / 覆盖摸底型 `preflight-only` 必须跑；纯 `run-only`、纯日志 `triage-only`、纯回填 `writeback-only` 可跳过。
   ```bash
   python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_env.py --repo-root $HYPTEST_HOME --platform <plat>     # 12h TTL 缓存 + 路径 re-stat；--invalidate-cache 强刷
   python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/repo_evidence_index.py --repo-root $HYPTEST_HOME --json > /dev/null   # 增量重建：cases/test_points/register 段独立 digest
   ```
   输入字段多或存在旧平台名/不确定模式时用 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/validate_task_request.py` 做 preflight。
2. **识别任务模式**：新增测试点模式 vs 补已有测试点模式（见 Non-Negotiables §3 第 1-2 条）。bug hunt 任务**开工前必须**跑一次 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_target_module.py --module <target_module>` 验证模块名——exact / snake↔Camel / edit-distance≤2 fuzzy 三层匹配；fuzzy 候选必须让用户确认，不能自动替换。
3. **覆盖检查 + 相似 + 唯一性**：按 `references/coverage_and_dedupe.md` 做测试点覆盖检查、repo 级 case 相似检索、精确唯一性检索（`$HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_uniqueness.py --expect absent`）。
   - **相似检索前先做 query 提炼**（无 tool call）：把"想找什么"拆成 3-5 条具体 term（目标指令/结构、硬件单元、特殊 condition、profile 类别、预期断言类型），用提炼后的 term 作 `--query` 参数。
   - `--limit` 按任务分档：补已有 `### PnX` 且只加 assert / 小改 `--limit 2-3`；补已有 `### PnX` 新增 case `--limit 3-4`；新增 `### PnX` 或跨模块 `--limit 5`；bug hunt / 跨模块扩点 `--limit 5-8`。
   - **读 top 结果时先看 `note` 字段再决定 Read**：`matched terms` 判真命中还是 term alias 溢出；`observability density` / `contains explicit cause/tval checking` 判质量；`calls related helpers` 判 helper 复用。
   - **`register_status=commented` 按来源分档处理**：commented 有多种原因（正式流程标 manual / 用户手动调试禁用 / WIP 暂停等），不能一刀切当硬信号。**判据是 Manual_Reference.md 有对应条目 _或_ memory/events.jsonl 有对应历史**——相似检索 render 会在 note 里标出分档：
     - `commented` 且 **Manual_Reference.md 或 memory/events.jsonl 命中**：**建议深入**——这是正式流程判过 / agent 已沉淀经验的 Spike 边界，**必须**先 Read 该 case 源文件 + 命中来源的条目再选同类角度
     - `commented` 但 Manual_Reference.md 无对应条目：**当噪音处理**——大概率是手动调试 / WIP 注释，不作为硬信号，但写怀疑点时仍应 Read 那个 case 看场景（作为相似检索的普通参考）
4. **profile 标记**（`new-case-only` / `supplement-existing-point` / bug hunt / `fix-case` 才需要；`run-only` / `writeback-only` / `preflight-only` 跳过；`triage-only` 只有在 PMA/PBMT/MMIO/no-response 判断会影响修改或分层时执行）：读 `references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md`。标记 `spike_gate_applicable`；PMA/PBMT/MMIO guard 还要写出 `spec_allowed`、`responder_required`、`testbench_responder_confirmed` 和证据路径。
5. **写前检查**（无 tool call，纯文本，所有写 case 类任务必跑）：在动笔前用文字回答——
   1. 本 corner 是否落在 **Nanhu 未实现** 范围内（data trigger / 3+ 层 chain / `classification=nanhu_not_impl` 等）？若 **是** → **停下回退**到 Nanhu 已实现的等价角度或请用户确认，**不要动笔**（Non-Negotiable §3 第 4 条）。若 **否** → 继续第 2 问。
   2. 本 case 的 `spike_gate_applicable` 是 true 还是 false？依据是 profile §5 / `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --nongate-summary` 的哪条？
   3. 若涉及 PMA/PBMT/MMIO/no-response：`spec_allowed` 与 `testbench_responder_confirmed` 分别是什么，证据路径是什么？
   4. 步骤 3 相似检索 top 中有 `register_status=commented` **且（Manual_Reference.md 有对应条目 _或_ memory/events.jsonl 有对应历史）**的同主题 case 吗？若有，已读了那 case + 命中来源的条目吗？本次为什么仍要选这个角度？（两处都没命中的 commented 视作普通 case，无需触发本问）

   写前检查答完走**分路**：
   - 第 1 问 "否" + 第 2 问 "**true**"（Spike 可 gate）→ **default-first 路径**：步骤 6 写 case → 步骤 7 预编译 lint → 步骤 8 注册**开启** `TEST_REGISTER(...);` → 步骤 9 compile → 步骤 10 跑 Spike → 步骤 11 失败分类（如需）→ 步骤 12-14 正常回填
   - 第 1 问 "否" + 第 2 问 "**false**"（Spike 不可 gate，但 case 照编）→ **nongate 路由**：步骤 6 写 case → 步骤 7 预编译 lint → 步骤 8 注册**直接注释** `// TEST_REGISTER(...);` → 步骤 9 compile 用 `--include-commented` → 步骤 10 **可选跑 Spike 看行为但不以结果翻 default**（Spike PASS 也不翻 default；跑出 FAILED 才进步骤 11 归因）→ 步骤 14 按证据落 `manual` / `compile-only` / `blocked` 并填写对应 `reason_code:` → 步骤 16 跑 submission card；若需要 LinkNan/no-diff、difftest、RTL-only 或 waveform 证据闭环，不在 workflow 内直接归因，生成 handoff 交给 failure-triage 指定 `runner_mode=linknan-no-diff|linknan-difftest`，workflow 只执行被指定的 compile/run/edit 动作；若最终分层是 `manual` / `blocked`，再按 4 档 verdict 处理 Manual_Reference。

   写前检查答不出 + 答案对不上证据 → 回补步骤 3-4 证据，**不要直接下笔**。这一步成本是几行文字，省的是错走 default-first 后再回退的 ~60-90s compile/run。
6. **写或改 case**：AI/批量生成放 `ai_test_cases/*.c`；人工维护放 `manual_test_cases/<module>/`；结构和断言以 `references/writing_cases.md` 为准。
7. **预编译 lint**（`new-case-only` / `supplement-existing-point` / `fix-case` 改 case 体后必跑；`run-only` / `writeback-only` 跳过）：
   ```bash
   python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_lint.py --repo-root $HYPTEST_HOME --file <new_case_file> --strict-case-end
   ```
   pre-compile lint 拦截 `TEST_END` 多写 / `TEST_SETUP_EXCEPT()` 漏调 / 多余 register 等结构错；命中 error 立即修，**不要先 compile**——一次 compile 在 NFS 上 ~30-60s，预编译 lint 只 1-2s。
8. **调整 `test_register.c`** 注册状态，**按步骤 5 分路**：default-first 路径**开启**注册 `TEST_REGISTER(...);`；nongate 路由**直接注释** `// TEST_REGISTER(...);`。
9. **单 case 编译**：default-first 用 `python3 $HYPTEST_HOME/compile_elf.py --plat spike --name <case_name>`；nongate 路由用 `python3 $HYPTEST_HOME/compile_elf.py --plat spike --name <case_name> --include-commented`（扫注释注册行）。
10. **单 case 运行**：
   - default-first：**必须**跑 `python3 $HYPTEST_HOME/get_result.py --platform spike --case <case_name>`；结果决定分层（PASSED → `default`；FAILED / untested → 步骤 11 归因）
   - nongate 路由：**可选**跑 Spike——想拿观察证据就跑，但结果**不翻 default**；最终仍按当前 runner/oracle 条件落 `manual` / `compile-only` / `blocked`
   - `compile-only` 分层：Gate D = `N/A`，明确写不运行原因
   运行前确认平台环境变量在当前进程可见。`compile-only` 允许 Gate D=`N/A`，但必须写明不运行原因。
11. **失败分类（强制）**：运行结果出现 `FAILED` / `untested exception` / `timeout` 时**必须**跑：
   ```bash
   python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/classify_failure_log.py --log-file <log> --spec-profile <spec_profile> --json
   ```
   并把 `scenario` / `error_points` / `reason_code_candidates` 写进交付摘要——分层归因必须以 classifier 输出为依据，**禁止凭旁证或感觉直接归 manual / blocked**。跳过此步等同于 `D-BLOCK-EVIDENCE`，不能交付非 default 分层。运行成功（`PASSED` 单独出现）的 case 跳过此步。
12. **test_point → case 映射表自查**：运行通过后，对照 `test_point` 正文逐条列出每个要求落在 case 哪一行断言。发现漏项立即补；发现偏移立即改。详见 `references/writing_cases.md` §14.1。
13. **回填 `test_point`**：默认轻量回填（只写 `case_name` + 必要短状态；不追加审计块）。详细模板和复用口径见 `references/writing_cases.md`。
14. **回填核对（含 `reason_code` 强制查表）**：
   ```bash
   python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_writeback_format.py \
     --repo-root $HYPTEST_HOME \
     --file <test_point_file> \
     --check-register \
     --check-reason-code
   ```
   `--check-reason-code` 校验非 default 状态的 `已实现 case` 行**必须**带 `reason_code:` 注释，且 code 必须在 `assets/reason_codes.json` 枚举里（当前 15 个——1 个 default + 5 个 manual + 2 个 compile-only + 7 个 blocked；见 §reason_code Catalog 或 `references/reason_code_catalog.md`）。**禁止编造** `manual.<...>` / 自由式 `D-MANUAL-<自造名>` 这类 code；catalog 不够用 → 用 `OTHER-PROPOSE:<一句话>` 占位（提示 skill 维护者扩 catalog），同时摘要里醒目标"⚠️ 待 catalog 扩展"。
15. **memory append 自问**（仅 bug hunt / 新增测试点 / `fix-case` 发现工具坑 / 非预期运行结果等场景）：按 `Workflow Memory` 段的 3 门槛处理。其它任务类型跳过。
16. **非 default 交付卡 + Manual_Reference 写回**：分层落到 `manual` / `compile-only` / `blocked` 时，必须跑 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/make_case_submission_card.py` 生成机器可读交付卡，作为 reason_code 和最终摘要的统一证据来源。分层落到 `manual` / `blocked` 时，再跑 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_manual_reference_topic.py` 判 4 档 verdict：
    - `profile_covered` → profile §5 / reason_code_catalog 已明确收录，**不新增 MR 条目**，交付摘要里引用 profile 对应条目
    - `memory_confirmed` → memory 已有 `confirmed` 条目覆盖本主题，**不新增 MR 条目**，复用 memory 条目的 fix/reason_code 结论
    - `manual_reference_open` → Manual_Reference 已有**未解决**条目，**不新开**，在已有条目末尾补一行 `- 本轮也碰到：<case_name>，<关键现象>`，摘要注明"已叠加到 MR #<id>"
    - `new_entry_needed` → 才 auto-append 新的 `#### <id>. <title>（**自动生成，待人工确认**）`，含涉及文件 / 涉及用例 / 怀疑点源码引用 / 本轮 Spike 观察 / 三条待人工确认问题（是否补入 profile、是否 LinkNan 复核、`reason_code` 确认）

    `compile-only` 只需要交付卡和摘要里说明 Gate D=`N/A` / 不运行原因；除非同时存在待人工判决的问题，否则不写 Manual_Reference。`default` 不触发本步。

    **人工后续确认或 LinkNan 复核完成后**，把该 Manual_Reference 条目标记为已解决（在条目后加 `> 已解决（<日期>）：<结论一句话>`），并用 `workflow_memory.py append --status confirmed` 把解决结论追加到 memory，同时对应 case 的注册状态也一并更新。若人工判决"作废/过时"，**直接从 Manual_Reference 删除该条目**；memory 如有对应记录也一并删除对应 JSON 行。

## Workflow Memory

`$HYPTEST_HOME/.hyptest_workflow_skill/memory/` 是本地经验白名单，**不是流水账**。目标：skill 越用越聪明，只沉淀**几乎确定有用且不会错**的经验。不替代本轮证据，不替代 SKILL.md 硬规则。

### 读端 + 写端：按任务类型分档

| 任务类型 | 默认 query | 完成后自问 append |
|---|---|---|
| bug hunt（`target_module=<m>` + `new-case-only`，或 test_point 文件名含 `suspected_bug_corner_points`） | ✓ 按 `target_module` 关键词 | ✓ |
| 新增测试点 `new-case-only`（有明确模块特征的 `test_point_file`） | ✓ 按 test_point 文件名模块部分 | ✓ |
| `fix-case` 遇到非平凡失败 | ✓ 按 `case_name` / `cause` | ✓ |
| 用户明确提到"以前的 XX 问题 / 复盘 / 历史问题" | 强制查 | 强制自问 |
| **用户本轮给出 Manual_Reference 条目的人工确认结论 / LinkNan 复核结果** | 强制查同 topic 历史 | ✓ 强制 append（`--status confirmed`，附结论） |
| 补已有 `### PnX` 小改 / `run-only` / `preflight-only` / `writeback-only` | ✗ | ✗ |
| `triage-only` | triage skill 自决 | triage skill 自决 |

查询按 topic 精确匹配，memory 2 档状态都直接返回（`unconfirmed` / `confirmed`），人工删行的过时记录自然不再出现；即使总量 100+ 条也只返回相关 10-20 条。

### 写端 3 条强门槛（同时满足才 append；任一不过 → 摘要里写"无经验可沉淀"）

1. **可验证事实，不是猜测**（✗ "感觉 StoreQueue 有问题"）
2. **下次相似任务会用得上**（✗ "今天补了 P13A" 这种流水账）
3. **非平凡**——文档/源码 5 分钟能查到的**不记**（✗ "TEST_END 只能一个"）

每条带日期标签、一条一事、不确定就不写。

CLI 入口（`append` / `query` / `summarize` / 按需 audit）、膨胀控制、与 Claude auto memory 的分工都在 `references/workflow_state.md`。

## Bug Hunt Evidence（仅 bug hunt 场景自动触发）

**本段是 Workflow 步骤 3 "选点"环节的 bug hunt 专用扩展**（用三类资料替代普通相似检索），**不替代** Workflow 其它步骤（唯一性 / profile 标记 / 写 case / 编译运行 / 回填 照常执行）。触发词：`target_module=<module>` + `new-case-only`、`bug_hunt_focus`、"继续围绕 X 找 bug 点"、`test_point_file` 文件名含 `suspected_bug_corner_points`。普通"落 test_point 的 case"任务**不触发**本段，以免增加无谓延迟。

### 核心策略：源码阅读 + profile 边界 + test_point 已有覆盖

bug hunt 主线是从 **RTL 源码 + profile 边界 + 已有 test_point** 找当前未被覆盖的可疑点。

**开工前先校验 `target_module` 拼写**（见 Workflow 步骤 2 已要求跑一次 `check_target_module.py`）——在 RTL 源码里确认模块名真实存在。验证器支持：

- **exact** 匹配（大小写不敏感）：`memblock` / `MemBlock` / `MEMBLOCK` 都命中 `MemBlock`
- **命名规范展开**：`mem_block` / `store_queue` / `load-queue` 自动归一化到 CamelCase
- **fuzzy 候选**（edit distance ≤ 2）：`mmemblock` / `memblck` 列出 `MemBlock` 等候选**让用户确认**，不自动替换
- 候选为空 → 停下报告："`target_module=<值>` 在 RTL 源码里找不到对应文件，请确认拼写"。不能静默继续——静默继续会让 bug hunt 跑偏成"什么都找不到"误导用户"该模块没 bug"。

### 三类资料按优先级读

1. **`references/spec_profiles/<spec_profile>.md` §5 "Spike 不适合 gate 的场景"**——profile 维护者已标出的 **分层事后判据**：这些类别的 case 若跑 Spike 不通，属 Spike 模型边界（走 manual/compile-only）而不是 RTL bug。**§5 只影响事后归因 + reason_code 选择，不替代选点**。用 `$HYPTEST_WORKFLOW_SKILL_HOME/scripts/query_spec_profile.py --nongate-summary --match-module <m> --json` 快速拿机器可读 nongate keyword；结合 profile "Nanhu 实现约束" 段识别当前 Nanhu 不支持的场景（不应设计对应 case）。
2. **target_module 的 RTL 源码**（`$HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main`）——**bug hunt 的选点主力来源**。扫典型 anti-pattern；**anti-pattern 清单与代表性引用例**见 `references/rtl_bug_patterns.md`。
3. **现有 `test_point/**/*.md` 覆盖情况**——用 `rg` 或 `find_similar_cases` 查已覆盖场景，找"RTL 有风险但 test_point 未覆盖"的交集。

三类资料**串行读**，不短路：§5 给事后归因口径，RTL 给选点候选，test_point 给去重和覆盖空隙。选完点再组合证据写怀疑点。

写 test_point 的"怀疑点"段时，用自然语言描述从源码或 profile 得到的具体线索（`<file>.scala:<line>` + 一句话说明为什么可疑）。推测就是推测，不要包装成已验证的 bug。

### 环境缺失兜底

`HYPTEST_LINKNAN_HOME` 不可见或目标 submodule 不在 LinkNan/Nanhu 下时：跳过 RTL 源码阅读；降级到 profile §5 + 现有 test_point + 相似 case 检索；摘要里注明"未读 RTL 源码（环境缺失）"。

### 输出要求

Bug hunt 场景最终交付摘要额外包含：

- 选点所用的证据来源：profile §5 哪条 / 源码哪个 anti-pattern（`<file>.scala:<line>` + 一句话说明）/ 现有 test_point 的覆盖空隙
- 诚实说明怀疑程度：推测就是推测，别包装成已验证 bug

## Why we still write cases when `spike_gate_applicable=false`

profile §5 说"Spike 不适合 gate"时，**case 仍要写**，只是不以 Spike 为 gate。`spike_gate_applicable=false` 是 **gate/runner 路由属性**，不是覆盖价值、风险优先级或测试点重要性的降级信号。选点先由测试点目标、项目 profile、RTL 风险和覆盖空缺决定；分层只决定 case 怎么注册、怎么运行、用什么证据闭环。

因此不要因为某场景不走 official Spike gate，就把它替换成更容易跑 Spike 的近似 baseline，也不要把 `manual` / `D-MANUAL-NONGATE` 解读为"低价值"、"可不写"、"先跳过"。只有当前 profile 明确写成 Nanhu 未实现、环境缺失且无法表达、或测试点本身无新增覆盖时，才停止或降为 blocked/compile-only。

三类用途：

1. **为 LinkNan / RTL 环境准备回归素材**：Spike 不建模但 LinkNan difftest / 真实 RTL 仿真可以 gate。case 写好并 `// TEST_REGISTER(...)` 注释；需要 LinkNan/no-diff、difftest 或 waveform 证据时，把场景、日志和可选 `waveform_context` 交给 `hyptest-failure-triage`，由 triage 指定 runner_mode，workflow 只执行对应 compile/run/edit。
2. **覆盖完成度**：test_point 要求的场景必须有 case——即使 Spike 不能 gate，case 本身是"场景已构造、待跑 LinkNan"的证据。未来 Spike 补了 gap，去掉注释即可翻 default。
3. **验证 profile §5 的描述**：nongate 路由允许"可选跑 Spike 看行为但不翻 default"，实际跑一次能**实证** profile §5 的说法——例如发现"chain mismatch 抑制路径 Spike 可观测，但 chain closed BP 确实不抛"，这类观察可以通过 step 15/16 append memory，或在 `manual` / `blocked` 需要人工复核时写进 Manual_Reference 扩 profile §5。

与 **Nanhu 未实现**（Non-Negotiable §3 第 4 条）的区别：

| | Spike 不适合 gate | Nanhu 未实现 |
|---|---|---|
| Nanhu 行为 | 按 spec 实现 | 根本没实现 |
| case 能 RTL 验证吗 | 能 | 不能（硬件没做）|
| 写 case 有用吗 | **有**（走 nongate 路由）| **无**（僵尸 case）|
| workflow 处理 | nongate 路由；按环境和 oracle 落 `manual` / `compile-only` / `blocked` | **禁止编写**（Non-Negotiable §3 第 4 条）|

## Output Defaults

正面清单：最终交付摘要**必须**包含哪些字段。禁止项见 Non-Negotiables §4。

- 改动文件、case 名、编译结果、运行结果、关键日志路径。
- 实际使用的规格/平台口径（`spec_profile`）。
- **唯一性证据**：测试点覆盖检查结论（范围 + 是否发现相近旧点）、repo 级相似 case 检索 top 结果、函数名精确唯一性结论。
- **test_point → case 映射表**：逐条列出 test_point 每个要求对应到 case 哪一行断言（详见 `references/writing_cases.md` §14.1）。
- `compile-only` 时显式写 Gate D=`N/A` 与不运行原因。
- 若任务是 `new-case-only` 但最终没有新增 `### PnX` 条目和新 case，必须明确说明原因，不能把旧条目或旧 case 当成"新增结果"。
- **memory 动作**（仅在 Workflow 步骤 15 触发的任务类型输出）：列本轮 query 了哪些 topic（或"未查"），append 了什么 / 或明确"无经验可沉淀"。补已有 `### PnX` 小改、run-only 等不触发步骤 15 的任务不用列。
- **非 default 交付卡 / Manual_Reference 动作**：`manual` / `compile-only` / `blocked` 必须说明 submission card 路径。只有 `manual` / `blocked` 触发 Manual_Reference 四档 verdict：说明 `check_manual_reference_topic.py` 的 `verdict`（`profile_covered` / `memory_confirmed` / `manual_reference_open` / `new_entry_needed`）以及对应动作：是否引用了 profile 条目 / 复用了 memory confirmed 条目 / 在已有 MR 条目下补"本轮也碰到"行 / 新 append 了 `#### <id>.（**自动生成，待人工确认**）`；或本轮收到人工 / LinkNan 复核结论，给对应 Manual_Reference 条目加了 `> 已解决（<日期>）：<结论一句话>` + 同步 `workflow_memory.py append --status confirmed`，或者人工判决"作废/过时"**直接删除了 MR 条目 + 对应 memory 行**。`compile-only` 默认不写 Manual_Reference；`default` 不触发本项。

## What To Read

按场景查 reference：

- 规格/profile 路由：`references/spec_and_model_limits.md`
- 当前规格/平台模型边界/Spike gate：`references/spec_profiles/<spec_profile>.md`
- 标准新 case 落地：`references/quick_execution.md` + `references/writing_cases.md` + `references/quality_gate.md`
- 框架 API / 注册 / 工具坑点：`references/framework_usage_pitfalls.md`
- 目录结构 / 平台名 / 环境变量：`references/repo_layout.md`
- 任务参数规格 / preflight：`references/task_input_schema.md`
- 失败定位：`references/build_run_debug.md` + `references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md`
- 失败交接给 triage：`references/triage_handoff_schema.md`
- 非 default 分层：`references/tiering_decision.md` + `references/reason_code_catalog.md`
- 交付前复核：`references/submission_card.md`
- 跨文件测试点覆盖检查或 case 去重：`references/coverage_and_dedupe.md`
- workflow 状态 / cache / memory CLI：`references/workflow_state.md`
- `excpt.cause` 常量怎么选：`references/cause_code_catalog.md`
- RTL 怀疑点示例：`references/rtl_bug_patterns.md`
- 用户侧用法、触发范例、字段速查、反例：`README.md`
- 完整资源索引：`references/resource_index.md`
