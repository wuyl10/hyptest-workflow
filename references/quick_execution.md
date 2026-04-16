# HYPTEST 快速执行版（保质量）

本文是加速执行入口，不是规则简化版。所有质量判定仍以 `references/rules_and_pitfalls.md`、`references/writing_cases.md`、`references/build_run_debug.md` 为准。

## 0. 使用原则

- 目标：减少路径切换成本，不减少质量检查项。
- 方法：把完整流程压缩成 8 步，每步都设硬门禁。
- 约束：任何门禁不通过，立即转详细文档排查，不得跳步。

Gate 对照（便于与 `references/quality_gate.md` 对齐）：

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

通过标准：

- 关键输入项都明确且可追踪。
- 仓库与分支检查通过。

不通过动作：

- 回到 `SKILL.md` 的输入检查清单补全。

建议检查命令：

```bash
git remote -v
git branch --show-current
```

## 2. 用例落地（Gate-1）

执行：

1. 先检索 2~5 个相似存量 case，优先复用已有写法中的结构、断言和环境构造。
   如果测试点描述较长、分支较多，优先让脚本先生成 reading pack，再由模型抽象哪些结构值得学、哪些不能照搬。
2. 需要骨架时，再从 `assets/templates/new_case_template.c` 起步；若测试点变化较大，直接按 `references/writing_cases.md` 的结构与断言原则自行展开，不要被模板形状反向限制。
3. 在 `ai_test_cases/` 写或改 case。
4. 保证单函数仅一个 `TEST_END(...)`。

建议命令：

```bash
python3 scripts/find_similar_cases.py \
  --repo-root <repo_root> \
  --from-file <test_point_file> \
  --query cross_16b --query retry --query access_fault \
  --show-snippet \
  --limit 5
```

更适合大模型阅读的检索方式：

```bash
python3 scripts/find_similar_cases.py \
  --repo-root <repo_root> \
  --from-file <test_point_file> \
  --query cross_16b --query retry --query access_fault \
  --assert-only \
  --emit-reading-pack \
  --limit 3
```

通过标准：

- 代码结构符合 `references/writing_cases.md`。
- 断言至少覆盖两类：异常/地址/数据/边界之一。
- 已查看相似存量 case，并明确哪些写法可复用、哪些不能直接照搬。
- 若命中的是薄 wrapper case，已继续查看脚本给出的 related helper 片段，而不是只看 wrapper 壳函数。
- 若使用 reading pack，已从中提炼出“结构/断言/环境顺序”三类可复用点，而不是把整段实现原样搬过去。

不通过动作：

- 回到 `references/writing_cases.md` 补齐断言与结构，或重新检索更接近目标测试点的存量 case。

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

- 先按 `references/build_run_debug.md` 的失败类型映射定位。

`compile-only` 特例：

- 若目标分层已明确为 `compile-only`，可跳过 Gate-3，并在最终结论标注“Gate-3=N/A(compile-only)”及不运行原因。

## 5. 语义裁决（Gate-4）

执行：

- 对照 `references/rules_and_pitfalls.md` 判定语义是否一致。

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
- 回填后，执行一次轻量格式检查脚本。

建议标注：

- `case_name`
- `case_name（default，已启用）`
- `case_name（已注释，manual）`
- `case_name（compile-only，未跑Spike）`
- `case_name（依赖PMA CSR/TLB一致性/cache一致性，未跑Spike）`

补充约束：

- `test_point` 里只回填映射与短状态，不追加 `## ...workflow 回填`、`[质量门禁结果]`、`[分层结论]` 等后半段证据块。

建议命令：

```bash
python3 scripts/check_writeback_format.py \
  --repo-root <repo_root> \
  --file <test_point_file> \
  --check-register
```

通过标准：

- 映射可追踪，原因写清楚。

## 8. 证据交付（Gate-7）

最小交付内容：

- 改动文件列表
- case 列表（默认只列 `case_name`；必要时附短状态）
- 编译结果
- 运行结果
- 日志路径
- 若有非 pass Gate：列出对应 Gate 与问题
- 若最终不是 `default`：分层结论（`decision_prelim` / `decision_final`）与依据
- 若最终不是 `default`：`reason_code`

补充说明：

- 上述内容属于最终交付摘要，不属于 `test_point` 回填块。

通过标准：

- 任意结论都能回溯到日志与规则依据。

提交前动作：

- 用 `references/submission_card.md` 完成最终勾选；任一关键项未勾选不得提交。

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
