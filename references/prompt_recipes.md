# Prompt Recipes

本文放 `hyptest-workflow` 的可复制 prompt 模板。README 只保留快速入口；完整模板放这里，避免 README 过长。

## 输入和环境变量

日常 prompt 优先写任务字段，不要把环境清单当成固定模板复制。规则是：当前进程能读到的 `HYPTEST_*` 变量可以省略；读不到、但本轮必需的变量才写进 prompt。prompt 显式写的值优先于 shell 环境，并会作为本轮脚本覆盖传入，例如 `--env HYPTEST_SPIKE_BIN=<path>`。

复制模板后必须替换所有尖括号占位符，例如 `<xxx>`、`<module>`。preflight 会把未替换占位符当成无效输入，而不是继续猜路径或 profile。

### 字段速查

| 字段 | 什么时候需要 | 含义 |
| --- | --- | --- |
| `HYPTEST_HOME` | 当前进程没有该变量，且本轮要读写/编译/运行 hyptest 仓库 | `riscv-hyp-tests` 仓库根目录；脚本 CLI 内部对应 `--repo-root` |
| `test_point_file` | 新增 case、补已有测试点、回填时必填 | 测试点容器文件；相对路径按 `HYPTEST_HOME` 下解析，绝对路径也可以 |
| `platform` | 需要编译、运行或判断平台 gate 时必填 | 常用 `spike` / `linknan` |
| `spec_profile` | 正式新增/分层建议显式填写 | 规格/平台口径；决定 Spike gate、模型边界和 default/manual/compile-only 判断 |
| `HYPTEST_SPIKE_BIN` | 本轮要跑 `platform: spike` gate，且当前进程读不到该变量 | community/upstream Spike 可执行文件；不要用 difftest 定制 Spike 替代 |
| `HYPTEST_LINKNAN_HOME` | 本轮要跑 LinkNan gate，或需要读 LinkNan/Nanhu 源码证据 | LinkNan 仓库根目录；Nanhu 源码从 `dependencies/nanhu/src/main` 推导 |
| `HYPTEST_DIFFTEST_REF_SO` | 本轮要跑 LinkNan / difftest gate | difftest ref so 路径 |
| `HYPTEST_TMPDIR` | `/tmp` 空间紧张或需要固定临时目录 | 临时目录；可指向个人可写目录 |

### 日常最短写法

如果环境已经设置好，prompt 里直接从任务字段开始：

```text
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>
```

如果当前进程看不到本轮必需变量，只补缺的变量。例如 spike-only gate 缺路径时：

```text
HYPTEST_HOME: <riscv-hyp-tests-nhv5.1 仓库根目录>
HYPTEST_SPIKE_BIN: <community/upstream Spike 可执行文件>
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>
```

围绕模块找 suspected bug 且需要读 Nanhu 源码时，只额外给 LinkNan 根目录；不需要单独给 Nanhu 路径：

```text
HYPTEST_LINKNAN_HOME: <LinkNan 仓库根目录>
test_point_file: test_point/<module>_suspected_bug_corner_points_<n>.md
platform: spike
spec_profile: <当前项目 spec_profile>
target_module: <module>
```

跑 LinkNan / difftest gate 时给 LinkNan 和 difftest-ref；`HYPTEST_SPIKE_BIN` 与本轮无关，可以省略：

```text
HYPTEST_LINKNAN_HOME: <LinkNan 仓库根目录>
HYPTEST_DIFFTEST_REF_SO: <riscv64-spike-so 路径>
platform: linknan
spec_profile: <当前项目 spec_profile>
```

### 识别不到时怎么提醒

preflight 不会用历史聊天或 PATH 猜关键路径。必需字段缺失时先停下并指出要补哪一项；与本轮平台无关的环境变量不会要求你补。

| 场景 | 处理方式 |
| --- | --- |
| 当前进程没有 `HYPTEST_HOME`，prompt 也没写 | 提醒补 `HYPTEST_HOME`，不继续做落地/运行 |
| prompt 写了 `$HYPTEST_HOME` / `$HYPTEST_SPIKE_BIN`，但当前进程展开不了 | 视为缺失，提醒写实际路径或让变量对 Codex/脚本可见 |
| `platform: spike` 且需要运行 gate，但没有 `HYPTEST_SPIKE_BIN` | 提醒补 community/upstream Spike 路径，不跑 spike gate |
| `platform: linknan` 且缺 `HYPTEST_LINKNAN_HOME` / `HYPTEST_DIFFTEST_REF_SO` | 提醒补缺失字段，不跑 linknan gate |
| `HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main` 不存在 | 提醒初始化 LinkNan 的 Nanhu submodule，或修正 `HYPTEST_LINKNAN_HOME` |

