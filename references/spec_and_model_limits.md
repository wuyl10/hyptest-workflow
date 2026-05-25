# HYPTEST 规格与平台模型边界入口

本文是规格/profile 路由入口，不承载项目专属细节。人工写 case、判断 Spike 结果、决定 default/manual/compile-only 前，先读本文，再按项目 profile 读取具体规则。

profile 参数：

- `spec_profile=<name>` 选择 `references/spec_profiles/<name>.md`。
- 例如 `spec_profile=<name>` 对应 `references/spec_profiles/<name>.md`。
- 可选 profile 和默认 profile 记录在 `references/spec_profiles/index.json`。
- 若用户给 profile 文件路径，直接读取该路径。
- 显式 `spec_profile` 优先；若未指定，默认使用 `spec_profile=<name>`。
- 交付摘要中应记录实际使用的 `spec_profile`。
- 可用 `python3 scripts/resolve_spec_profile.py --spec-profile <name>` 确认实际 profile 路径。

## 1. 使用顺序

1. 先确认当前任务所属项目/profile，即 `spec_profile`；未指定时使用 profile registry 中的 `default_profile`。
2. 读取 `references/spec_profiles/<spec_profile>.md`。
3. 再读取 `references/writing_cases.md` 落地 case 结构与断言。
4. 需要 harness/API、注册、脚本细节时，读取 `references/framework_usage_pitfalls.md`。
5. 需要编译运行和日志判读时，读取 `references/build_run_debug.md`。

## 2. 通用问题清单

写 case 或判断 Spike 结果前，必须先回答：

- 规格来源是什么：ISA/privileged spec、当前项目 profile（`references/spec_profiles/<spec_profile>.md`），还是 memory `events.jsonl` 中 `status=confirmed` 的已确认历史规则？
- 目标地址类型是什么：DRAM/cacheable、PBMT=NC、PBMT=IO、PMA IO/device、PMP deny/restore、bad PA、MMIO responder？
- 目标语义来自哪里：PMA、PBMT、PMP、页表权限、trigger、异常优先级，还是微架构路径？
- 是否依赖 Spike 缺失或弱化的 TLB/cache/CBO/refill/replay/sbuffer/MSHR/reservation-timeout 行为？
- 当前平台/testbench 是否有满足本场景语义的 responder？
- 本 case 初始分层应是 default、manual、compile-only 还是 blocked？

## 3. 通用裁决原则

- 测试点写了什么 bug 场景，case 就必须构造什么 bug 场景；不要用“近似场景”替代“目标场景”。
- 若测试点要求 specific fault order / producer order / template switch / address layout / guard-preserved 检查，case 中必须保留这些关键维度。
- 若文本要求与现实可构造性冲突，先标 `blocked` 或降级分层，不要偷换成更容易通过 Spike 的相邻场景。
- Spike 是重要参考，但不是所有场景的最终真值；先按当前 profile 判断 `spike_gate_applicable`，再决定是否运行/准入。
- `spike_gate_applicable=false` 只表示 official Spike 不适合作为该场景的 default gate；它不是测试价值低、覆盖优先级低、可以不写 case 的信号。不要为了得到 default/Spike pass，把测试点目标替换成更容易建模的近似 baseline。
- 不要因为单次 Spike 结果反向改写长期规则口径；先判断是否属于 profile 中的模型边界。

## 4. 新增或切换 profile

如果后续项目/核/平台规格变化，不直接堆到本文，新增或修改 profile。建议从空白模板起步：

```text
references/spec_profiles/template.md
```

新 profile 文件放在：

```text
references/spec_profiles/<spec_profile>.md
```

同时把新 profile 加入 registry：

```text
references/spec_profiles/index.json
```

推荐流程：

1. 先确定新 profile 名称，例如 `<project_or_core>.md`，文件放在 `references/spec_profiles/`。
2. 不要复制旧 profile 后只局部替换项目名；先清空项目专属事实，再逐项写入当前项目真实规则。
3. 按本文的通用问题清单补齐项目范围、平台模型边界、Spike gate、异常优先级和分层默认口径。
4. 检查是否有旧项目残留词，例如旧核名、旧地址窗口、旧 PMA/PBMT 表、旧 Spike 限制、旧 RTL-only 规则。
5. 若 profile 改动会影响 `default` / `manual` / `compile-only` / `blocked` 裁决，再同步检查分层和原因码文档。
6. 运行 profile 结构检查，确认新增 profile 能被解析且必备结构完整。

profile 至少包含：

- 项目范围与默认策略。
- PMP/PMA/PBMT/MMIO/cacheability 口径。
- Spike gate 可用/不可用边界。
- LinkNan 或其它平台 responder/环境限制。
- 异常优先级、`tval/tval2/tinst` 等项目口径。
- default/manual/compile-only/blocked 默认分层建议。

profile 中应显式回答：

- 本项目哪些内容属于常规验证范围，哪些属于本轮范围外。
- 目标平台是否有 cache/TLB/PMA/PBMT/MMIO/responder 模型限制。
- official Spike 可以作为哪些场景的 gate，哪些场景只能 RTL-only / manual / compile-only / blocked。
- 访问区间、PMA/PBMT 组合、异常优先级、`tval/tval2/tinst` 等是否有项目专属口径。
- 如果 Spike 与项目规则不一致，默认归因路径是什么。

可能需要同步检查的通用文档：

- `references/tiering_decision.md`
- `references/reason_code_catalog.md`
- `references/quality_gate.md`
- `references/submission_card.md`

新增或修改 profile 后，建议执行：

```bash
python3 scripts/check_spec_profile_registry.py
python3 scripts/check_spec_profile.py --spec-profile <name>
python3 scripts/check_spec_profile.py --spec-profile <name> --strict
```

若调用方传的是 profile 文件路径，建议同时确认两种入口都可解析：

```bash
python3 scripts/resolve_spec_profile.py --spec-profile <name>
python3 scripts/resolve_spec_profile.py --spec-profile references/spec_profiles/<name>.md
```
