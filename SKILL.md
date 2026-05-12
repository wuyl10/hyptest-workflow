---
name: hyptest-workflow
description: hyptest 测试点到用例落地 skill。**必须触发**：新增/改 ai_test_cases 或 manual_test_cases、新增/回填 test_point/**/*.md `### PnX`、更新 test_register.c、跨 test_point 排重或 case 去重、按模块找 suspected bug 并写新测试点、default/manual/compile-only/blocked 初判分层、test_point↔断言映射核对、涉及 hyptest harness (TEST_START/TEST_END/TEST_ASSERT/TEST_SETUP_EXCEPT/TEST_REGISTER) 的 case 编写。spec_profile 路由到 references/spec_profiles/<name>.md。**不触发**：只看 Spike/LinkNan 失败日志不落新 case、FSDB/stuck/50000 cycles/difftest mismatch/suspected RTL bug 深挖 → hyptest-failure-triage；波形协议分析 → waveform-debug；纯 RISC-V 知识问答/Spike 工具链参数/解析 ELF/通用代码 review。
---

# HYPTEST Workflow

Agent 执行入口。触发后按以下优先级执行：

1. **Workflow**（下文）是默认 14 步流程；每步都要遵守 **Non-Negotiables** 的 4 组硬规则
2. 规则冲突按 **Source Priority** 裁决
3. bug hunt 场景在 Workflow 步骤 3 的"选点"环节用 **Bug Hunt Evidence** 的三类资料替代普通相似检索；其它步骤（唯一性 / profile 标记 / 写 case / 编译运行 / 回填）仍按 Workflow 正常执行
4. 输出必满足 **Output Defaults**

用户面向的用法/字段表/触发范例在 `README.md`——agent 不用看 README，只管按本文件执行。

## Source Priority

冲突时按以下顺序裁决：

1. `test_point/Manual_Reference.md`
2. `references/quality_gate.md` + `references/tiering_decision.md` + `references/reason_code_catalog.md` + `references/submission_card.md`
3. `references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md` + `references/writing_cases.md` + `references/framework_usage_pitfalls.md` + `references/build_run_debug.md`
4. `references/repo_layout.md`
5. `test_point/CRITICAL_ISSUES_LOG.md`

补充：

- 顺序问题一律以日志和最小复现实验为准，不以视觉顺序经验做硬判断。
- 存量 case 是学习样本，不高于项目规则。

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
- **prompt 显式给的运行环境字段**（`HYPTEST_SPIKE_BIN` / `HYPTEST_LINKNAN_HOME` / `HYPTEST_DIFFTEST_REF_SO` / `HYPTEST_CROSS_COMPILE` / `HYPTEST_TMPDIR`）**必须映射成 `--env KEY=VALUE`** 传给支持 `--env` 的脚本；`$HYPTEST_SKILL_HOME` 由调用者 export，skill 文档不写死个人绝对路径。Why: 脚本子进程不继承 shell 别名和 prompt 字段，不显式传会拿到 OS 默认或旧值；skill 里写死绝对路径会让其他人 clone 后直接报错。
- 环境 troubleshooting（`~/.bashrc` 非交互 shell 提前 return、`$VAR` 展开失败、submodule 未初始化、`case $-` 保护位置等）见 `references/build_run_debug.md` §7.2，不在 Non-Negotiables 展开。

### 3. 工作流边界（防误判、漏去重、错误扩点）

- **`test_point_file` 是容器，`### PnX` 才是独立测试点**。去重、扩写、复用、完成判定都按条目级进行；不能把整个文件当单个测试点，也不能因为文件之前改过就停止处理新条目或误把旧条目当新增结果。Why: `test_point_file` 里可能有十几个 `### PnX`，"文件改过"≠"每个条目都处理过"；把旧条目包装成新增是**虚假交付**。
- **两种任务模式**：
  - **新增测试点模式**（`task_mode=new-case-only` 或未指定条目）：默认 `coverage_scope=repo` 做全仓 `test_point/**/*.md` 覆盖检查，必须新增新的 `### PnX` 条目和新的 `ai_*` case。新条目编号沿当前文件前缀继续递增（如 `*_points_7.md` 继续补 `P7D/P7E`）。
  - **补已有测试点模式**（`task_mode=supplement-existing-point` 或用户明确指定 `### PnX`）：默认 `coverage_scope=file` 围绕该条目/文件做局部测试点检查，优先在旧条目下补 case，不强行新增新条目。
