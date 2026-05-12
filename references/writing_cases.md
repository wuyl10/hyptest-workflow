# HYPTEST 用例编写指南

本文面向 `riscv-hyp-tests` 仓库（`$HYPTEST_HOME` 指向的工作目录），用于规范 AI/人工协同写 case 的方式。skill 不绑死某个 fork 或分支；具体 URL/分支以 `$HYPTEST_HOME` 实际指向为准。

## Table of Contents

- [1. 放置位置与命名](#1-放置位置与命名) — 目录规则、命名前缀、大文件拆分、写前学存量 case
- [2. 基础函数结构](#2-基础函数结构) — case 骨架模板
- [3. 断言与可观测性](#3-断言与可观测性) — 面向 `excpt.*` / 数据 / 边界
- [4. 异常路径写法](#4-异常路径写法) — `TEST_SETUP_EXCEPT` 使用口径、异常后清理
- [5. 特权态和环境切换建议](#5-特权态和环境切换建议)
- [6. 注册与回归准入](#6-注册与回归准入) — test_register.c、三层准入策略
- [7. 测试点回填](#7-测试点回填) — 默认/扩展模板、复用依据四行、一一映射
- [8. 高质量 case 的最小标准](#8-高质量-case-的最小标准)
- [9. 常见反模式](#9-常见反模式)
- [10. 推荐起步流程](#10-推荐起步流程)
- [11. 建议的四段式 case 结构](#11-建议的四段式-case-结构) — prepare/action/observe/validate
- [12. side effect 检查建议](#12-side-effect-检查建议) — store/amo 目标 + 邻接
- [13. 异常路径的状态隔离建议](#13-异常路径的状态隔离建议)
- [13.1 Case 独立性](#131-case-独立性) — prepare 段清理清单
- [14. 提交前硬检查](#14-提交前硬检查可复制到-pr-描述) — PR 前勾选清单
- [14.1 test_point → case 映射表自查](#141-test_point--case-映射表自查写完运行通过后必做) — 覆盖完整性核对

## 1. 放置位置与命名

- AI/批量生成的新用例默认放在 `ai_test_cases/*.c`。
- 人工维护的新用例按模块放在 `manual_test_cases/<module>/`。
- 用例函数返回值必须是 `bool`。
- 推荐命名前缀：
  - 架构语义：`ai_arch_*`
  - 微架构路径：`ai_micro_*`
- 命名应包含关键维度：
  - 指令类型（load/store/amo/prefetch/sfence）
  - 场景（cross_page/cross_16b/pbmt/pmp/trigger）
  - 预期（page_fault/access_fault/misaligned/recovers）

示例：

- `ai_arch_load_misalign_pf_priority`
- `ai_micro_hs_load_cross_page_high_half_page_fault`
- `ai_micro_m_store_cross_16b_second_split_access_fault_then_same_address_valid_store_recovers_corner`

### 1.1 大文件拆分规则

- 若目标文件已经明显过长，或用户已明确指出该文件“不应继续追加”，应优先新建主题明确的 case 文件承载新 case。
- 对已经成为“历史大文件”的目标，例如 `ai_micro_mmode_memblock_cases.c`，不要默认继续往里堆新 case。
- 新文件命名应反映主题或子场景，例如：
  - `ai_micro_mmode_memblock_followup_cases.c`
  - `ai_micro_mmode_memblock_mab_flush_cases.c`
  - `ai_micro_mmode_memblock_p4_cases.c`
- 新建文件后，仍需按现有仓库规则确认它会被编译系统自动收集。

### 1.2 写新 case 前先看存量 case

- 写新 case 时，优先从仓库现有 `ai_test_cases/*.c` 与 `manual_test_cases/**/*.c` 中找 2~5 个相似 case，再决定如何落地；不要上来就套模板。
- 存量 case 的价值主要在于：
  - 看这个仓库现有的环境构造方式
  - 看断言文案和 `cause/tval/data/guard` 的组合习惯
  - 看相似路径下常见的特权态切换、页表/PMP/PBMT 处理顺序
- 但存量 case 不是高于规则的真值。遇到冲突时，优先级始终是：
  - `test_point/Manual_Reference.md`
  - 本 skill 的门禁/分层/规则文档
  - 存量 case
- 不要机械照抄存量 case。必须先比对：
  - 场景顺序是否一致
  - 断言覆盖是否一致
  - 特权态/翻译路径是否一致
  - 是否只是“邻近 case”而非“目标 case”
- 优先参考这些存量 case：
  - 已在 `test_register.c` 中启用的 default case
  - 与当前测试点关键维度最接近的 case
  - 近期风格一致、断言完整、仍被频繁复用的 case
- 谨慎参考这些存量 case：
  - `manual` / `compile-only` / 已注释 case
  - 大文件中风格明显陈旧、断言偏弱、只做近似覆盖的 case
  - 规则口径已经发生变化的旧 case（例如 misalign、PMA/PBMT、Spike 偏差相关）
- 需要骨架时，再把 `assets/templates/new_case_template.c` 当作“空白骨架”；模板不替代对存量 case 的检索。

## 2. 基础函数结构

推荐骨架：

```c
bool ai_xxx_case_name()
{
    TEST_START();

    goto_priv(PRIV_M);
    // 1) 准备数据/页表/PMP/PBMT环境

    // 2) 若本步骤要检查 excpt.*，先初始化异常状态
    // TEST_SETUP_EXCEPT();

    // 3) 执行目标指令/路径

    // 4) 断言
    TEST_ASSERT("行为描述", condition);

    TEST_END("ai_xxx_case_name");
}
```

说明：

- `TEST_END(...)` 在一个函数里只能出现一次。
- 若中途失败想提前退出，直接 `return false;`，不要再写第二个 `TEST_END(...)`。
- `TEST_END` 会执行收尾（回到 M 态、重置状态）。

## 3. 断言与可观测性

断言必须面向“可观测结果”，避免只断言中间变量。

优先断言维度：

- `excpt.triggered`
- `excpt.cause`
- `excpt.tval`
- 数据值（load 结果、store 后内存值）
- 邻接区域不被污染（adjacent preserved）

推荐写法：

```c
TEST_ASSERT("high-half load PF with second-half tval",
    excpt.triggered &&
    excpt.cause == CAUSE_LPF &&
    excpt.tval == expected_second_half_vaddr
);
```

## 4. 异常路径写法

### 4.1 什么时候用 TEST_SETUP_EXCEPT

规则不是“只在预期异常时使用”，而是：

- 只要本步骤要断言 `excpt.triggered/cause/tval`，无论预期 `true` 还是 `false`，都先调用 `TEST_SETUP_EXCEPT()` 初始化状态。
- 如果该步骤不读取 `excpt.*`，可以不调用。
- 不要把它当成“掩盖真实异常”的通用保险。

```c
TEST_SETUP_EXCEPT();
volatile uint64_t v = *(volatile uint64_t *)fault_addr;
(void)v;
TEST_ASSERT("expect load access fault", excpt.triggered && excpt.cause == CAUSE_LAF);
```

```c
TEST_SETUP_EXCEPT();
uint64_t val = *(volatile uint64_t *)ok_addr;
TEST_ASSERT("normal load should keep triggered=false",
    excpt.triggered == false && val == expected);
```

### 4.2 异常后清理

当一个 case 里有多段 fault/recovery 过程时：

- 在关键切换点重置异常状态（按框架现有风格处理）
- 每段操作前确保环境一致（页表、PMP、PBMT、权限）
- 避免上一次 fault 的状态污染下一段断言
- `reset_state()` 主要做 CSR/状态重置，不等价于异常状态初始化；检查 `excpt.*` 前仍应显式调用 `TEST_SETUP_EXCEPT()`

## 5. 特权态和环境切换建议

- 用 `goto_priv(...)` 显式切换特权态。
- 特权态、H 扩展、HS helper 语义别名等范围以当前 `spec_profile` 为准；先读 `references/spec_and_model_limits.md` 与 `references/spec_profiles/<spec_profile>.md`。
- 与页表翻译相关的场景优先走 `M-mode + MPRV` 或项目既有 HS/S 语义路径，保持与现有 case 风格一致。
- 涉及翻译修改后要配合 `sfence_vma()`。
- 涉及 PMA/PBMT 操作时，严格标注场景来源（PMA 还是 PBMT）。

## 6. 注册与回归准入

### 6.1 注册位置

- 统一在 `test_register.c` 中 `TEST_REGISTER(...)`。
- 不在 case 源文件末尾注册。

### 6.2 执行顺序注意

`test_register.c` 的视觉顺序不应被当成唯一真值。实际执行顺序受 `.test_table` 收集与链接布局影响，调试时应以日志与最小复现实验结果为准。

因此调试时：

- 先做最小复现（仅保留 1~3 个可疑 case）确认真实顺序。
- 卡死时先看“最后打印/最后进入”的 case，而不是只按文件上下位置猜。
- 新 case 建议先放在便于快速隔离的位置。
- 稳定后再挪到目标分组。

### 6.3 三层准入策略

- default：打开注册，参与常规批跑。
- manual：保留代码和映射，默认注释注册，人工确认。
- compile-only：只要求可编译，默认不进 Spike gate。

## 7. 测试点回填

需要把 case 名回填到对应测试点文件，保持“测试点 -> 用例”可追踪。

回填建议格式：

- 已闭环：`case_name`
- 已闭环且希望显式说明注册状态：`case_name（default，已启用）`
- manual：`case_name（已注释，manual）`
- compile-only：`case_name（compile-only，未跑Spike）`
- 依赖 PMA/PBMT 且未走 Spike gate：`case_name（依赖PMA CSR/TLB一致性/cache一致性，未跑Spike）`

不要在 `test_point` 正文后追加 workflow 回填块或审计式证据块。
新回填优先使用 `case_name（已注释，manual）`；`check_writeback_format.py` 也接受短状态写法 `case_name 已注释（manual）`。
若任务要求输出 `Gate A-H`、`decision_prelim` / `decision_final`、`reason_code`，默认放到最终交付摘要，不写进 `test_point`。

### 7.1 测试点正文模板（默认简版 + RTL扩展）

当本轮不只是“追加映射”，而是新增/改写 `test_point_file` 的正文描述时，默认使用“标题 + 双模板”。下面给出按当前推荐口径整理后的常用示例：

- 默认模板（不需要从 RTL/源码定位可疑点；`new-case-only` 最常用）：

```text
### P6X. same-page cross-16B translated scalar store 的 refault repair 后再次同模板 success store 是否仍无 stale state

测试点：

- 在 same-page scalar cross-16B `sd(1B+7B)` 的 repeated fault/retry 路径里，refault repair 后再次发起同地址同模板 success store，应该继续 trap-free，且最终 boundary image 只保留最新 overlay。

构建场景：

- `sd(1B+7B)` repeated `SAF` -> repair -> upper-half aligned `sd(8B)` success x4 -> refault `SAF` -> repair -> retried original-template `sd(1B+7B)` success -> immediate same-address same-template `sd(1B+7B)` success
- 使用 `guard_before[8B] | boundary[16B] | guard_after[8B]` 布局。
- 最终要求 `excpt.triggered == false`，boundary image 正确，guard 区不变。

已实现 case：

- `ai_micro_xxx_case_name`（default，已启用）
```

- 扩展模板（需要从 RTL/源码定位可疑点）：

```text
### P6Y. same-page cross-16B translated scalar store 的 retry 后 width-switch store 是否会误复用旧模板

测试点：

- retry 成功后立刻切到同地址不同模板 `sw(1B+3B)`，应该只刷新当前窄模板，不应把旧 `sd` 模板残留一起带出来。

怀疑点：

- [evidence=commit] `<RTL/path/File.scala:line>`（commit `<hash>`，`git log` 查到的已修复 bug，当前场景在其邻域但未直接覆盖）
- [evidence=speculation] `<RTL/path/Other.scala:line>` 描述与本测试点相关的可疑交互点（仅源码阅读推测，无已知 commit / 无复现日志）

对应场景：

- `sd(1B+7B)` repeated `SAF` -> repair -> upper-half aligned `sd(8B)` success x4 -> refault `SAF` -> repair -> retried `sd(1B+7B)` success -> immediate `sw(1B+3B)` success
- 最终要求 `sw` trap-free，只覆盖 bytes7-10，不破坏其余 boundary image。

已实现 case：

- `ai_micro_xxx_width_switch_case`（default，已启用）
```

怀疑点证据分级（在 `[evidence=<level>]` 方括号标签中写明）：

- `commit`：有 git log 的 RTL fix commit 明确指向该路径（最强证据，优先追问；可用 `scripts/query_rtl_bug_history.py` 交叉验证）。
- `log-confirmed`：有当前项目可复现的失败日志指向该路径。
- `suggestive`：RTL 代码中该段逻辑有已知 anti-pattern（例如 always-true 默认值、不对称的 ready/valid、resource 被共用但无退场信号）。
- `speculation`：单纯源码阅读推测，没有 commit/日志/已知 pattern 支撑。

同一测试点可以列多个怀疑点，按 `commit > log-confirmed > suggestive > speculation` 排序，让审阅者一眼看出最硬的证据。`speculation` 级可以保留但不应作为"这条 case 一定能抓 bug"的理由。

- 复用已有 case 时，才追加固定四行 `复用依据`：

```text
已实现 case：

- `ai_micro_existing_case`

复用依据（仅复用已有 case 时填写）：

顺序一致性：一致；测试点顺序=fault -> repair -> success；复用 case 顺序=fault -> repair -> success；差异=无
断言一致性：一致；测试点断言=检查 `excpt.triggered/cause/tval` 与 boundary image；复用 case 断言=检查 `excpt.triggered/cause/tval` 与 boundary image；差异=无
关键变量一致性：一致；测试点关键项=`sd(1B+7B)`+repeated SAF+upper-half aligned；复用 case 关键项=`sd(1B+7B)`+repeated SAF+upper-half aligned；差异=无
覆盖粒度一致性：一致；测试点粒度=byte boundary + cross-16B；复用 case 粒度=byte boundary + cross-16B；差异=无
```

建议：

- 每个测试点条目都先写标题，再选默认模板或扩展模板。
- 默认优先简版模板；满足以下任一条件时启用扩展模板：新增/修改了源码怀疑点、需要引用 RTL/源码位置解释判定、分层结论依赖模块实现细节。
- 简版模板中的 `构建场景` 与扩展模板中的 `对应场景` 都应可直接指导 case 构造，避免只写抽象结论。
- 需要项目内具体 RTL 怀疑点示例时，看 `references/rtl_bug_patterns.md`；不要把那里的项目路径写成通用规则。
- `new-case-only` 场景通常只写到 `已实现 case` 即可；只有复用已有 case 时才出现 `复用依据` 四行。
- `已实现 case` 段只放与该测试点一一对应的 case；默认只写 `case_name`，只有确有必要时才附短状态说明；不要在这里写文件名、函数签名、日志、Gate 结果或分层块。若当前无新增且无可复用 case，写 `暂无（原因：...）`。
- 若复用已有 case，必须补"复用依据"，且固定为四行字段：`顺序一致性`、`断言一致性`、`关键变量一致性`、`覆盖粒度一致性`。任一行差异非"无"，就不能把旧 case 当作复用，应新增 case 或标 `blocked`。
- `test_point` 回填到 `已实现 case` / `复用依据` 即结束；除非用户明确要求，不再追加 `[新增 case]`、`[唯一性检索证据]`、`[质量门禁结果]`、`[分层结论]` 等块。

### 7.2 测试点与 case 必须一一映射

- 新增 case 或复用已有 case 都必须严格符合测试点要求并逐项映射到对应 bug 场景。
- 不允许用“很像但不完全相同”的路径替代测试点要求的路径。
- 若测试点要求包含特定模板、producer 切换、fault 次序、地址布局、guard 检查或期望 `tval/cause`，case 必须逐项落到断言里。
- 若复用已有 case，必须在回填里给出固定四行"复用依据"（`顺序一致性` + `断言一致性` + `关键变量一致性` + `覆盖粒度一致性`），否则视为未覆盖。
- 若最终发现无法构造出测试点要求的场景，应在结论里明确 `blocked`，而不是拿邻近 case 顶替。

## 8. 高质量 case 的最小标准

- 命名唯一，语义清晰。
- 断言覆盖 cause/tval/数据至少两类以上。
- 对 store 类场景检查 side effect 边界。
- 异常和恢复路径都覆盖（fault + recover）。
- 能被单 case 编译脚本独立编译。

## 9. 常见反模式

- 在不检查 `excpt.*` 的路径机械性滥用 `TEST_SETUP_EXCEPT()`。
- 一个函数写多个 `TEST_END`。
- 只验证“触发了异常”，不验证 `cause/tval`。
- 只验证目标地址，不验证邻接地址污染。
- 把 PMA=IO 与 PBMT=IO 混写为同一语义。
- 未更新 `test_point` 和 `test_register.c` 就宣称完成。

## 10. 推荐起步流程

1. 从 `test_point` 选 1 个小场景。
2. 检索 2~5 个相似存量 case，确认最值得复用的结构和断言。
3. 在合适的 case 目录写 1 个基础 case（非 corner）。
4. 用 `compile_elf.py --name <case>` 单点编译。
5. 用单 ELF Spike 命令跑通。
6. 回填测试点后，再扩展 repeated/adjacent/cross-producer corner。

## 11. 建议的四段式 case 结构

推荐把每个 case 显式拆成 4 段，便于定位：

1. prepare：初始化内存、页表、权限、PBMT/PMA、寄存器
2. action：执行目标路径（fault 或 normal）
3. observe：采集异常与数据结果
4. validate：断言 cause/tval/数据/side effect

建议每段之间保留最小必要注释，不要把多种语义混在一段中。

## 12. side effect 检查建议

对 store/amo/vector store 场景，建议同时检查：

- 目标地址最终值（expected target）
- 邻接地址保持不变（expected adjacent）
- 若是 split/cross-page：低半区与高半区分别校验

推荐断言风格：

```c
TEST_ASSERT("target word updated as expected", target_val == expected_target);
TEST_ASSERT("adjacent word remains unchanged", adjacent_val == expected_adjacent);
```

## 13. 异常路径的状态隔离建议

多段 fault/recovery case 中，建议每一段都做到：

- 段首明确当前特权态（`goto_priv(...)`）
- 段首明确本段是否检查 `excpt.*`（若检查则先调用 `TEST_SETUP_EXCEPT()`）
- 段尾完成本段断言后再进入下一段

不要把“上一段的异常残留”当作下一段的判定依据。

## 13.1 Case 独立性

新 case 的一个隐性质量指标：**能不能独立跑通，不依赖前面 case 的副作用**。这关系到未来 `test_register.c` 注册顺序调整或某个前置 case 被移除后，当前 case 是否仍然表达原测试意图。

prepare 段应显式清理本 case 用到的状态，常见需要清理/初始化的项目：

- CSR 残留：`mstatus.SUM/MXR`、`satp`、`menvcfg`、`senvcfg` 等本 case 会读/依赖的位
- 翻译状态：相关页表项 + `sfence_vma(...)`；跨 ASID 时显式指定
- Reservation：LR/SC 场景前做一次 dummy 操作清掉 reservation；或明确本 case 不依赖前 case reservation 状态
- 异常状态：检查 `excpt.*` 前 `TEST_SETUP_EXCEPT()`
- TLB/cache 预热假设：如果 case 真的**需要** warm cache / 预热 alias，prepare 段要显式构造；不要假设前面 case 刚好留了需要的状态

**写完单跑通过**即可落 `default`。`compile-only` 不跑运行时本条不适用。

怀疑有顺序依赖或 case 涉及跨 case 可见的全局状态（改过 `test_register.c` 的分组、共用 static 变量、触发 trigger/PMP 等粘性 CSR）时，可以手工跑一次窄范围的批跑做对比：

```bash
python3 get_result.py --platform spike --range <本 case 前后几条行号>
```

单跑 PASS 但窄范围批跑 FAIL，说明本 case 对前置 case 的副作用有依赖，应该标 `manual` + `reason_code="顺序敏感"`，并回头补 prepare 段的状态清理。这不是硬门禁（会给每次新增 case 多花 30-90s），按需使用。

## 14. 提交前硬检查（可复制到 PR 描述）

- case 源文件中函数命名与文件命名语义一致
- 单函数仅 1 个 `TEST_END(...)`
- 已完成单 case 编译
- 非 compile-only：已完成单 case 运行且日志中失败类型已归因（不是只给 `FAILED`）
- compile-only：已注明 Gate D=N/A、不运行原因与分层依据
- 已完成 `test_point` 轻量回填（case 名 + 必要短状态；非 default 结论可在交付摘要中说明）
- `test_register.c` 注册状态与分层策略一致
- **已做 test_point → case 映射表自查**：逐条列出 test_point 每个要求对应到 case 哪一行断言；漏项已补、偏移已改

### 14.1 test_point → case 映射表自查（写完运行通过后必做）

对照 test_point 正文（尤其"构建场景"或扩展模板的"对应场景"），逐条列出**哪一条要求落在 case 的哪一行**：

```text
test_point 要求 → case 断言位置
- "repeated SAF"           → L28 TEST_ASSERT("first SAF", excpt.cause==CAUSE_SAF)
                              L42 TEST_ASSERT("second SAF", excpt.cause==CAUSE_SAF)
- "repair 后再 retry 成功"  → L58 TEST_ASSERT("retried trap-free", excpt.triggered==false)
- "boundary image 保持"     → L71 TEST_ASSERT("guard_before unchanged", guard_before==0xCC)
                              L72 TEST_ASSERT("guard_after unchanged", guard_after==0xCC)
- "最终 sw trap-free"       → L85 TEST_ASSERT("final sw no trap", excpt.triggered==false)
```

这一步的目的：

- **抓漏项**：test_point 要求了但断言里没写的，立即补（例如要求查 boundary 但只断言了 target）
- **抓偏移**：断言方向跟 test_point 不一致的，立即改（例如 test_point 说 `CAUSE_SAF` 但写成了 `CAUSE_LAF`，参考 `references/cause_code_catalog.md`）
- **抓场景不匹配**：test_point 要 cross-16B 但 case 写成 cross-page，改回来

工作方式：

- 运行通过后、回填 test_point 前，在最终交付摘要里**显式输出一次这张表**（不写到 test_point 正文，只放摘要）
- 如果 test_point 某条要求无法在 case 里构造（平台/环境/模型限制），在表里写明 `blocked` 原因，不要偷换成邻近场景
- 补已有 `### PnX` 只加 assert 时，映射表也要做，只是只列本次改动的那几条

映射表的时间开销 < 1 分钟，但能抓到 20-30% 的"写完才发现漏"类错误。
