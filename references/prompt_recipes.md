# Prompt Recipes

本文放 `hyptest-workflow` 的可复制 prompt 模板。README 只保留快速入口；完整模板放这里，避免 README 过长。

## 路径写法

`repo_root` 是 workflow 输入，不是 hyptest 平台环境变量。共享文档里建议写成占位符，使用时替换为实际仓库根目录：

```text
repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
```

如果当前 shell 或团队环境已经有仓库路径变量，可以直接写：

```text
repo_root: $REPO_ROOT
test_point_file: test_point/<xxx>.md
```

仓库路径变量只是个人或团队便利别名，不要求 hyptest 仓库必须提供。脚本入口会展开 `$VAR` 路径，所以 request 文件或命令里可以用团队已有变量名。`SPIKE_BIN`、`LINKNAN_HOME`、`DIFFTEST_REF_SO`、`CROSS_COMPILE` 仍按 hyptest 仓库的编译/运行环境说明设置，这里不复制配置说明。

如果 `test_point_file` 写相对路径，按 `repo_root` 下的路径理解；如果写绝对路径，也可以使用 `$REPO_ROOT/test_point/<file>.md`。不要在共享文档里写个人绝对路径。

## 高质量默认 Prompt

适合正式新增 case，质量最稳：

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
coverage_scope: repo

要求：
- 先分析目标模块和 test_point；test_point_file 只当容器，按 `### PnX` 条目处理
- 先做全仓 test_point 覆盖检查、repo 级 case 相似检索、函数名唯一性检查
- 写 case 前确认 spec_profile、Spike gate 适用性和模型边界
- 如需命名建议，可先用 suggest_case_name；如需骨架，可用 make_case_skeleton，但不能把骨架当完成 case
- 新增 1 个 ai_* case，更新 test_register.c
- 非 compile-only 必须单 case 编译并单 case 跑 spike
- 回填 test_point，并与 test_register.c 一致
- 输出新增 case、唯一性证据、编译/运行结果、关键日志路径、test_point 回填状态和最终决策
```

## 更快 Prompt

适合希望缩短单 case 生成时间，但不降低质量：

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
coverage_scope: repo

提速要求：
- 优先使用 case_preflight_pack.py 聚合输入、profile、repo evidence index、相似 case reading pack
- 用 suggest_case_name.py 生成候选名并检查同名/相似名
- 如需要 skeleton，用 make_case_skeleton.py 生成保守骨架，再按 test_point 和相似 case 填断言
- 写完后用 case_gate_pack.py 完成单 case 编译、运行、postcheck 和本轮日志定位
- 用 make_case_submission_card.py --emit-final-draft 整理交付草稿
- 用 case_workflow_ledger.py 记录耗时和返工信号

质量要求：
- 不跳过 spec_profile、repo 级去重、单 case 编译/运行、回填/注册一致性
- 不把 skeleton、命名建议、submission draft 或 ledger 当作分层结论
```

## 按模块找 suspected bug Prompt

适合用户不是指定某个旧 `### PnX`，而是要求“继续围绕某个模块找 bug 点，并新增 case”。这个模板比默认新增 case 更明确：它要求先分析目标模块源码和当前 test_point，不能把已有条目或已有 case 当成本轮新增结果。

### 高质量版

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<module>_suspected_bug_corner_points_<n>.md
platform: spike
spec_profile: <spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
coverage_scope: repo
target_module: <module>

目标：
- 继续围绕 <module> 找 1 个高价值 suspected bug corner point，并新增 1 个对应 ai_* case
- 当前 test_point_file 只当容器，文件里已有 `### PnX` 和“已实现 case”不能重复当成本轮新增结果
- 优先从 <bug_hunt_focus> 等共享路径里找未覆盖的边界
- 不要按模块目录做局部捷径；必须做 repo 级 test_point 覆盖检查和 repo 级 case 去重

执行要求：
- 先分析目标模块源码、当前 test_point 文件、已有“已实现 case”映射和 test_register.c 状态
- 新增测试点前，扫描全仓 test_point/*.md，证明类似测试点未覆盖
- 写 case 前，搜索全仓 ai_test_cases/*.c 和 manual_test_cases/**/*.c，读取 2-5 个相似 case 作为实现参考
- 同时做精确函数名唯一性检查，不能只凭相似检索未命中
- 写 case 前确认 spec_profile、Spike gate 适用性和模型边界
- 新增 1 个新的 `### PnX` 测试点条目，不复用旧条目
- 新增 1 个新的 ai_* case，默认放 ai_test_cases 中主题合适的位置；如果已有文件过大或主题不合适，可以新建主题明确的新文件
- case 必须有可观测断言：数据值、marker progress、guard 不变、异常状态、side effect 边界等按场景选择
- 如检查 excpt.*，必须先 TEST_SETUP_EXCEPT()
- 一个 case 函数只能有一个 TEST_END(...)
- 更新 test_register.c，并保证 default/manual/compile-only 状态与注册状态一致
- 单 case 编译目标平台；非 compile-only 必须单 case 运行目标平台
- 回填 test_point，只在新条目的“已实现 case”下轻量写 case 映射，不追加审计式块
- 回填后检查 test_point 与 test_register.c 一致性