连续对话里，workflow 可以沿用前文理解任务意图，例如你前面刚指定了仓库、测试点文件和平台，后面说“继续新增 1 个用例”通常能被理解。但脚本 preflight 不读聊天历史；真正执行前仍以本轮 prompt、CLI 参数和当前进程环境为准。正式交付或让别人复跑时，建议写清 `test_point_file`、`platform`、`spec_profile` 和任务目标；路径变量只在当前环境不可见时补充。

## 规格/平台口径和覆盖范围

`spec_profile` 是“规格/平台口径”的名字，不是功能开关。它告诉 workflow 当前项目按哪套规则判断 Spike gate、PMA/PBMT/MMIO/cache/TLB/CBO 等模型边界，以及 case 是否能进入 `default`。不写时会使用 profile registry 的默认值；正式新增 case 或跨项目共享 prompt 时，建议显式填写。当前 `riscv-hyp-tests-nhv5.1` 常用示例是：

```text
spec_profile: nhv5_1_ap
```

如果以后切到其它项目或新增 profile，再把这里换成对应 profile 名。用户通常不需要填写 `coverage_scope`：新增测试点、继续找 suspected bug、跨文件排重时，workflow 自动做全仓 `test_point/*.md` 覆盖检查；补已有 `### PnX` 时，workflow 自动围绕当前条目/文件做局部测试点检查。case 相似检索始终是 repo 级。

## 模板怎么选

| 模板 | 适合场景 | 速度口径 |
| --- | --- | --- |
| `高质量默认 Prompt` | 正式新增 case，想稳妥覆盖全部质量门禁 | 默认推荐，质量最稳 |
| `轻量快速 Prompt` | 单次只新增 1 个 case，希望 wall-clock 尽量短 | 不强制跑报告/ledger，保留质量底线 |
| `自动化证据 Prompt` | 连续多 case、多人复盘、需要标准报告路径 | 优化证据标准化和返工成本，不承诺单次最快 |
| `只读预检 Prompt` | 先判断有没有新增空间或准备会议材料 | 只读，最快给方向 |

## 高质量默认 Prompt

适合正式新增 case，质量最稳：

```text
使用hyptest-workflow skill

test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first

要求：
- 先分析目标模块和 test_point；test_point_file 只当容器，按 `### PnX` 条目处理
- 根据任务目的选择覆盖范围；新增测试点默认先做全仓 test_point 覆盖检查
- 做 repo 级 case 相似检索、函数名唯一性检查
- 写 case 前确认规格/平台口径（spec_profile）、Spike gate 适用性和模型边界
- 如需命名建议，可先用 suggest_case_name；如需骨架，可用 make_case_skeleton，但不能把骨架当完成 case
- 新增 1 个 ai_* case，更新 test_register.c
- 非 compile-only 必须单 case 编译并单 case 跑 spike
- 回填 test_point，并与 test_register.c 一致
- 输出新增 case、唯一性证据、编译/运行结果、关键日志路径、test_point 回填状态和最终决策
```

## 轻量快速 Prompt

适合单次新增 1 个 case、希望实际完成时间尽量短，但不降低质量。这个模板不强制生成 submission card / ledger，也不强制所有辅助脚本都跑；它要求把时间花在必须的质量门禁上。

```text
使用hyptest-workflow skill

test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first

目标：
- 新增 1 个高价值测试点和 1 个对应 ai_* case
- 用最短可靠路径完成，不额外生成非必需报告

快速路径：
- 若输入和环境清楚，不跑完整 preflight pack；直接确认 spec_profile、platform、test_point_file 和任务模式
- 用 rg / find_similar_cases.py 做 repo 级 test_point 覆盖检查、case 相似检索和函数名精确唯一性检查
- 只读取实现所需的 2-5 个相似 case，不扩展到无关模块
- 命名明确时直接定名；只有命名不确定时才用 suggest_case_name.py
- 结构简单时直接写 case；只有框架结构不确定时才用 make_case_skeleton.py，且必须补完整断言
- 写完后优先单 case 编译和单 case 运行；case_gate_pack.py 可用于汇总，但不强制替代直接命令
- 默认不跑 make_case_submission_card.py 和 case_workflow_ledger.py，除非用户要求标准报告或复盘耗时

不可省略：
- 规格/平台口径（spec_profile）确认
- repo 级 test_point 覆盖检查
- repo 级 case 相似检索
- 函数名精确唯一性检查
- 单 case 编译
- 非 compile-only 单 case 运行目标平台
- test_point 回填与 test_register.c 一致性检查

