# HYPTEST 一页提交核对卡

用途：把快速执行流程和质量门禁合并为一张可勾选清单，用于提交前最后确认。

## A. 输入锁定

- [ ] 测试点文件与条目明确
- [ ] case 名唯一且可追踪
- [ ] 平台明确（通常 `spike`）
- [ ] 目标分层明确（default/manual/compile-only）

## B. 用例结构

- [ ] 单函数仅一个 `TEST_END(...)`
- [ ] 只要该步骤检查 `excpt.*`，都已先调用 `TEST_SETUP_EXCEPT()` 初始化状态
- [ ] 断言至少覆盖两类：异常/地址/数据/边界
- [ ] store/amo/vector store 已检查 side effect（目标+邻接）

## C. 编译与运行

- [ ] 单 case 编译通过（已生成 ELF）
- [ ] 非 compile-only：单 case 运行完成
- [ ] 非 compile-only：结果可归因（pass/fail/untested）
- [ ] compile-only：已注明 Gate D=N/A 与不运行原因
- [ ] 非 compile-only：日志路径可回溯（`result_log/spike/*.log`）
- [ ] compile-only：Gate D=N/A 证据可回溯（不运行原因 + 分层依据/原因码）

## D. 语义与分层

- [ ] 与项目规则一致（`Manual_Reference.md` + `rules_and_pitfalls.md`）
- [ ] PMA/TLB/cache 依赖场景已正确标注
- [ ] 分层结论与 `test_register.c` 注册状态一致

## E. 回填与交付

- [ ] `test_point/*` 已回填 case 与状态
- [ ] 改动文件清单已整理
- [ ] 编译/运行统计已整理
- [ ] 分层结论与依据已整理

## F. 自动裁决

- [ ] 已按 `tiering_decision.md` 完成自动裁决
- [ ] 已记录 `decision_prelim`（default/manual/compile-only/blocked）
- [ ] 已记录 `decision_final`（default/manual/compile-only/blocked）
- [ ] 已记录 `reason_code`
- [ ] `reason_code` 已在 `reason_code_catalog.md` 中定义
- [ ] 若为 blocked，已给出修复动作与负责人

## 一票否决项

若命中任意一条，禁止进入 default：

- [ ] 语义未对齐项目规则
- [ ] `untested exception` 原因未查明
- [ ] PMA/TLB/cache 依赖场景未标注却尝试 default 放行
- [ ] 回填状态与注册状态不一致

## 提交签字区

- 执行人：
- 日期：
- 初裁结论（decision_prelim）：default / manual / compile-only / blocked
- 终裁结论（decision_final）：default / manual / compile-only / blocked
- 原因码：
- 备注（异常或降级原因）：
