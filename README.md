# hyptest-workflow

`hyptest-workflow` 用于 `riscv-hyp-tests-nhv5` 仓库里的 hyptest 落地闭环：从 `test_point` 分析、到 `ai_test_cases/*.c` 写 case、到 `test_register.c` 注册、到编译/运行/日志归因、再到 `default` / `manual` / `compile-only` 决策与 `test_point` 回填。

这份 README 面向“怎么调用这个 skill”。真正执行时，仍以 `SKILL.md` 为权威规则源；如果 README 和 `SKILL.md` 有冲突，以 `SKILL.md` 为准。

## 它适合做什么

- 根据 `test_point/*` 新增 1~3 个 hyptest case
- 修改或新增 `ai_test_cases/*.c`
- 调整 `test_register.c` 注册状态
- 单 case 编译、单 case 跑 Spike、定位失败日志
- 判断 case 应进入 `default` / `manual` / `compile-only`
- 把结果按项目约定轻量回填到 `test_point`

## 推荐先这样用

如果你平时是直接给 Codex / agent 下任务，默认先用这个短版 prompt。它更符合当前 skill 的“轻量回填 + 按需展开”口径。

```text
使用hyptest-workflow skill

repo_root: <repo_root>
test_point_file: <test_point_file>
platform: spike
spike_bin: <spike_bin>
task_mode: new-case-only
new_case_count: 1-3
target_policy: default-first

要求：
- 先分析目标模块和 test_point，再新增 1-3 个 ai_* case
- 必须先写 case，再编译/运行
- 非 compile-only 必须单 case 跑 spike
- 回填 test_point，并与 test_register.c 一致
- 输出新增 case、唯一性证据、编译/运行结果、关键日志路径和最终决策
```

适用场景：

- 默认新增 1~3 个 case
- 希望 `test_point` 保持轻量回填
- 只想拿到必要交付摘要，不想每次都显式展开所有字段

## 完整版 Prompt

如果你希望任务一开始就显式带上更多约束和交付项，再用完整版 prompt。

```text
使用hyptest-workflow skill

repo_root: <repo_root>
test_point_file: <test_point_file>
batch_size: 1-3
platform: spike
spike_bin: <spike_bin>
target_policy: default-first
allow_fallback: yes

task_mode: new-case-only
new_case_count: 1-3
new_case_naming: ai_*

execution_constraints:
- 严格按 skill 文档口径优先级执行
- 必须先新增 1-3 个 case 到 ai_test_cases/*.c，再做编译/运行
- 禁止把“仅启用注释中的已有 case”当作完成
- 禁止把“仅重跑已有 case”当作完成
- 非 compile-only 必须单 case 跑 spike
- compile-only 可 Gate D=N/A，但必须写不运行原因
- 回填 test_point，并保证与 test_register.c 一致

delivery_requirements:
- 去看目标 RTL / 模块实现里可疑的 bug 点，并补充到 test_point_file
- 用例要构造到对应测试场景，能跑到该 bug 问题
- 明确“新增 case 名称 + 所在文件 + 函数签名”
- 提供“唯一性检索证据”
- Gate A-H
- decision_prelim / decision_final
- reason_code
- 编译/运行统计
- 关键日志路径
- 修改文件清单
- 回填结果与 test_register.c 一致性
```

这个模板适合大多数“从测试点出发，新增 case 并闭环验证”的任务。

补充说明：

- `delivery_requirements` 默认指最终交付摘要，不是 `test_point` 里的追加尾块。
- 即使你要求 `Gate A-H`、`decision_prelim` / `decision_final`、`reason_code`，skill 也会优先把这些内容放在最终交付摘要，而不是写进 `test_point`。

## 这些字段分别是做什么的

- `repo_root`
  - hyptest 仓库根目录。skill 会以这里为主工作区。
- `test_point_file`
  - 当前要分析和回填的测试点文件。
- `batch_size`
  - 本轮建议处理的 case 数量。常见值就是 `1-3`，便于快速定位和单点验证。
- `platform`
  - 目标编译/运行平台。常见是 `spike`；如果只是编译，也可切换到别的平台口径。
- `spike_bin`
  - Spike 可执行文件路径。只有需要跑 Spike 时才会用到。
- `target_policy`
  - 常见为 `default-first`，表示优先争取 `default` 准入，不行再退到 `manual` 或 `compile-only`。
- `allow_fallback`
  - 允许在证据不足或平台限制下，从 `default` 回退到更保守结论。