输出要求：
- 新增测试点编号、case 名、文件路径
- 唯一性证据摘要
- 编译/运行结果和关键日志路径
- test_point 回填状态与 test_register.c 注册状态
- 最终决策；如果不是 default，给 reason_code
```

## 自动化证据 Prompt

适合连续新增多个 case、需要标准报告路径、需要复盘返工信号或多人协作的任务。它会减少证据遗漏和后续整理成本，但工具启动、索引和报告生成有固定开销；单次新增 1 个 case 时不一定比 `轻量快速 Prompt` 更快。

```text
使用hyptest-workflow skill

test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first

自动化证据流程：
- 用 case_preflight_pack.py 聚合输入、规格/平台口径、repo evidence index、相似 case reading pack 和目标 test_point 摘要
- 用 repo_evidence_index.py 复用全仓 case/test_point/register 索引缓存，但不能缩小到模块局部范围
- 命名不确定时用 suggest_case_name.py 生成候选名并检查同名/相似名
- 如需要 skeleton，用 make_case_skeleton.py 生成保守骨架，再按 test_point 和相似 case 填断言
- 写完后用 case_gate_pack.py 汇总单 case 编译、非 compile-only 单 case 运行、postcheck 和本轮日志定位
- 用 make_case_submission_card.py --emit-final-draft 整理交付草稿
- 用 case_workflow_ledger.py 记录耗时和返工信号

质量要求：
- 不跳过规格/平台口径（spec_profile）、repo 级 case 去重、单 case 编译/运行、回填/注册一致性
- 不需要手动填写 coverage_scope；新增测试点默认全仓 test_point 覆盖检查，补已有条目默认局部测试点检查
- 不把 preflight、skeleton、命名建议、submission draft 或 ledger 当作分层结论

输出要求：
- 新增 case、唯一性证据、编译/运行结果、关键日志路径、test_point 回填状态和最终决策
- preflight / gate / postcheck / submission card / ledger 的报告路径
```

## 按模块找 suspected bug Prompt

适合用户不是指定某个旧 `### PnX`，而是要求“继续围绕某个模块找 bug 点，并新增 case”。这个模板比默认新增 case 更明确：它要求先分析目标模块源码和当前 test_point，不能把已有条目或已有 case 当成本轮新增结果。

### 高质量版

```text
使用hyptest-workflow skill

test_point_file: test_point/<module>_suspected_bug_corner_points_<n>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
target_module: <module>

目标：
- 继续围绕 target_module 指定的模块找 1 个高价值 suspected bug corner point，并新增 1 个对应 ai_* case
- 当前 test_point_file 只当容器，文件里已有 `### PnX` 和“已实现 case”不能重复当成本轮新增结果
- 如果 prompt 提供了 bug_hunt_focus，优先从这些方向找未覆盖边界
- 不要按模块目录做局部捷径；必须做 repo 级 test_point 覆盖检查和 repo 级 case 去重

执行要求：
- 先分析目标模块源码、当前 test_point 文件、已有“已实现 case”映射和 test_register.c 状态
- 新增测试点前，扫描全仓 test_point/*.md，证明类似测试点未覆盖
- 写 case 前，搜索全仓 ai_test_cases/*.c 和 manual_test_cases/**/*.c，读取 2-5 个相似 case 作为实现参考
- 同时做精确函数名唯一性检查，不能只凭相似检索未命中
- 写 case 前确认规格/平台口径（spec_profile）、Spike gate 适用性和模型边界
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
- 实际使用的规格/平台口径（spec_profile）
- 新增测试点编号和标题
- 新增 case 名与文件路径
- 唯一性证据：repo 级 test_point 覆盖检查、repo 级相似 case 检索 top results、函数名精确唯一性检查
- 编译命令、编译结果、ELF/ASM 路径
- 运行命令、运行结果、关键日志路径
- test_point 回填位置和 test_register.c 注册状态
- 最终决策：default/manual/compile-only/blocked；如果不是 default，给出 reason_code
- 如果扫描后没有发现新的高价值 bug 点，明确说明“未发现新的测试点 / 未新增 case”，不要把旧条目或旧 case 当作新增结果
```

### 轻量快速版

适合像“继续围绕 memblock 新增 1 个用例”这类单 case 任务。目标是缩短实际完成时间，不强制跑完整 preflight pack、submission card 或 ledger；但质量门禁不缩水。

```text
使用hyptest-workflow skill

test_point_file: test_point/<module>_suspected_bug_corner_points_<n>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
target_module: <module>

