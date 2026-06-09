# HYPTEST 原因码目录

本文定义统一原因码，避免同类问题在不同任务中使用不同口径。

## 1. 命名规则

- 格式：`D-<CLASS>-<TAG>`
- `CLASS` 取值：`PASS` / `MANUAL` / `COMPILE` / `BLOCK`
- `TAG` 描述主要触发原因

## 2. 原因码清单

### 2.1 PASS 类（可进 default）

- `D-PASS-DEFAULT`
  - 触发：编译通过 + 运行通过 + 规则一致 + 可作为 Spike gate
  - 最小证据：编译记录、运行记录、规则核对、日志路径
  - 后续动作：进入 default，保持注册开启

### 2.2 MANUAL 类（不进 default，但场景保留）

- `D-MANUAL-NONGATE`
  - 触发：场景不宜以 Spike 作为 gate（常见于 PMA/PBMT/MMIO/cache/TLB/CBO/refill/replay/sbuffer/MSHR/PMP 粒度等模型边界）
  - 最小证据：规则引用 + 场景说明 + 运行/环境限制说明
  - 后续动作：标为 manual，回填原因
  - 注意：PMA/PBMT/MMIO 关键词只产生候选。若当前现象是 `linknan-difftest` / `HYPTEST_DIFFTEST_REF_SO` 的 REF-DUT mismatch，先交 `hyptest-failure-triage` 做 first-divergence、PMA CSR/profile、PA window、responder 分析；不能只凭关键词直接用本 code 收口。

- `D-MANUAL-UNSTABLE`
  - 触发：语义可解释，但 Spike 运行不稳定
  - 最小证据：多次运行差异、失败日志、规则一致性说明
  - 后续动作：标为 manual，补充稳定性观察计划

- `D-MANUAL-RTL-ONLY`
  - 触发：语义面向 RTL 现象，当前仿真平台无法完整验证
  - 最小证据：场景说明 + 平台限制说明
  - 后续动作：标为 manual，等待 RTL 环境验证

- `D-MANUAL-SPIKE-GAP`
  - 触发：Nanhu RTL 按 spec 正确实现了该语义，通常是 official/community Spike (`HYPTEST_SPIKE_BIN`) 有实现 gap（未建模该 spec 场景）；Spike 过或不过都不能作为 gate。若暂时复用本 code 表达 `linknan-difftest` / `HYPTEST_DIFFTEST_REF_SO` 的 reference gap，必须已有 REF-DUT first-divergence 证明这是 LinkNan difftest REF/model alignment gap，而不是待定位的 DUT/PMA/responder 问题。
  - 最小证据：指向 spec 的引用（spec 哪段要求该行为）+ Spike 实测不一致证据 + LinkNan/RTL 复核证据（或待补记录）
  - 后续动作：标为 manual；step 16 `check_manual_reference_topic.py` 按 verdict 路由（profile §5 已覆盖则引用、memory confirmed 已覆盖则复用、MR 已有未解决条目则叠加、否则 auto-append `#### <id>.（**自动生成，待人工确认**）` 记录 Spike gap 位置）；RTL 跑通后可回归
  - LinkNan difftest 注意：若不一致来自 `linknan-difftest` / `HYPTEST_DIFFTEST_REF_SO`，不要只写“Spike gap”。摘要和 test_point 短状态必须明确 runner 是 LinkNan difftest reference、写出 LinkNan difftest REF/model alignment gap、REF-DUT first-divergence 证据和为什么按本 code 暂放；若只是待定位的 REF-DUT PMA/MMIO/CSR 对齐问题，优先交 `hyptest-failure-triage` 继续归因，不用本 code 直接收口。

- `D-MANUAL-NANHU-NOT-IMPL`
  - 触发：目标语义超出 Nanhu 当前实现范围（例如 data trigger / 3+ 层 chain / 本版本未实现的 debug 特性）
  - **硬规则（SKILL.md Non-Negotiable §3 第 4 条）**：遇到此类 corner **默认禁止编写 case**——应回退到 Nanhu 已实现的等价角度，或停下来请用户确认。只有用户**显式确认**作为"未来 Nanhu 支持后的占位"（极罕见）才允许用这个 code；否则不该出现在交付里。
  - 最小证据：Nanhu 实现范围引用（`references/spec_profiles/<profile>.md` 对应段落）+ 用户显式确认保留的依据 + 为什么不回退到已实现等价场景
  - 后续动作：**优先回退**；`check_writeback_format.py --check-reason-code` 会对此 code 抛 `reason_code_nanhu_not_impl` warning 提示 reviewer 复核（不硬 fail，给占位留出口）；step 16 走 verdict 路由落条目（未覆盖时 auto-append 待人工确认），写清 Nanhu 哪段没实现、何时可回归

### 2.3 COMPILE 类（仅编译准入）

- `D-COMPILE-ONLY-ENV`
  - 触发：具备编译条件，但运行 gate 不成立（环境或平台限制）
  - 最小证据：编译通过记录 + 运行不可用说明
  - 后续动作：标为 compile-only，默认关闭回归注册

- `D-COMPILE-ONLY-STAGE`
  - 触发：阶段性先保留代码与编译能力，后续再补运行验证
  - 最小证据：编译通过记录 + 阶段计划
  - 后续动作：标为 compile-only，记录下一阶段计划

### 2.4 BLOCK 类（当前禁止分层落位）

- `D-BLOCK-COMPILE`
  - 触发：编译未通过
  - 最小证据：编译错误输出
  - 后续动作：先修编译错误，不做分层

- `D-BLOCK-UNTSTD`
  - 触发：存在原因不明 `untested exception`
  - 最小证据：失败日志 + 未解释点
  - 后续动作：先完成归因，不做 default 判定

- `D-BLOCK-RULE`
  - 触发：规则未对齐
  - 最小证据：规则条款与当前行为冲突说明
  - 后续动作：先修语义或修测试点映射

- `D-BLOCK-EVIDENCE`
  - 触发：证据缺失（日志/统计/回填不完整）
  - 最小证据：缺失项清单
  - 后续动作：补齐证据后再裁决

- `D-BLOCK-RUN-NOT-ATTEMPTED`
  - 触发：该场景需要运行 gate，但本轮未执行单 case 运行
  - 最小证据：编译记录 + 运行缺失说明
  - 后续动作：补跑单 case 或调整为合法的 `compile-only` 场景

- `D-BLOCK-RUN-UNEXPLAINED`
  - 触发：已运行，但失败结果不可归因（无法解释）
  - 最小证据：运行日志 + 未解释点
  - 后续动作：先完成归因，再继续分层

- `D-BLOCK-REGISTER`
  - 触发：分层与 `test_register.c` 状态不一致
  - 最小证据：当前注册状态与目标分层对照
  - 后续动作：修正注册状态再提交

## 3. 使用约束

- 每个 case 只保留一个主原因码。
- 若有次要原因，可在备注写 secondary，不新增主码。
- 禁止自造原因码；如需新增，先扩展本目录。

## 4. 交付落地点

- 自动裁决结果：`references/tiering_decision.md` 输出中记录原因码。
- 提交前核对：`references/submission_card.md` 勾选“原因码已记录且来自目录”。
- 最终摘要：在结论段写明原因码和对应证据。
