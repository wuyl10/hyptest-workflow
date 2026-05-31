# Workflow State / Cache / Memory

本文承载 workflow 辅助状态的目录布局、清理/重建策略、memory 经验追加和 CLI 入口。`SKILL.md` 只保留最精要提醒，细节放这里。

## 目录布局

workflow 辅助状态默认统一放在 `$HYPTEST_HOME/.hyptest_workflow_skill/` 下，按用途分 4 个子目录：

| 子目录 | 内容 | 可清理 |
| --- | --- | --- |
| `cache/` | 可重建索引（`repo_evidence_index` / `find_similar_cases` 缓存）、preflight pack 中间产物 | 是 |
| `reports/` | preflight / gate / postcheck / submission / ledger 报告 | 是（留痕需要时再保留） |
| `tmp/` | 临时文件 | 是 |
| `memory/` | 本地可审计的经验记录 | **否**（见下文） |

目标 repo 的 `.gitignore` 建议包含：

```text
/.hyptest_workflow_skill/
```

避免把 workflow 状态提交到 upstream。

## Cache / Report / Tmp

- 这三类都只是"聚合 / 证据 / 临时文件"，失效或脏了可以直接删除重建。
- 跑一次 `repo_evidence_index.py` / `case_preflight_pack.py` 就会重建索引；删掉不会影响规则。
- 长期只保留"需要复盘的某次报告"即可。

清理命令：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/clean_generated.py --repo-root $HYPTEST_HOME
```

默认不会清 `memory/`。

## Memory

- `memory/` 记录本 repo 范围内**已知对的事实**——agent 可以直接复用的经验线索（历史失败现象、debug 路径、发现的 RTL quirk 等），**不替代**当前源码/日志/`spec_profile`/平台证据。
- 做 `default / manual / compile-only / blocked` 决策时，仍以**本轮证据**为准；memory 只是检索线索。
- **过时处理**：events.jsonl 是 append-only 但文件手工可编辑。某条记录因 Spike/RTL 升级不再成立 → **人工直接打开 `events.jsonl` 删除对应 JSON 行**，同时审阅 `test_point/Manual_Reference.md` 是否有相关条目需要一起删除。memory 没有 `obsolete` 占位——"memory 里每条都是当前仍然成立的事实"是单一真值约束。

### Status 分档（读写优先级）

memory 只存**可以直接参考的事实**；"可疑/待确认"一律放 `test_point/Manual_Reference.md`。2 档 status：

| status | 含义 | 典型来源 | 读取优先级 |
|---|---|---|---|
| `unconfirmed` | agent 自动沉淀的事实观察（3 门槛过）；**未经人工确认**——供参考但不作硬证据。`append` 默认值 | `workflow_memory.py append`（step 15 触发）| 次级参考 |
| `confirmed` | **人工确认过的经验**（从 Manual_Reference 迁入） | audit 迁入流程（见下文）| **首选** |

读端（`query` / 相似检索的 commented 判据 / bug hunt 历史复盘）两档状态都直接返回；优先用 `confirmed`，`unconfirmed` 作辅助参考。

**历史数据迁移**：commit d1151bf 前的 `info` / `fixed` 状态已分别等同为 `unconfirmed` / `confirmed`；历史 `open` / `obsolete` 条目极罕见——遇到请人工删行清理（不留占位）。

### Manual_Reference → memory 迁入流程

当人工 audit `test_point/Manual_Reference.md` 的一条 auto-append 条目时，结果分三档：

1. **"规则真值"**：把内容迁进 `references/spec_profiles/<profile>.md`（例如新的 Nanhu 实现约束、新的 Spike gap 类别，同步 `hyptest-nongate-keywords` JSON 块）；Manual_Reference 该条标 `> 已解决（<日期>）：已进 profile §X`，**不进 memory**（规则真值在 profile）。
2. **"复用线索"**：结论简化后 append memory `status=confirmed`；Manual_Reference 该条标 `> 已解决（<日期>）：已进 memory`。
3. **"作废 / 过时"**：**直接从 Manual_Reference 删除该条目**（不留 `> 已解决` 墓碑）；若 memory 里有对应的 `unconfirmed` 行，**同时从 `events.jsonl` 删除**。保持两边"干净 + 当前仍成立"的单一真值。

对应 CLI（"复用线索" 路径）：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/workflow_memory.py append \
  --repo-root $HYPTEST_HOME \
  --module <m> --platform <plat> --spec-profile <profile> \
  --phase case_design --status confirmed \
  --case <case_name> \
  --symptom "<一句话症状>" \
  --reason-code <reason_code_from_catalog> \
  --fix "<一句话结论>" \
  --source "test_point/Manual_Reference.md#C7" \
  --note "promoted from Manual_Reference after human confirmation <YYYY-MM-DD>"
```