- **写新 case 或判断 Spike 结果前必须先确定规格/平台口径 `spec_profile`**（未指定则用 profile registry 中的 `default_profile`），再看 `references/spec_and_model_limits.md` 与 `references/spec_profiles/<spec_profile>.md`，**标记**规格来源、平台模型边界、`spike_gate_applicable` 作为初始分层候选（最终分层按 Gate 证据落位，见 `Source Priority`）。Why: 同一个断言在不同 profile 下的结论可能相反（例如 PMA=IO 非对齐在某些 profile 下走 AF，通用 RISC-V 走 AM）。不定口径就判 Spike 结果会把"profile 限制"误认为"RTL bug"。
- **写新 case 前先检索 2~5 个相似存量 case**；模板只作骨架提醒，不替代存量 case 学习。Why: 模板只给形状，存量 case 含本 repo 的**特权态切换顺序、页表/PMP 处理习惯、断言文案风格**。跳过学习容易写出和仓库风格脱节的 case，review 阶段被打回。
- **写新 case 前必须同时做 repo 级 case 相似检索 + 精确唯一性检索**；"相似检索未命中"和"函数名唯一"不是同一件事，两者都要留证据。命名确定后优先用 `scripts/check_case_uniqueness.py --expect absent` 走缓存索引快路径；缓存由 `scripts/repo_evidence_index.py` 预热（见 Workflow 步骤 1），**没预热时脚本会 fallback 到全仓 rg，等于违反此条**。写完后的 postcheck 只作复核，不能替代写前唯一性拦截。`case` 去重始终是 repo 级；`find_similar_cases.py` 始终搜索全仓 `ai_test_cases/*.c` 与 `manual_test_cases/**/*.c`。详见 `references/coverage_and_dedupe.md`。
- **新增测试点前必须先做测试点覆盖检查**；默认按全仓 `test_point/**/*.md` 扫描，不能只看当前文件就声称"全仓未覆盖"。Why: test_point 按模块分文件但**同一怀疑点可能散落在多个文件**。只看当前文件就声称"新点"会造成跨文件重复。
- **若扫描后未发现新的高价值测试点，必须明确说明"未发现新的测试点 / 未新增 case"**，不能把旧条目或旧 case 再次作为新增结果交付。Why: LLM 为了"完成任务"有凑数倾向。硬规则强制承认"这次没找到"，避免把旧成果包装成本轮新增污染历史。
- **case 独立性**：新 case 必须能单跑通过（不依赖前面 case 的 CSR/TLB/cache/reservation 残留）。prepare 段应显式清理本 case 会用到的状态（相关 CSR 位、`sfence_vma`、`TEST_SETUP_EXCEPT()` 等）。Why: 批跑顺序会变（新增/移除 case 影响 `test_register.c` 注册位置；全局 `.data`/`.bss` 段 layout 也会变）。默认只要求单跑通过 + prepare 段显式清理状态即可落 `default`；怀疑有顺序依赖时可手工跑一次窄范围 `get_result.py --platform <plat> --range <本 case 前后几条>` 补对比证据，但不作为硬门禁。

### 4. 输出默认值（禁止项；正面清单见 `Output Defaults`）

- **`test_point` 默认只回填正文和 `已实现 case`**；默认只写 `case_name`，必要时才补短状态；**禁止追加 `[新增 case]`、`[质量门禁结果]`、`[分层结论]`、`[编译/运行统计]` 等审计式块**。Why: `test_point` 是测试意图描述，不是审计日志。加运行证据和分层块会让 test_point 膨胀难读，且审计证据在别处（gate pack / submission card / 最终交付摘要）已有。
- **禁止默认输出 `exclude_check`**。Why: 默认输出会让交付摘要携带无意义字段。
- **禁止默认输出全量 Gate A-H**；只有非 pass Gate 或用户明确要求时，才在最终交付摘要里输出 `[质量门禁结果]`。Why: 全 pass 时列八条"Gate X: pass"纯噪声；只在有问题时列出来反而让工程师一眼看到阻塞点。
- **禁止为 `default` case 默认单独输出 `[分层结论]`**；只有 `manual` / `compile-only` / `blocked`，或用户明确要求时，才在最终交付摘要里输出 `decision_prelim` / `decision_final` / `reason_code`。Why: `default` 是"一切正常"的默认分层，需要解释的是**偏离 default 的情况**；给 default case 加分层块是反向信息量。

