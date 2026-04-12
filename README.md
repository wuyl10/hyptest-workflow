# hyptest-workflow skill 包使用说明

## 适用仓库与分支

- 仓库地址：https://github.com/wuyl10/riscv-hyp-tests-nhv5.git
- 使用范围：该仓库的 `nhv5.1` 分支工作目录

只要当前工作目录来自上述仓库且分支为 `nhv5.1`，本 skill 可直接使用。

## 文件结构

- `SKILL.md`: 技能入口、触发场景、总体流程
- `quick_execution.md`: 快速执行版（保质量）
- `quality_gate.md`: 质量门禁清单（统一验收标准）
- `tiering_decision.md`: 自动分层裁决规则（统一结论口径）
- `reason_code_catalog.md`: 原因码目录（统一追溯口径）
- `submission_card.md`: 一页提交核对卡（提交前勾选）
- `writing_cases.md`: 用例编写规范
- `build_run_debug.md`: 编译、运行、调试命令
- `rules_and_pitfalls.md`: 规则边界与已知坑点
- `templates/new_case_template.c`: 可直接复制的 case 骨架

## 快速开始

1. 先读 `SKILL.md` 了解分层策略（default/manual/compile-only）。
2. 选择执行模式：快速执行优先看 `quick_execution.md`，复杂问题走完整执行版。
3. 按 `writing_cases.md` 在 `ai_test_cases/` 新建或修改 case。
4. 先核对 `test_point/ai_exclude_*.txt` 与 `test_point/human_exclude_*.list` 是否命中目标 case。
5. 用 `build_run_debug.md` 的命令做单 case 编译；非 `compile-only` 再做单 case 运行。
6. 依据 `rules_and_pitfalls.md` 判断是否进入 default。
7. 用 `quality_gate.md` 做最终验收。
8. 用 `tiering_decision.md` 生成分层结论与原因码。
9. 用 `submission_card.md` 做提交前勾选确认。
10. 更新 `test_register.c` 与 `test_point` 映射，完成闭环。

## 推荐阅读顺序（避免漏细节）

1. `SKILL.md`
2. `quick_execution.md`
3. `quality_gate.md`
4. `tiering_decision.md`
5. `reason_code_catalog.md`
6. `submission_card.md`
7. `rules_and_pitfalls.md`
8. `writing_cases.md`
9. `build_run_debug.md`
10. `templates/new_case_template.c`

说明：

- 先读规则再写代码，能显著降低“写完后整体返工”。
- 模板用于起步，不替代规则文档里的边界约束。
- 快速执行版用于提速，质量门禁用于兜底，二者必须同时使用。
- 若文档表述冲突，优先按 `Manual_Reference.md` 与 `quality_gate.md` 执行，`CRITICAL_ISSUES_LOG.md` 主要用于历史线索。

## 最小闭环（一次完整落地）

1. 从 `test_point/*` 选定一个条目并定义 case 名。
2. 在 `ai_test_cases/` 写用例，先保证可编译。
3. 用 `compile_elf.py --name <case>` 做单点编译。
4. 非 `compile-only`：用 `get_result.py --case <case>` 做单点运行；`compile-only`：在结论中标注 Gate D=`N/A` 与不运行原因。
5. 根据运行日志（或 Gate D=`N/A` 的原因说明）判定 default/manual/compile-only。
6. 回填测试点映射并更新注册状态。

## 失败时看哪里

- 断言不符合预期：先看 `writing_cases.md` 的异常与断言章节。
- `untested exception`：先看 `build_run_debug.md` 的失败分叉建议。
- 语义冲突（尤其 PMA/PBMT/TLB/cache）：先看 `rules_and_pitfalls.md` 的硬规则与非对齐口径。
