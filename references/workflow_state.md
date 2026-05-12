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
python3 scripts/clean_generated.py --repo-root $HYPTEST_HOME
```

默认不会清 `memory/`。

## Memory

- `memory/` 记录本 repo 范围内的**经验线索**（历史失败现象、debug 路径、发现的 RTL quirk 等），不替代当前源码/日志/`spec_profile`/平台证据。
- 做 `default / manual / compile-only / blocked` 决策时，仍以**本轮证据**为准；memory 只是检索线索。
- 不要默认删除；经验过期改为追加一条 `status=obsolete` 的废弃说明：
  ```bash
  python3 scripts/workflow_memory.py append \
    --repo-root $HYPTEST_HOME \
    --status obsolete \
    --topic <topic> \
    --note "<为什么废弃>"
  ```

常用 CLI：

```bash
# 追加一条经验
python3 scripts/workflow_memory.py append \
  --repo-root $HYPTEST_HOME \
  --topic <topic> \
  --note "<结论 / 现象 / 关键命令>"

# 按 topic 或关键词检索
python3 scripts/workflow_memory.py query \
  --repo-root $HYPTEST_HOME \
  --topic <topic>

# 汇总当前有哪些活跃经验
python3 scripts/workflow_memory.py summarize \
  --repo-root $HYPTEST_HOME
```

## 路径策略速查

查看当前路径推导结果（调试路径相关问题时用）：

```bash
python3 scripts/workflow_paths.py --repo-root $HYPTEST_HOME
```

## 与 Claude auto memory 的分工

本 workflow memory 只覆盖**本 repo 范围内**的经验。跨项目/用户偏好类信息（例如"用户是验证工程师，偏好简洁回答"）属于 Claude harness 级别的 auto memory，不应写入 workflow memory。

换个 repo 就不再成立的经验 → workflow memory。
跨 repo 仍然成立的偏好 → auto memory。
