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
  - 触发：场景不宜以 Spike 作为 gate（常见于 PMA/TLB/cache 依赖）
  - 最小证据：规则引用 + 场景说明 + 运行/环境限制说明
  - 后续动作：标为 manual，回填原因

- `D-MANUAL-UNSTABLE`
  - 触发：语义可解释，但 Spike 运行不稳定
  - 最小证据：多次运行差异、失败日志、规则一致性说明
  - 后续动作：标为 manual，补充稳定性观察计划

- `D-MANUAL-RTL-ONLY`
  - 触发：语义面向 RTL 现象，当前仿真平台无法完整验证
  - 最小证据：场景说明 + 平台限制说明
  - 后续动作：标为 manual，等待 RTL 环境验证

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

- 自动裁决结果：`tiering_decision.md` 输出中记录原因码。
- 提交前核对：`submission_card.md` 勾选“原因码已记录且来自目录”。
- 最终摘要：在结论段写明原因码和对应证据。