输出要求：
- 实际使用的 spec_profile
- 新增测试点编号和标题
- 新增 case 名与文件路径
- 唯一性证据：repo 级 test_point 覆盖检查、repo 级相似 case 检索 top results、函数名精确唯一性检查
- 编译命令、编译结果、ELF/ASM 路径
- 运行命令、运行结果、关键日志路径
- test_point 回填位置和 test_register.c 注册状态
- 最终决策：default/manual/compile-only/blocked；如果不是 default，给出 reason_code
- 如果扫描后没有发现新的高价值 bug 点，明确说明“未发现新的测试点 / 未新增 case”，不要把旧条目或旧 case 当作新增结果
```

### 更快版

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<module>_suspected_bug_corner_points_<n>.md
platform: spike
spec_profile: <spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
coverage_scope: repo
target_module: <module>

目标：
- 快速但不降质量地继续找 1 个 <module> 高价值 suspected bug corner point
- 新增 1 个新的 `### PnX` 条目和 1 个对应 ai_* case
- 不重复当前文件已实现条目，不把旧条目或旧 case 当新增结果

提速流程：
- 先用 case_preflight_pack.py 聚合任务输入、profile、repo snapshot、repo evidence index、环境检查、相似 case reading pack 和目标 test_point 摘要
- preflight query 至少覆盖：<bug_hunt_focus_terms>
- 用 repo_evidence_index.py 复用全仓 case/test_point/register 索引缓存，但不能缩小到模块局部范围
- 用 suggest_case_name.py 生成候选 case 名并检查同名/相似名
- 如需要 skeleton，用 make_case_skeleton.py 生成保守骨架，再根据 test_point 和相似 case 填完整断言；不能把 skeleton 当完成 case
- 写完 case 后用 case_gate_pack.py 完成单 case 编译、非 compile-only 单 case 运行、postcheck、本轮日志定位和失败日志自动分类
- 用 make_case_submission_card.py --emit-final-draft 汇总交付草稿
- 用 case_workflow_ledger.py 记录耗时和返工信号

质量要求：
- 不跳过 spec_profile
- 不跳过 repo 级 test_point 覆盖检查
- 不跳过 repo 级 case 相似检索
- 不跳过函数名精确唯一性检查
- 不跳过单 case 编译
- 非 compile-only 不跳过单 case 运行目标平台
- 不跳过 test_point 回填与 test_register.c 一致性检查
- 不把 preflight、skeleton、命名建议、submission draft 或 ledger 当作分层结论

输出要求：
- 新增测试点编号和新增 case 名
- preflight / gate / postcheck / submission card / ledger 的报告路径
- 唯一性证据：test_point 覆盖检查范围和结论、相似 case top results、函数名唯一性结论
- 编译结果、运行结果、关键日志路径
- test_point 回填状态与 test_register.c 注册状态
- 最终决策：default/manual/compile-only/blocked；如果不是 default，给 reason_code
- 如果未找到新的高价值 bug 点，明确说明未新增，不硬凑 case
```

### memblock 示例填法

```text
test_point_file: test_point/memblock_suspected_bug_corner_points_11.md
target_module: memblock
bug_hunt_focus: MemBlock / StoreQueue / sbuffer flush owner / CMO / LRSC / fence / vector/VSegment / TLB/cache/refill/replay
bug_hunt_focus_terms: memblock, StoreQueue, sbuffer, cmo, cbo.inval, fence, lrsc, vector, vsegment, owner, marker
```

## 只读预检 Prompt

适合先判断有没有新增空间、准备任务或会议演示：

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <spec_profile>

task_mode: run-only
coverage_scope: repo

要求：
- 只做只读分析，不修改文件
- 跑 case_preflight_pack.py，必要时跑 repo_evidence_index.py 和 find_similar_cases.py
- 输出目标 test_point 摘要、相似测试点/相似 case、profile/Spike gate 注意点
- 给出是否值得新增 case 的建议，但不新增 case、不注册、不编译、不运行
```

## 补已有测试点 Prompt

适合用户明确指定了旧条目，例如“继续补 P6B”：

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <spec_profile>

task_mode: supplement-existing-point
target_test_point: "### P<id>. <title>"
new_case_count: 1
coverage_scope: file
target_policy: default-first

要求：
- 只围绕指定 `### P<id>` 补 case，不新增无关测试点
- 仍做 repo 级 case 相似检索和函数名唯一性检查
- 新增/修改 case 后单 case 编译，非 compile-only 单 case 运行
- 只在该条目的 `已实现 case` 下轻量回填，并检查 test_register.c 一致性
```

## 只跑验证 Prompt

适合已有 case，只想拿编译/运行证据：

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
platform: spike
spec_profile: <spec_profile>

task_mode: run-only
case_name: <case_name>

要求：
- 不修改源码、不修改 test_point、不修改 test_register.c
- 单 case 编译并运行 spike
- 输出编译结果、运行结果、关键日志路径、失败时的候选原因
```

## 反例

- 只写“帮我补几个 case”，不写 `test_point_file`、平台、profile。
- 默认要求 `new_case_count: 1-3`，但没有说明每个 case 的覆盖差异。
- 只要求“编译通过”，没有要求非 compile-only 单跑。
- 要求“全量编译/全量跑”作为单 case 默认流程，会明显拖慢。
- 把 `test_point_file` 当成一个测试点，不指定 `### PnX` 或新增/补旧模式。
- 要求把大量审计证据写回 `test_point`，会污染文档；证据应放最终摘要和报告文件。
