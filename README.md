# hyptest-workflow

`hyptest-workflow` 用于 `riscv-hyp-tests-nhv5` 仓库里的 hyptest 测试点落地闭环。它面向的不是“只写一个 C 函数”，而是把 `test_point` 里的测试意图推进到可追踪的 case、注册状态、编译运行证据、分层结论和轻量回填。

典型目标：

- 从 `test_point/*.md` 新增、补充或修复 `ai_test_cases/*.c` / `manual_test_cases/**/*.c`。
- 围绕某个模块继续找 suspected bug point，新增 `### PnX` 条目并落地对应 `ai_*` case。
- 防止重复造点：做全仓 `test_point` 覆盖检查、跨文件扩点排重、case 相似检索和函数名唯一性检查。
- 确认规格/平台口径（`spec_profile`）、Spike gate 适用性，以及 PMA/PBMT/MMIO/cache/TLB/CBO 等模型边界。
- 通过 `compile_elf.py` / `get_result.py` 拿到单 case、小批量或多平台编译运行证据。
- 保持 `test_register.c`、`test_point` 的“已实现 case”映射和最终分层一致。
- 判断 case 进入 `default`、`manual`、`compile-only` 还是 `blocked`。

## 入口文件

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | Codex 触发和执行入口，包含硬规则、流程、分层和最终答复要求 |
| `references/prompt_recipes.md` | 高质量 prompt、更快 prompt、模块 suspected bug prompt、只读预检等可复制模板 |
| `references/command_index.md` | 完整命令索引，由 `scripts/list_skill_commands.py --markdown` 生成 |
| `references/quick_execution.md` | 从 preflight 到 gate、postcheck、submission card 的快速闭环 |
| `references/task_input_schema.md` | 目标仓库、测试点文件、平台、任务模式等输入字段 |
| `references/coverage_and_dedupe.md` | 测试点覆盖检查、case 去重和唯一性证据口径 |
| `references/spec_and_model_limits.md` | 规格/profile 路由和平台模型边界入口 |
| `references/spec_profiles/` | 项目 profile，决定 Spike gate、PMA/PBMT/MMIO 等口径 |
| `references/writing_cases.md` | case 编写、断言、注册、回填格式 |
| `references/quality_gate.md` | Gate A-H 质量门禁 |
| `references/tiering_decision.md` | `default` / `manual` / `compile-only` / `blocked` 分层规则 |
| `references/resource_index.md` | 本 skill 的资源索引，列出 references、scripts、assets 和 eval |
| `references/maintainer_guide.md` | 修改 skill、脚本、profile、reason_code 和 eval 后的维护检查 |

## 什么时候使用

看到这些任务或关键词时应使用本 skill：

- 新增、补充或修复 hyptest case。
- 修改 `ai_test_cases/`、`manual_test_cases/` 或 `test_register.c`。
- 根据 `test_point` 回填“已实现 case”。
- 检查类似测试点是否已经覆盖。
- 检查其它文件里有没有重复 case 或相似 case。
- 跨 `test_point/*.md` 排重、扩点或找新的 suspected bug point。
- 编译单 case、小批量 case 或全量 active case。
- 跑 Spike / LinkNan，并输出运行日志路径。
- 初步分析 Spike / LinkNan 运行日志，并做 default/manual/compile-only/blocked 分层。
- 处理 PMA/PBMT/MMIO/cache/TLB/CBO 等需要 profile 判断的场景。
- 需要把一次 case 交付整理成“新增 case、唯一性证据、编译/运行结果、日志路径和最终决策”。

如果任务已经进入 selfcheck fail、difftest mismatch、stuck、`50000 cycles no commit`、FSDB 波形或疑似 RTL bug 深挖，优先使用 `hyptest-failure-triage`。`hyptest-workflow` 负责 case 落地、证据整理和初步归因；深入失败闭环交给 triage。若任务需要波形 first-bad-cycle、握手、协议或 X-state 分析，同时使用 `waveform-debug`。

## 目标仓库和环境