## Workflow

默认走"**预热 + 轻量直通**"：`repo_evidence_index` 预热 → `find_similar_cases` → `check_case_uniqueness` → 写 case → `compile_elf` → `get_result` → `check_case_lint` →（失败时）`classify_failure_log` → 回填 → `check_writeback_format --check-register`。**不默认跑 pack 聚合工具**（`case_preflight_pack` / `case_gate_pack` / `case_postcheck_pack` / `make_case_submission_card` / `case_workflow_ledger`）；只有用户明确要求"跑完整 pack"、"输出 submission card"、"复盘耗时"时才走完整 pipeline。质量工具（lint / 失败分类 / 注册一致性）在轻量路径仍必须保留。

1. **锁定输入 + 预热缓存**：确认 `HYPTEST_HOME`、`test_point_file`、平台、case 名、目标分层和 `spec_profile`（未指定则用 profile registry 中的 `default_profile`）；本轮需要运行平台时先用 `scripts/check_env.py` 检查环境。输入字段多或存在旧平台名/不确定模式时用 `scripts/validate_task_request.py` 做 preflight。要做 repo 级检索/唯一性时先预热：
   ```bash
   python3 scripts/repo_evidence_index.py --repo-root $HYPTEST_HOME --json > /dev/null
   ```
2. **识别任务模式**：新增测试点模式 vs 补已有测试点模式（见 Non-Negotiables §3 第 1-2 条）。
3. **覆盖检查 + 相似 + 唯一性**：按 `references/coverage_and_dedupe.md` 做测试点覆盖检查、repo 级 case 相似检索、精确唯一性检索（`check_case_uniqueness.py --expect absent`）。相似检索 `--limit` 按任务分档：
   - 补已有 `### PnX` 且只加 assert / 小改：`--limit 2-3`
   - 补已有 `### PnX` 新增 case：`--limit 3-4`
   - 新增 `### PnX` 或跨模块：`--limit 5`
   - bug hunt / 跨模块扩点：`--limit 5-8`
4. **profile 标记**：读 `references/spec_and_model_limits.md` + `references/spec_profiles/<spec_profile>.md`，标记 `spike_gate_applicable` 作为初始分层候选（最终分层按 Gate 证据落位）。
5. **写或改 case**：AI/批量生成放 `ai_test_cases/*.c`；人工维护放 `manual_test_cases/<module>/`；结构和断言以 `references/writing_cases.md` 为准。
6. **调整 `test_register.c`** 注册状态，使其与目标分层一致。
7. **单 case 编译**：
   ```bash
   python3 compile_elf.py --plat spike --name <case_name>
   ```
8. **单 case 运行**（非 `compile-only`）：
   ```bash
   python3 get_result.py --platform spike --case <case_name>
   ```
   运行前确认平台环境变量在当前进程可见。`compile-only` 允许 Gate D=`N/A`，但必须写明不运行原因。
9. **lint + 失败分类**：
   ```bash
   python3 scripts/check_case_lint.py --repo-root $HYPTEST_HOME --changed-only --strict-case-end
   ```
   运行失败或 `untested exception` 时补一次失败分类（`FAILED` 不是分层结论）：
   ```bash
   python3 scripts/classify_failure_log.py --log-file <log> --json
   ```
10. **test_point → case 映射表自查**：运行通过后，对照 `test_point` 正文逐条列出每个要求落在 case 哪一行断言。发现漏项立即补；发现偏移立即改。详见 `references/writing_cases.md` §14.1。
11. **回填 `test_point`**：默认轻量回填（只写 `case_name` + 必要短状态；不追加审计块）。详细模板和复用口径见 `references/writing_cases.md`。
12. **回填核对**：
   ```bash
   python3 scripts/check_writeback_format.py \
     --repo-root $HYPTEST_HOME \
     --file <test_point_file> \
     --check-register
   ```
