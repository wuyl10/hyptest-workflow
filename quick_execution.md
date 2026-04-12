# HYPTEST 快速执行版（保质量）

本文是加速执行入口，不是规则简化版。所有质量判定仍以 `rules_and_pitfalls.md`、`writing_cases.md`、`build_run_debug.md` 为准。

## 0. 使用原则

- 目标：减少路径切换成本，不减少质量检查项。
- 方法：把完整流程压缩成 8 步，每步都设硬门禁。
- 约束：任何门禁不通过，立即转详细文档排查，不得跳步。

Gate 对照（便于与 `quality_gate.md` 对齐）：

- Gate-0 -> Gate A（输入清晰度）
- Gate-1 -> Gate B（代码结构完整性）
- Gate-2 -> Gate C（编译通过）
- Gate-3 -> Gate D（运行可解释）
- Gate-4 -> Gate E（语义一致性）
- Gate-5 -> Gate F（分层与注册一致）
- Gate-6 -> Gate G（回填闭环完整）
- Gate-7 -> Gate H（交付证据完整）

## 1. 输入锁定（Gate-0）

必须先明确：

- 仓库来源（https://github.com/wuyl10/riscv-hyp-tests-nhv5.git）
- 当前分支（`nhv5.1`）
- 测试点文件与条目
- case 名
- 平台（通常 `spike`）
- 分层目标（default/manual/compile-only）
- 是否命中 `test_point/ai_exclude_*.txt` 或 `test_point/human_exclude_*.list`

通过标准：

- 关键输入项都明确且可追踪。
- 仓库与分支检查通过。
- 若命中排除清单：目标分层不设为 default，且原因可追溯。

不通过动作：

- 回到 `SKILL.md` 的输入检查清单补全。

建议检查命令：

```bash
git remote -v
git branch --show-current
rg -n "^<case_name>$" test_point/ai_exclude_*.txt test_point/human_exclude_*.list
```

## 2. 用例落地（Gate-1）

执行：

1. 从 `templates/new_case_template.c` 起步。
2. 在 `ai_test_cases/` 写或改 case。
3. 保证单函数仅一个 `TEST_END(...)`。

通过标准：

- 代码结构符合 `writing_cases.md`。
- 断言至少覆盖两类：异常/地址/数据/边界之一。

不通过动作：

- 回到 `writing_cases.md` 补齐断言与结构。

## 3. 单点编译（Gate-2）

执行：

```bash
python3 compile_elf.py --plat spike --name <case_name>
```

通过标准：

- 对应 ELF 生成成功。

不通过动作：

- 只修编译问题，不进入运行阶段。

## 4. 单点运行（Gate-3）

执行：

```bash
python3 get_result.py --platform spike --case <case_name>
```

通过标准：

- 结果可解释（通过或可归因失败）。

不通过动作：

- 先按 `build_run_debug.md` 的失败类型映射定位。

`compile-only` 特例：

- 若目标分层已明确为 `compile-only`，可跳过 Gate-3，并在最终结论标注“Gate-3=N/A(compile-only)”及不运行原因。

## 5. 语义裁决（Gate-4）

执行：

- 对照 `rules_and_pitfalls.md` 判定语义是否一致。

通过标准：

- 语义与项目规则一致，或已明确不作为 Spike gate。

不通过动作：

- 不强行进 default，降级到 manual/compile-only 并注明原因。

## 6. 分层落位（Gate-5）

执行：

- 决定 case 属于 default/manual/compile-only。
- 调整 `test_register.c` 注册状态。

判定建议：

- `manual`：已运行且结果可归因，但 Spike 不稳定或该场景不宜作为 gate。
- `compile-only`：本轮仅保编译，不执行运行 gate。

通过标准：

- 分层与注册状态一致。

不通过动作：

- 先修分层/注册不一致，再继续。

## 7. 回填闭环（Gate-6）

执行：

- 更新测试点映射与状态标注。

建议标注：

- `(case_name)`
- `(case_name, manual)`
- `(case_name, compile-only)`
- `(case_name, 依赖PMA CSR/TLB一致性/cache一致性, 未跑Spike)`
- 若命中排除清单，备注中附命中清单名与 `reason_code`

通过标准：

- 映射可追踪，原因写清楚。

## 8. 证据交付（Gate-7）

最小交付内容：

- 改动文件列表
- case 列表
- 编译结果
- 运行结果
- 日志路径
- 分层结论（`decision_prelim` / `decision_final`）与依据
- `reason_code`
- 排除清单命中情况（若命中）

通过标准：

- 任意结论都能回溯到日志与规则依据。

提交前动作：

- 用 `submission_card.md` 完成最终勾选；任一关键项未勾选不得提交。

## 快速执行不降质的三条红线

- 不允许跳过单 case 编译直接做分层；运行仅在 `compile-only` 场景可按规则标记为 `N/A`。
- 不允许用“编译通过”替代语义验证。
- 不允许在语义不确定时强行放入 default。

## 一条命令的最短闭环（仅在已满足 Gate-0/1 时）

```bash
python3 compile_elf.py --plat spike --name <case_name> && \
python3 get_result.py --platform spike --case <case_name>
```

说明：该命令只是执行加速，不包含规则裁决；裁决必须继续执行 Gate-4 至 Gate-7。