一次任务需要先说明 `riscv-hyp-tests` 仓库位置。推荐直接在 prompt 里填仓库根目录：

```text
repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
```

如果团队希望少写路径，可以约定一个明确的便利变量：

```text
repo_root: $HYPTEST_REPO
test_point_file: test_point/<xxx>.md
```

这里的 `repo_root` 只是 prompt 字段名，含义是“`riscv-hyp-tests` 仓库根目录”；它不是 hyptest 平台环境变量。`HYPTEST_REPO` 也只是可选的团队便利别名，不要求 hyptest 仓库必须提供。路径字段支持 shell 风格的 `$VAR` 展开。

hyptest 编译/运行环境变量仍按 hyptest 仓库既有说明设置，例如：

```text
SPIKE_BIN         official Spike executable
LINKNAN_HOME      LinkNan repo root
DIFFTEST_REF_SO   difftest reference shared object
CROSS_COMPILE     RISC-V toolchain prefix
```

本 README 不重复展开这些变量的配置方式。需要检查环境时运行：

```bash
python3 scripts/check_env.py --repo-root <hyptest_repo> --platform all --explain
```

平台名只使用 `spike` 或 `linknan`；不要把 `xiangshan` 写成 hyptest 的 `platform` / `--plat` 参数。

## Prompt 关键词速查

写 prompt 时不需要把所有字段都填满。先填“最小必填”，再按任务类型补条件字段；其余字段让 workflow 按默认规则推导。

### 最小必填

| 关键词 | 是否必填 | 含义 | 常见写法 |
| --- | --- | --- | --- |
| `repo_root` | 必填 | `riscv-hyp-tests` 仓库根目录。它是 prompt 字段名，不是 hyptest 平台环境变量。 | `<riscv-hyp-tests-nhv5.1 仓库根目录>` 或 `$HYPTEST_REPO` |
| `task_mode` | 必填 | 本次任务类型，决定是新增、补旧、修 case、只运行还是只回填。 | `new-case-only`、`supplement-existing-point`、`fix-case`、`run-only`、`writeback-only`、`triage-only` |
| `platform` | 编译/运行/环境检查时必填 | 目标 hyptest 平台。 | `spike` 或 `linknan` |
| `test_point_file` | 新增、补点、回填时必填 | 测试点容器文件。相对路径按 `repo_root` 下解析；绝对路径也可以。 | `test_point/<xxx>.md` |

### 建议填写

| 关键词 | 是否必填 | 含义 | 常见写法 |
| --- | --- | --- | --- |
| `spec_profile` | 建议填写；未填会用默认 profile | 规格/平台口径，用来判断 Spike gate、PMA/PBMT/MMIO/cache/TLB/CBO 模型边界和最终分层。它不是功能开关。 | `<当前项目 spec_profile>` |
| `target_policy` | 选填，默认 `default-first` | 分层目标倾向。`default-first` 表示优先争取 default，不是无条件 default。 | `default-first`、`manual-ok`、`compile-only-ok` |
| `new_case_count` | 新增 case 时建议填写，默认 `1` | 本轮希望新增几个 case。 | `1` 或 `1-3` |

### 按任务条件填写

| 关键词 | 什么时候填 | 含义 | 常见写法 |
| --- | --- | --- | --- |
| `case_name` | `run-only`、`fix-case`、已有 case gate 时 | 指定要编译、运行、修复或收证据的 case。 | `ai_micro_xxx` |
| `target_test_point` | 补已有 `### PnX` 时 | 指定只围绕哪个旧测试点补 case，避免误新增无关条目。 | `"### P11A. <title>"` |
| `target_module` | 按模块继续找 suspected bug 时 | 指定目标模块，帮助聚焦源码和测试点。 | `memblock` |
| `bug_hunt_focus` / `bug_hunt_focus_terms` | 按模块找新 bug 点时 | 给 workflow 一组关注方向和检索词，加快 preflight 与相似 case 检索。 | `CMO / LRSC / fence` |
| `failure_log` | `triage-only` 或失败归因时 | 指定失败日志。若进入 stuck、difftest、FSDB 或疑似 RTL bug，优先转 `hyptest-failure-triage`。 | `result_log/<platform>/<log>` |