`--status confirmed` + `--source test_point/Manual_Reference.md#<id>` 的组合让后续 query 能区分"人工确认的"与"agent 沉淀的"。

### Step 16 判 4 档路由

写回 Manual_Reference 前先跑 `check_manual_reference_topic.py` 判 verdict，避免重复 append：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_manual_reference_topic.py \
  --repo-root $HYPTEST_HOME \
  --case <case_name> --module <m> \
  --topic <kw1> --topic <kw2> \
  --spec-profile <profile>
```

| verdict | 动作 |
|---|---|
| `profile_covered` | 不新增 MR 条目；交付摘要里引用 profile §X |
| `memory_confirmed` | 不新增 MR 条目；复用 memory 条目的 fix/reason_code |
| `manual_reference_open` | **不新开条目**，在已有 MR 条目末尾补一行 `- 本轮也碰到：<case_name>，<关键现象>` |
| `new_entry_needed` | auto-append 新的 `#### <id>.（**自动生成，待人工确认**）` |

### 常用 CLI

```bash
# 追加一条经验（3 门槛过才跑；status 默认 unconfirmed，可省略）
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/workflow_memory.py append \
  --repo-root $HYPTEST_HOME \
  --topic <topic> \
  --note "<结论 / 现象 / 关键命令>"

# 按 topic 或关键词检索
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/workflow_memory.py query \
  --repo-root $HYPTEST_HOME \
  --topic <topic>

# 汇总当前有哪些活跃经验
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/workflow_memory.py summarize \
  --repo-root $HYPTEST_HOME
```

## 路径策略速查

查看当前路径推导结果（调试路径相关问题时用）：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/workflow_paths.py --repo-root $HYPTEST_HOME
```

## 膨胀控制

- 3 门槛把关（写端） + 按需 audit 人工删行 + 过时记录不留占位
- 典型规模：一年 20-50 条、几十 KB、按 topic 检索不会线性变慢

## 按需 audit（用户 prompt 触发）

用户发 "audit workflow memory" / "清理一下过时的 memory" / "memory 体检" 这类 prompt 时，agent 按以下步骤做：

1. 跑 `scripts/workflow_memory.py summarize --repo-root $HYPTEST_HOME` 拿所有 entry 概览
2. 按以下启发式标记**候选过时 entry**（不直接改，先列给用户确认）：
   - 含"可能 / 也许 / 感觉 / 估计"等模糊词（违反 3 门槛"可验证事实"）
   - 未带日期标签（违反补充准入）
   - 一条内容同时讲多件事（违反"一条一事"）
   - 日期早于 6 个月，但 topic 近期没被任何任务 query 命中（低复用）
   - 内容已在 SKILL.md / references / test_point 中正式文档化（不符合"非平凡"）
3. 把候选清单列给用户：`timestamp / case / module / symptom / 可疑原因`
4. 用户**逐条确认**后，**人工直接在 `events.jsonl` 中删除对应 JSON 行**（memory 没有 obsolete 占位，审完即清）；同时审阅 `test_point/Manual_Reference.md` 是否有相关条目一起删除。
5. 完成后给用户出**audit 报告**：保留 X 条、删除 Y 条、建议人工再核 Z 条

**约束**：
- **agent 不自动改** `events.jsonl`；只列候选 + 让用户决定，最后由用户亲手编辑文件
- **不自动判定**过时，只列候选 + 让用户决定
- 建议频次：每积累 50 条 entry 或每 3 个月手工触发一次，不定时

## 与 Claude auto memory 的分工

本 workflow memory 只覆盖**本 repo 范围内**的经验。跨项目/用户偏好类信息（例如"用户是验证工程师，偏好简洁回答"）属于 Claude harness 级别的 auto memory，不应写入 workflow memory。

换个 repo 就不再成立的经验 → workflow memory。
跨 repo 仍然成立的偏好 → auto memory。