目标：
- 快速但不降质量地继续找 1 个 target_module 相关的高价值 suspected bug corner point
- 新增 1 个新的 `### PnX` 条目和 1 个对应 ai_* case
- 不重复当前文件已实现条目，不把旧条目或旧 case 当新增结果

快速路径：
- 若输入和环境清楚，不跑完整 case_preflight_pack.py；直接确认 spec_profile、platform、test_point_file、task_mode 和 target_module
- 如果提供了 bug_hunt_focus / bug_hunt_focus_terms，先围绕这些关键词查；没有提供时根据 target_module、当前 test_point 和相关源码自行选关键词
- 用 rg / find_similar_cases.py 完成 repo 级 test_point 覆盖检查、repo 级 case 相似检索和函数名精确唯一性检查
- 只读取实现所需的 2-5 个相似 case；不要扩展到无关模块或全量审计
- 命名明确时直接定名；只有命名不确定时才用 suggest_case_name.py
- case 结构简单时直接写；只有框架结构不确定时才用 make_case_skeleton.py，且必须补完整断言
- 写完后优先用单 case 编译/运行命令闭环；case_gate_pack.py 可用于汇总，但不强制替代直接命令
- 默认不跑 make_case_submission_card.py 和 case_workflow_ledger.py，除非用户要求标准报告或复盘耗时

质量要求：
- 不跳过规格/平台口径（spec_profile）
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

### 自动化证据版

适合连续跑多个 suspected bug case、需要统一报告路径、或要复盘耗时/返工原因。它优化的是证据标准化和复盘成本；由于会固定跑多个 pack/report 工具，单次 1 个 case 不一定比 `轻量快速版` 更快。

```text
使用hyptest-workflow skill

test_point_file: test_point/<module>_suspected_bug_corner_points_<n>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
target_module: <module>

目标：
- 继续围绕 target_module 找 1 个高价值 suspected bug corner point
- 新增 1 个新的 `### PnX` 条目和 1 个对应 ai_* case
- 不重复当前文件已实现条目，不把旧条目或旧 case 当新增结果

自动化证据流程：
- 用 case_preflight_pack.py 聚合任务输入、规格/平台口径、repo snapshot、repo evidence index、环境检查、相似 case reading pack 和目标 test_point 摘要
- preflight query 优先覆盖 bug_hunt_focus_terms；未提供时根据 target_module、当前 test_point 和相关源码自行选关键词
- 用 repo_evidence_index.py 复用全仓 case/test_point/register 索引缓存，但不能缩小到模块局部范围
- 命名不确定时用 suggest_case_name.py 生成候选 case 名并检查同名/相似名
- 如需要 skeleton，用 make_case_skeleton.py 生成保守骨架，再根据 test_point 和相似 case 填完整断言；不能把 skeleton 当完成 case
- 写完 case 后用 case_gate_pack.py 完成单 case 编译、非 compile-only 单 case 运行、postcheck、本轮日志定位和失败日志自动分类
- 用 make_case_submission_card.py --emit-final-draft 汇总交付草稿
- 用 case_workflow_ledger.py 记录耗时和返工信号

质量要求：
- 不跳过规格/平台口径（spec_profile）
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

test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: preflight-only

要求：
- 只做只读分析，不修改文件
- 跑 case_preflight_pack.py，必要时跑 repo_evidence_index.py 和 find_similar_cases.py
- 按“是否要找新增空间”自动选择测试点覆盖范围；如果是跨文件排重，检查全仓 test_point
- 输出目标 test_point 摘要、相似测试点/相似 case、规格/平台口径和 Spike gate 注意点
- 给出是否值得新增 case 的建议，但不新增 case、不注册、不编译、不运行
```

## 补已有测试点 Prompt

适合用户明确指定了旧条目，例如“继续补 P6B”：

```text
使用hyptest-workflow skill

test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: supplement-existing-point
target_test_point: "### P<id>. <title>"
new_case_count: 1
target_policy: default-first

要求：
- 只围绕指定 `### P<id>` 补 case，不新增无关测试点
- 测试点覆盖检查默认围绕该条目/当前文件；case 相似检索仍是 repo 级
- 仍做 repo 级 case 相似检索和函数名唯一性检查
- 新增/修改 case 后单 case 编译，非 compile-only 单 case 运行
- 只在该条目的 `已实现 case` 下轻量回填，并检查 test_register.c 一致性
```

## 只跑验证 Prompt

适合已有 case，只想拿编译/运行证据：

```text
使用hyptest-workflow skill

platform: spike
spec_profile: <当前项目 spec_profile>

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
