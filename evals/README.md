# hyptest-workflow Evals

本目录放 `hyptest-workflow` skill 的 **真实任务 prompt eval 集**，按 `skill-creator`/`references/schemas.md` 的 `evals.json` schema 维护。

和 `scripts/eval_*.py` 的区别：

- `scripts/eval_*.py` 是**脚本代码的单元/集成测试**（固定输入 → 固定输出）
- `evals/evals.json` 是**用 skill 完成真实任务**的端到端 eval，用于 `skill-creator` 的 benchmark 循环（with-skill vs without-skill 对比）

## 当前 eval 集

| id | name | 覆盖场景 |
| --- | --- | --- |
| 1 | `new-case-memblock-cross16b-boundary` | 新增测试点 + 新 case（memblock 场景，store side effect 检查）|
| 2 | `supplement-existing-p6b-assert` | 补已有 `### PnX` 条目（supplement 模式）|
| 3 | `bug-hunt-storequeue-uncovered-neighbor` | bug hunt + 源码阅读 + profile §5 + 现有 test_point 覆盖空隙 |

每个 eval 含 12-16 条 expectations，可被 grader 机器验证（grep/ls/python 脚本）或人工判断（`human`）。

## 怎么跑

按 skill-creator 手册：

1. 对每个 eval，spawn 两个 subagent（with-skill / without-skill），同一 prompt
2. 输出存到 `../hyptest-workflow-workspace/iteration-N/eval-<id>/{with_skill,without_skill}/outputs/`
3. 跑 grader 评每条 expectation → `grading.json`
4. aggregate 成 `benchmark.json`
5. 打开 eval-viewer 对比两边

目前本 skill 主要在单人/小团队使用，未跑过正式 benchmark 循环；当 skill 结构性调整或需要向外发布时再跑。

## 维护约束

- 改动 SKILL.md 的触发条件（`description` 或 Non-Negotiables）时，应同步检查 eval prompt 是否仍覆盖这些触发路径
- expectations 里涉及的文件名、宏名（`CAUSE_*` / `TEST_*`）、`references/spec_profiles/*` 路径应和 skill 当前实际情况一致
- 新增 eval 时保持 `id` 唯一递增；可参考已有 3 个 eval 的 expectations 粒度