13. **memory append 自问**（仅 bug hunt / 新增测试点 / `fix-case` 发现工具坑 / 非预期运行结果等场景）：按 `Workflow Memory` 段的 3 门槛处理。其它任务类型跳过。
14. **Manual_Reference 写回**（仅分层落到 `manual` / `blocked` 且原因涉及**新的模型边界 / Spike nongate / 待人工规则裁定**，不是 profile §5 / `reason_code_catalog` 已明确收录的场景时）：在 `test_point/Manual_Reference.md` 对应 section 末尾 append 一条 `#### <id>. <title>（**自动生成，待人工确认**）`，含涉及文件 / 涉及用例 / 怀疑点源码引用 / 本轮 Spike 观察 / 三条待人工确认问题（是否补入 profile、是否 LinkNan 复核、`reason_code` 确认）。`default` / `compile-only` 不触发本步。**人工后续确认或 LinkNan 复核完成后**，把该 Manual_Reference 条目标记为已解决（在条目后加 `> 已解决（<日期>）：<结论一句话>`），并用 `workflow_memory.py append --status fixed` 把解决结论追加到 memory，同时对应 case 的注册状态也一并更新。

## Workflow Memory

`$HYPTEST_HOME/.hyptest_workflow_skill/memory/` 是本地经验白名单，**不是流水账**。目标：skill 越用越聪明，只沉淀**几乎确定有用且不会错**的经验。不替代本轮证据，不替代 SKILL.md 硬规则。详细 CLI 见 `references/workflow_state.md`。

### 读端 + 写端：按任务类型分档

| 任务类型 | 默认 query | 完成后自问 append |
|---|---|---|
| bug hunt（`target_module=<m>` + `new-case-only`，或 test_point 文件名含 `suspected_bug_corner_points`） | ✓ 按 `target_module` 关键词 | ✓ |
| 新增测试点 `new-case-only`（有明确模块特征的 `test_point_file`） | ✓ 按 test_point 文件名模块部分 | ✓ |
| `fix-case` 遇到非平凡失败 | ✓ 按 `case_name` / `cause` | ✓ |
| 用户明确提到"以前的 XX 问题 / 复盘 / 历史问题" | 强制查 | 强制自问 |
| **用户本轮给出 Manual_Reference 条目的人工确认结论 / LinkNan 复核结果** | 强制查同 topic 历史 | ✓ 强制 append（`--status fixed`，附结论） |
| 补已有 `### PnX` 小改 / `run-only` / `preflight-only` / `writeback-only` | ✗ | ✗ |
| `triage-only` | triage skill 自决 | triage skill 自决 |

查询按 topic 精确匹配，自动过滤 `status=obsolete`，即使总量到 100+ 条也只返回相关 10-20 条。

### 写端：3 条强门槛（同时满足才 append）

过 3 门槛，**任一不满足就不写**。宁缺毋滥。

1. **可验证事实，不是猜测**（✗ "感觉 StoreQueue 有问题"）
2. **下次相似任务会用得上**（✗ "今天补了 P13A" 这种流水账）
3. **非平凡**——文档/源码 5 分钟能查到的**不记**（✗ "TEST_END 只能一个"）

**补充**：每条带日期标签、一条一事、不确定就不写。

```bash
# append（三门槛全过才跑）
python3 scripts/workflow_memory.py append --repo-root $HYPTEST_HOME --topic <kw> --note "<...>"

# 标过时
python3 scripts/workflow_memory.py append --repo-root $HYPTEST_HOME --topic <kw> --status obsolete --note "<...>"
```

**3 门槛全过** → append；**任一不过** → 摘要里写"无经验可沉淀"（不 append）。

### 膨胀控制

- 3 门槛把关（写端） + `status=obsolete` 过滤（读端） + 按需 audit 清过时的
- 典型规模：一年 20-50 条、几十 KB、按 topic 检索不会线性变慢

用户发 "audit workflow memory" / "清理过时 memory" 类 prompt 时的具体步骤见 `references/workflow_state.md` 的"按需 audit"段。

## Bug Hunt Evidence（仅 bug hunt 场景自动触发）

**本段是 Workflow 步骤 3 "选点"环节的 bug hunt 专用扩展**（用三类资料替代普通相似检索），**不替代** Workflow 其它步骤（唯一性 / profile 标记 / 写 case / 编译运行 / 回填 照常执行）。触发词：`target_module=<module>` + `new-case-only`、`bug_hunt_focus`、"继续围绕 X 找 bug 点"、`test_point_file` 文件名含 `suspected_bug_corner_points`。普通"落 test_point 的 case"任务**不触发**本段，以免增加无谓延迟。

### 核心策略：源码阅读 + profile 边界 + test_point 已有覆盖

bug hunt 主线是从 **RTL 源码 + profile 边界 + 已有 test_point** 找当前未被覆盖的可疑点。

**开工前先校验 `target_module` 拼写**：