### 通常不用填

| 关键词 | 默认行为 | 什么时候才手动填 |
| --- | --- | --- |
| `coverage_scope` | workflow 根据目的自动推导：新增测试点 / 找 suspected bug / 跨文件排重 -> `repo`；补已有 `### PnX` -> `file`。case 相似检索始终是 repo 级。 | 只有高级排查、复现实验或需要覆盖默认行为时才显式写 `file` / `repo`。 |
| `reason_code` | 通常由运行结果、profile 和分层规则推断。 | 已经有明确非 default 结论，希望保留或复核原因码时。 |

最常见的新增 case prompt 只需要这些字段：

```text
repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first
```

更完整的字段说明见 `references/task_input_schema.md`，可复制 prompt 模板见 `references/prompt_recipes.md`。

## 标准流程

常用命令可以直接列出：

```bash
python3 scripts/list_skill_commands.py
```

一次新增 case 的典型闭环：

1. 锁定输入：目标仓库、测试点文件、平台、任务模式、目标策略和规格/平台口径（`spec_profile`）。
2. 区分新增测试点还是补已有 `### PnX`。`test_point_file` 只是容器，`### PnX` 才是独立测试点。
3. 根据任务目的选择覆盖检查范围：新增测试点默认全仓排重；补已有 `### PnX` 默认只围绕该条目做局部测试点检查。
4. 做测试点覆盖检查、repo 级 case 相似检索和函数名唯一性检查。
5. 确认规格/平台口径、Spike gate 适用性和平台模型边界。
6. 新增或修改 case，更新 `test_register.c`。
7. 单 case 编译；非 `compile-only` 必须单 case 跑目标平台。
8. 回填 `test_point`，只写 case 映射和必要短状态，不追加审计式块。
9. 检查回填与注册一致性。
10. 输出新增 case、唯一性证据、编译/运行结果、关键日志路径和最终决策。

覆盖检查范围通常不用用户手动填写：

- 你说“新增测试点 / 继续找 suspected bug point / 跨文件排重”，workflow 自动按全仓 `test_point/*.md` 检查。
- 你说“补已有 PnX / 给这个条目再补 case”，workflow 自动按当前条目或当前文件做局部测试点检查。
- case 相似检索始终是 repo 级，不因为局部补点而缩小范围。

`spec_profile` 是“规格/平台口径”的名字，不是功能开关。它告诉 workflow 当前项目按哪套规则判断 Spike gate、PMA/PBMT/MMIO/cache/TLB/CBO 等模型边界，以及 case 能否进入 `default`。不写时会使用默认 profile；正式新增 case 时建议显式写出当前项目 profile，具体可复制示例见 `references/prompt_recipes.md`。

常用入口：

```bash
python3 scripts/validate_task_request.py --repo-root <hyptest_repo> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1
python3 scripts/case_preflight_pack.py --repo-root <hyptest_repo> --test-point-file <test_point_file> --platform spike --spec-profile <spec_profile> --task-mode new-case-only --new-case-count 1 --query '<scenario terms>' --md-out .hyptest_skill_reports/case_preflight.md --json-out .hyptest_skill_reports/case_preflight.json
python3 scripts/case_gate_pack.py --repo-root <hyptest_repo> --test-point-file <test_point_file> --case <case_name> --platform spike --spec-profile <spec_profile> --md-out .hyptest_skill_reports/case_gate.md --json-out .hyptest_skill_reports/case_gate.json --postcheck-md-out .hyptest_skill_reports/case_postcheck.md --postcheck-json-out .hyptest_skill_reports/case_postcheck.json
```

这里的 `<hyptest_repo>` 就是目标 `riscv-hyp-tests-nhv5.1` 仓库根目录；如果使用变量，建议写成 `"$HYPTEST_REPO"`。

更多命令见 `references/command_index.md`。

## Prompt 模板

最短可用 prompt：