- `task_mode`
  - 常见为 `new-case-only`，表示这轮目标是新增 case，不是只复用或只重跑已有 case。
- `new_case_count`
  - 本轮期望新增多少个 case。
- `new_case_naming`
  - 新 case 的命名前缀约束，常见是 `ai_*`。

## 推荐的执行约束

你这类任务里，下面这些约束很关键，建议保留：

- 必须先新增 case，再做编译/运行。
- 不允许把“只是打开已有注释注册”当成完成。
- 不允许把“只是重跑旧 case”当成完成。
- 只要不是 `compile-only`，就应该单 case 跑 Spike。
- 如果是 `compile-only`，必须明确写出为什么不跑，以及 Gate D=`N/A`。
- 回填 `test_point` 时，必须和 `test_register.c` 当前状态一致。

## 推荐的交付内容

如果你希望 agent 的最终交付物比较完整，常见要求包括：

- 新增 case 的名称、所在文件、函数签名
- 唯一性检索证据，例如 `rg` 未命中旧定义
- Gate A-H
- `decision_prelim`
- `decision_final`
- `reason_code`
- 编译/运行统计
- 关键日志路径
- 修改文件清单
- 回填结果和 `test_register.c` 的一致性说明

这些内容默认属于最终交付摘要，不属于 `test_point` 的轻量回填部分。

如果任务特别强调“从 RTL / 模块实现反推测试点”，也可以像你常用 prompt 那样，明确要求：

- 先看目标模块实现
- 抽取一个可疑 bug 点
- 把怀疑点补进 `test_point_file`
- 用新增 case 精确构造出对应触发场景

## 当前默认口径

虽然你常用 prompt 里有时会要求完整交付，但这个 skill 当前的默认输出已经更偏“轻量化”。如果任务里没有显式要求，默认按下面口径执行：

- `test_point` 只回填正文和 `已实现 case`
- `已实现 case` 默认只写 `case_name`，必要时可补短状态，例如 `（default，已启用）`、`（已注释，manual）`
- 默认不输出 `exclude_check`
- 默认不在 `test_point` 追加审计式尾块，例如 `[新增 case]`、`[质量门禁结果]`、`[分层结论]`
- `[质量门禁结果]` 只有存在非 pass Gate，或任务显式要求时，才在最终交付摘要里写
- `decision_prelim` / `decision_final` / `reason_code` 只有最终不是 `default`，或任务显式要求时，才在最终交付摘要里写

也就是说：你的 prompt 可以写得很完整，但 skill 本身已经支持“默认简写、按需展开”。

## 关键文件

- `SKILL.md`
  - 真正规则入口，定义执行优先级、强约束、默认行为和工作流。
- `agents/openai.yaml`
  - skill 的基础元信息和入口描述。
- `references/writing_cases.md`
  - case 编写规范、断言覆盖、回填模板、反模式。
- `references/quick_execution.md`
  - 常见执行路径和快速入口。
- `references/build_run_debug.md`
  - 编译、运行和日志定位方法。
- `references/quality_gate.md`
  - Gate A-H 的判定规则。
- `references/tiering_decision.md`
  - `default` / `manual` / `compile-only` 决策逻辑。
- `references/reason_code_catalog.md`
  - `reason_code` 的标准口径。
- `scripts/find_similar_cases.py`
  - 用于在存量 case 中找最相近的参考样本。
- `scripts/check_writeback_format.py`
  - 用于检查 `test_point` 轻量回填格式和注册一致性。
- `scripts/eval_check_writeback_format.py`
  - 用于回归检查写回校验逻辑，避免后续修改把状态格式或注册解析改坏。
- `scripts/eval_find_similar_cases.py`
  - 用于回归检查相似 case 检索逻辑，避免后续修改把排序、状态判定或 markdown section 选择改坏。

## 使用建议

- 想新增 case 时，优先把目标说具体：模块、测试点文件、平台、期望新增数量、是否必须跑 Spike。
- 想让结论更稳定时，把 `execution_constraints` 和 `delivery_requirements` 明确写出来。
- 想让回填更简洁时，不必重复写大段格式要求；skill 已内置轻量回填默认值。
- 想让 case 写得更像仓库原生风格时，直接给 `test_point_file` 和目标场景，skill 会优先学习存量 case，而不是死套模板。

## 目录结构

```text
hyptest-workflow/
├── SKILL.md
├── README.md
├── agents/
│   └── openai.yaml
├── references/
├── scripts/
└── assets/
```
