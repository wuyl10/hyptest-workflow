# HYPTEST 快速执行版（保质量）

本文是加速执行入口，不是规则简化版。所有质量判定仍以 `references/spec_and_model_limits.md`、当前 `references/spec_profiles/<spec_profile>.md`、`references/writing_cases.md`、`references/framework_usage_pitfalls.md`、`references/build_run_debug.md` 为准。

## Table of Contents

- [0. 使用原则](#0-使用原则) — Gate-0..7 对照、提速边界
- [1. 输入锁定（Gate-0）](#1-输入锁定gate-0) — 输入清单、preflight pack 聚合入口
- [2. 用例落地（Gate-1）](#2-用例落地gate-1) — 相似检索、skeleton、命名建议、uniqueness
- [3. 单点编译（Gate-2）](#3-单点编译gate-2)
- [4. 单点运行（Gate-3）](#4-单点运行gate-3) — `compile-only` 特例
- [5. 语义裁决（Gate-4）](#5-语义裁决gate-4) — profile + `spike_gate_applicable`
- [6. 分层落位（Gate-5）](#6-分层落位gate-5) — default/manual/compile-only 判定
- [7. 回填闭环（Gate-6）](#7-回填闭环gate-6) — 映射回填 + `check_writeback_format`
- [8. 证据交付（Gate-7）](#8-证据交付gate-7) — submission card、multi-platform gate、timing、ledger
- [快速执行不降质的三条红线](#快速执行不降质的三条红线)
- [一条命令的最短闭环](#一条命令的最短闭环仅在已满足-gate-01-时) — `compile_elf && get_result`

## 0. 使用原则

- 目标：减少路径切换成本，不减少质量检查项。
- 方法：把完整流程压缩成 8 步，每步都设硬门禁。
- 约束：任何门禁不通过，立即转详细文档排查，不得跳步。
- 推荐：写 case 前先用 `scripts/case_preflight_pack.py` 聚合只读上下文；写完后优先用 `scripts/case_gate_pack.py` 做单 case 编译/运行/证据收口，若已经手工编译运行过，再用 `scripts/case_postcheck_pack.py` 只收证据。
- 提速边界：pack 脚本可以并行执行独立检查、保守缓存只读 preflight、快速定位日志和整理证据卡，但不能省略 Gate，也不能自动决定 default/manual/compile-only。

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

- 仓库来源（`$HYPTEST_HOME` 指向的 `riscv-hyp-tests` fork）
- 当前分支（以团队约定为准，常见 `nhv5.1`）
- 测试点文件与条目
- case 名
- 平台（通常 `spike`）
- 规格/平台口径（`spec_profile`，可显式指定；未指定时默认 profile registry 的 `default_profile`）
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

更快的聚合入口：

```bash
cd $HYPTEST_SKILL_HOME
python3 scripts/case_preflight_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --platform spike \
  --spec-profile <spec_profile> \
  --task-mode new-case-only \
  --new-case-count 1 \
  --query '<scenario terms>' \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.md \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json
```

说明：

- `case_preflight_pack.py` 会并行执行输入、规格/平台口径、repo snapshot、相似 case 和环境检查。
- 只补当前进程看不到的必需环境变量。若当前环境没有 `HYPTEST_HOME`，prompt 要写 `HYPTEST_HOME: <riscv-hyp-tests 仓库根目录>`；若 `platform=spike` 且会跑 gate、但当前环境没有 `HYPTEST_SPIKE_BIN`，prompt 要写 `HYPTEST_SPIKE_BIN: <community/upstream Spike 可执行文件>`；若要跑 LinkNan，确认 `HYPTEST_LINKNAN_HOME`、`HYPTEST_DIFFTEST_REF_SO`；若要读 Nanhu 源码，确认 `HYPTEST_LINKNAN_HOME/dependencies/nanhu/src/main` 存在。与本轮平台无关的组件可以省略。
- 如果 prompt 显式给了 `HYPTEST_SPIKE_BIN: <path>` / `HYPTEST_LINKNAN_HOME: <path>` / `HYPTEST_DIFFTEST_REF_SO: <path>`，命令里加对应 `--env HYPTEST_*=<path>`；临时目录用 `--env HYPTEST_TMPDIR=<path>`。
- 未显式传 `--coverage-scope` 时，脚本会按 `--task-mode` 推导：`new-case-only` 默认 repo，`supplement-existing-point` 默认 file；case 相似检索仍始终是 repo 级。
- `case_preflight_pack.py` 会同时调用 `repo_evidence_index.py`，构建或复用全仓 case、`test_point` 条目和注册状态索引。该索引按文件指纹失效，不按模块裁剪覆盖范围。
- preflight pack 使用保守缓存；只要输入参数、目标 test_point、`test_point/*.md`、`ai_test_cases/*.c`、`manual_test_cases/**/*.c`、`test_register.c`、关键环境变量、toolchain 命中路径、profile 文件或相关 skill 脚本发生变化，缓存就会失效。
- 如需强制重跑，加 `--no-pack-cache`。

## 2. 用例落地（Gate-1）

执行：

1. 先按 `references/spec_and_model_limits.md` 选择规格/平台口径（`spec_profile`，未指定时默认 profile registry 的 `default_profile`），并按 `references/spec_profiles/<spec_profile>.md` 确认规格来源、平台模型边界、`spike_gate_applicable` 和初始分层候选。
2. 再检索 2~5 个相似存量 case，优先复用已有写法中的结构、断言和环境构造。
   如果测试点描述较长、分支较多，优先让脚本先生成 reading pack，再由模型抽象哪些结构值得学、哪些不能照搬。
3. 命名确定后，先做精确唯一性检查；新增 case 用 `--expect absent`，不要等写完后才第一次发现撞名。
4. 需要骨架时，再从 `assets/templates/new_case_template.c` 起步；若测试点变化较大，直接按 `references/writing_cases.md` 的结构与断言原则自行展开，不要被模板形状反向限制。
5. 在合适的 case 目录写或改 case：AI/批量生成 case 默认放 `ai_test_cases/`，人工维护 case 放 `manual_test_cases/<module>/`。
6. 按 `references/framework_usage_pitfalls.md` 复核 `TEST_SETUP_EXCEPT()`、`TEST_END(...)`、注册和工具使用风险。

建议命令：

```bash
python3 scripts/find_similar_cases.py \
  --repo-root $HYPTEST_HOME \
  --from-file <test_point_file> \
  --query cross_16b --query retry --query access_fault \
  --show-snippet \
  --limit 5
```

更适合大模型阅读的检索方式：

```bash
python3 scripts/find_similar_cases.py \
  --repo-root $HYPTEST_HOME \
  --from-file <test_point_file> \
  --query cross_16b --query retry --query access_fault \
  --assert-only \
  --emit-reading-pack \
  --limit 3
```

如果只是想预热或复用全仓索引，可单独执行：

```bash
python3 scripts/repo_evidence_index.py \
  --repo-root $HYPTEST_HOME \
  --query '<scenario terms>' \
  --json
```

需要机械骨架时，可从 preflight 证据生成保守 skeleton：

```bash
python3 scripts/make_case_skeleton.py \
  --case <case_name> \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --test-point-id <PnX>
```

注意：skeleton 只减少搭框架时间，默认保留 TODO 和失败断言；不能把 skeleton 当作已完成 case。

命名前可以先生成候选并做冲突检查：

```bash
python3 scripts/suggest_case_name.py \
  --repo-root $HYPTEST_HOME \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --prefix ai_micro \
  --json
```

该脚本只建议 case 名，并检查全仓精确同名和相似名称；最终命名仍需结合测试点语义和相似 case 检索结果确认。

命名确定后做快速唯一性检查：

```bash
python3 scripts/check_case_uniqueness.py \
  --repo-root $HYPTEST_HOME \
  --case <case_name> \
  --expect absent \
  --json
```

该检查复用 `repo_evidence_index.py` 缓存，适合放在写 case 之前；写完后 `case_postcheck_pack.py` 仍会复核 `definition_unique=true`。

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

如果希望把 Gate-2、Gate-3 和证据收口压成一个命令，可在写完 case、注册和回填后执行：

```bash
cd $HYPTEST_SKILL_HOME
python3 scripts/case_gate_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case_name> \
  --platform spike \
  --spec-profile <spec_profile> \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.md \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json \
  --postcheck-md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.md \
  --postcheck-json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.json
```

该命令只聚合执行和证据，不替代 profile/tiering 规则裁决。它的 PASS 还要求 postcheck 能看到目标 ELF；非 `--compile-only` / 非 `--skip-run` 时，还要求能看到目标 case 的最新运行日志。

如果本轮 prompt 指定了 runner，例如 `HYPTEST_SPIKE_BIN: <path>`，在 `case_gate_pack.py` 命令中加 `--env HYPTEST_SPIKE_BIN=<path>`。如果 prompt 没写 runner，就必须先确认当前执行环境已有对应变量；缺失时先提醒调用者补齐，不运行 gate。

补充：

- 如果单 case 编译失败，`case_gate_pack.py` 会跳过运行阶段，但仍执行 postcheck 收集定义、注册和回填证据。
- `case_gate_pack.py` 会记录本轮 `get_result.py` 后新出现或更新的目标日志；如果运行失败或日志显示失败/超时，会优先用这份本轮日志调用 `classify_failure_log.py` 生成候选原因和下一步动作。该分类结果不等于最终分层。

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

- 对照 `references/spec_and_model_limits.md` 与 `references/spec_profiles/<spec_profile>.md` 判定语义是否一致，并确认 `spike_gate_applicable`。

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
  --repo-root $HYPTEST_HOME \
  --file <test_point_file> \
  --check-register
```

通过标准：

- 映射可追踪，原因写清楚。

## 8. 证据交付（Gate-7）

最小交付内容：

- 改动文件列表
- 实际使用的规格/平台口径（`spec_profile`）
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

```bash
cd $HYPTEST_SKILL_HOME
python3 scripts/case_gate_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case_name> \
  --platform spike \
  --spec-profile <spec_profile> \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.md \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json \
  --postcheck-md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.md \
  --postcheck-json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_postcheck.json
```

- 可继续生成证据卡片，减少最终摘要整理时间：

```bash
python3 scripts/make_case_submission_card.py \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.md
```

证据卡片只汇总 preflight/gate/postcheck 证据，不做分层裁决。

如果本轮一次新增 2~3 个 case，可用批量 gate 保留每个 case 的独立证据：

```bash
python3 scripts/case_batch_gate_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case1> \
  --case <case2> \
  --platform spike \
  --spec-profile <spec_profile> \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_batch_gate.json \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_batch_gate.md
```

批量 gate 默认串行执行，避免共享 build/result 目录互相踩踏；只有确认目标仓库产物隔离时才显式加 `--parallel`。批量报告不把多个 case 合并为一个分层结论。

最终交付草稿可让 submission card 生成：

```bash
python3 scripts/make_case_submission_card.py \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json \
  --emit-final-draft \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.md
```

交付草稿只整理“新增 case、唯一性证据、编译/运行、日志和回填”字段，`decision_final` 仍必须由 workflow 根据 profile、Spike gate 和日志证据填写。

如果同一 case 明确要求同时看 Spike 和 LinkNan，可用多平台 gate：

```bash
python3 scripts/case_multi_platform_gate_pack.py \
  --repo-root $HYPTEST_HOME \
  --test-point-file <test_point_file> \
  --case <case_name> \
  --platform spike \
  --platform linknan \
  --spec-profile <spec_profile> \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_multi_platform_gate.json \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_multi_platform_gate.md
```

多平台 gate 只是并行收集每个平台的证据，不把平台结果合并成最终分层。

长期观察耗时瓶颈时，可汇总 timing：

```bash
python3 scripts/case_timing_summary.py \
  --reports '$HYPTEST_HOME/.hyptest_workflow_skill/reports/*.json' \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/timing_summary.json \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/timing_summary.md
```

timing summary 只用于观察 compile/run/postcheck/cache hit 等耗时，不是质量门禁。

如果要记录单个 case 的端到端耗时和返工信号，可生成 workflow ledger：

```bash
python3 scripts/case_workflow_ledger.py \
  --case <case_name> \
  --preflight-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_preflight.json \
  --gate-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/case_gate.json \
  --submission-json $HYPTEST_HOME/.hyptest_workflow_skill/reports/submission_card.json \
  --json-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/workflow_ledger.json \
  --md-out $HYPTEST_HOME/.hyptest_workflow_skill/reports/workflow_ledger.md
```

ledger 只用于观察 preflight、编辑、compile、run、postcheck、提交整理中的耗时和返工信号，不参与分层裁决。

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