```text
使用hyptest-workflow skill

repo_root: <riscv-hyp-tests-nhv5.1 仓库根目录>
test_point_file: test_point/<xxx>.md
platform: spike
spec_profile: <当前项目 spec_profile>

task_mode: new-case-only
new_case_count: 1
target_policy: default-first

要求：
- 先分析目标模块和 test_point，再新增 1 个 ai_* case
- 根据任务目的选择覆盖检查范围；新增测试点默认做全仓 test_point 覆盖检查
- 做 repo 级 case 相似检索和函数名唯一性检查
- 写 case 前确认规格/平台口径和 Spike gate 适用性
- 非 compile-only 必须单 case 编译并单 case 跑目标平台
- 回填 test_point，并与 test_register.c 一致
- 输出新增 case、唯一性证据、编译/运行结果、关键日志路径和最终决策
```

更完整的模板见 `references/prompt_recipes.md`：

| 用途 | 推荐模板 |
| --- | --- |
| 正式新增 1 个高质量 case | 高质量默认 Prompt |
| 想缩短单 case 生成时间 | 更快 Prompt |
| 围绕某个模块继续找 suspected bug | 按模块找 suspected bug Prompt |
| 先只看有没有新增空间 | 只读预检 Prompt |
| 补已有 `### PnX` | 补已有测试点 Prompt |
| 只跑已有 case | 只跑验证 Prompt |

## 分层口径

| 分层 | 含义 | 注册状态 |
| --- | --- | --- |
| `default` | 编译通过、运行通过、规则一致、Spike gate 适用、证据完整 | `TEST_REGISTER(case_name);` 开启 |
| `manual` | 场景合理，但不适合常规 Spike gate，或需要人工/RTL 环境确认 | 通常注释注册 |
| `compile-only` | 当前只保证可编译，运行 gate 不成立或阶段性不运行 | 通常注释注册 |
| `blocked` | 编译、运行、规则、证据或注册一致性存在阻塞 | 不作为完成落位 |

`default-first` 的意思是优先争取 default，不是无条件放 default。PMA/PBMT/MMIO/cache/TLB/CBO 等场景必须先看 profile；如果 `spike_gate_applicable=false`，不能只凭 official Spike 结果作为 default gate。

## 硬规则速记

- 写 case 或判断 Spike 结果前，先确认规格/平台口径（`spec_profile`）。
- `test_point_file` 是容器文件，每个 `### PnX` 才是独立测试点。
- 新增测试点默认做 repo 级 `test_point` 覆盖检查。
- 写 case 前同时做 repo 级 case 相似检索和函数名精确唯一性检查。
- 一个 case 函数只能有一个 `TEST_END(...)`。
- 只要断言 `excpt.triggered/cause/tval`，先调用 `TEST_SETUP_EXCEPT()`。
- 注册统一放 `test_register.c`，不在 case 源文件末尾注册。
- 非 `compile-only` 必须单 case 编译并单 case 运行目标平台。
- `test_point` 只回填 case 映射和必要短状态，不写日志、Gate 结果或分层审计块。
- `test_register.c` 的启用/注释状态必须和最终分层一致。

## 自检

修改本 skill 后运行：

```bash
python3 scripts/check_readme_commands.py
python3 scripts/check_docs_links.py
python3 scripts/check_skill_consistency.py
python3 scripts/check_resource_index.py
python3 scripts/update_resource_index.py --check
```

需要更完整的快速自检：

```bash
python3 scripts/self_check.py --quick --spec-profile <spec_profile>
```

## 最终答复要求

默认用中文，结论要具体。完成一次 case 工作后至少输出：

- 实际使用的规格/平台口径（`spec_profile`）。
- 新增或修改的 case 名和文件路径。
- 唯一性证据：测试点覆盖检查、相似 case 检索、函数名唯一性检查。
- 编译命令、编译结果、ELF/ASM 路径。
- 运行命令、运行结果、关键日志路径。
- `test_point` 回填位置和 `test_register.c` 注册状态。
- 最终决策：`default` / `manual` / `compile-only` / `blocked`。
- 如果不是 `default`，给出 `reason_code` 和简要原因。