```bash
# 校验 target_module 在 Chisel 源码里真实存在（自动展开大驼峰：memblock → MemBlock）
ls $HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main 2>/dev/null \
  | grep -iE "^<target_module>$|<target_module>\.scala$" \
  || find $HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main -type f -iname "*<target_module>*" | head -5
```

或用 `find -iname "*<module>*"`（大小写不敏感）验证。如果查不到任何匹配文件，**停下提醒用户**："`target_module=<值>` 在 RTL 源码里找不到对应文件，请确认拼写（`memblock` 而非 `mmemblock`）"。不能静默继续——静默继续会让 bug hunt 跑偏成"什么都找不到"误导用户"该模块没 bug"。

### 源码可疑点识别（主要动作）

按优先级读以下三类资料，每读一处提取可疑点候选：

1. **`references/spec_profiles/<spec_profile>.md` §5 "Spike 不适合 gate 的场景"**
   - profile 维护者已标出的**已知高风险领域**：TLB/cache/CBO/refill/replay/sbuffer/MSHR/reservation/PMA CSR 等
   - target_module 属于哪些类别 → 优先在这些类别里找 corner

2. **target_module 的 RTL 源码**（`$HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main`）
   - 看 anti-pattern：
     - `WireDefault(false.B)` 后条件分支不完整
     - `Valid` 输出但无对应 `ready` 握手
     - `Reg(Vec)` 资源共用但无显式 retire/dealloc
     - 粘性 CSR（trigger/pmp/mstatus）未清
     - 特权态切换时状态未重置

3. **现有 `test_point/**/*.md` 覆盖情况**
   - 用 `rg` 或 `find_similar_cases` 查 target_module 相关 test_point 已覆盖哪些场景
   - 找"profile 关心但 test_point 未覆盖"的交集——这是确认的未覆盖区域

写 test_point 的"怀疑点"段时，用自然语言描述从源码或 profile 得到的具体线索（`<file>.scala:<line>` + 一句话说明为什么可疑）。推测就是推测，不要包装成已验证的 bug。

### 环境缺失兜底

`HYPTEST_LINKNAN_HOME` 不可见或目标 submodule 不在 LinkNan/Nanhu 下时：

- 跳过 RTL 源码阅读（无法访问）
- 降级到 profile §5 + 现有 test_point + 相似 case 检索
- 摘要里注明"未读 RTL 源码（环境缺失）"

### 输出要求

Bug hunt 场景最终交付摘要额外包含：

- 选点所用的证据来源：profile §5 哪条 / 源码哪个 anti-pattern（`<file>.scala:<line>` + 一句话说明）/ 现有 test_point 的覆盖空隙
- 诚实说明怀疑程度：推测就是推测，别包装成已验证 bug

## Output Defaults

正面清单：最终交付摘要**必须**包含哪些字段。禁止项见 Non-Negotiables §4。

- 改动文件、case 名、编译结果、运行结果、关键日志路径。
- 实际使用的规格/平台口径（`spec_profile`）。
- **唯一性证据**：测试点覆盖检查结论（范围 + 是否发现相近旧点）、repo 级相似 case 检索 top 结果、函数名精确唯一性结论。
- **test_point → case 映射表**：逐条列出 test_point 每个要求对应到 case 哪一行断言（详见 `references/writing_cases.md` §14.1）。
- `compile-only` 时显式写 Gate D=`N/A` 与不运行原因。
- 若任务是 `new-case-only` 但最终没有新增 `### PnX` 条目和新 case，必须明确说明原因，不能把旧条目或旧 case 当成"新增结果"。
- **memory 动作**（仅在 Workflow 步骤 13 触发的任务类型输出）：列本轮 query 了哪些 topic（或"未查"），append 了什么 / 或明确"无经验可沉淀"。补已有 `### PnX` 小改、run-only 等不触发步骤 13 的任务不用列。
- **Manual_Reference 动作**（仅在 Workflow 步骤 14 触发时输出）：说明是否在 `test_point/Manual_Reference.md` 对应 section append 了 `#### <id>.（**自动生成，待人工确认**）` 条目 + 附的 3 条待人工确认问题；或本轮收到人工 / LinkNan 复核结论、给对应 Manual_Reference 条目加了 `> 已解决（<日期>）：<结论一句话>` + 同步 `workflow_memory.py append --status fixed`。`default` / `compile-only` 不触发本步，摘要里明确"未触发"。

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
