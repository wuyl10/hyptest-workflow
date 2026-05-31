# 覆盖检查与去重口径

本文用于统一 `hyptest-workflow` 中“类似测试点是否已覆盖”和“case 是否重复”的执行口径。它补充 `SKILL.md`，但不替代其中的硬规则。

## 1. 两类问题要分开看

- `test_point` 级覆盖检查：
  - 关注仓库里的 `test_point/**/*.md` 是否已经存在相近测试点。
  - 判断对象是“怀疑点 / 场景轴 / 断言目标”。
- `case` 级去重检查：
  - 关注仓库里的 `ai_test_cases/*.c` 与 `manual_test_cases/**/*.c` 是否已经有相近或重复实现。
  - 判断对象是“场景构造 / 断言结构 / 函数名唯一性”。

不要把这两类检查混成一件事。

## 2. 覆盖范围口径

普通 prompt 一般不需要手动填写 `coverage_scope`。workflow 会根据任务目的推导覆盖范围：补已有条目走局部测试点检查，新增测试点或跨文件排重走全仓测试点检查。只有在高级排查、复现实验或需要覆盖默认行为时，才显式指定 `coverage_scope=file/repo`。

- `coverage_scope=file`
  - 只检查当前 `test_point_file` 或指定 `### PnX`。
  - 适合“补已有测试点模式”。
- `coverage_scope=repo`
  - 除当前目标外，还要扫描全仓 `test_point/**/*.md`。
  - 适合“新增测试点模式”以及用户明确要求“查类似测试点有没有覆盖 / 其它文件里有没有重复”。

默认规则：

- 补已有 `### PnX`：默认 `coverage_scope=file`
- 新增测试点 / `new-case-only` / 跨文件排重诉求：默认 `coverage_scope=repo`

说明：

- `case` 去重始终是 repo 级，不因 `coverage_scope=file` 而降级。

## 3. test_point 级覆盖检查

目标：

- 确认类似测试点是否已经存在
- 确认旧点是否已经覆盖当前怀疑点
- 确认本轮是不是只在旧点基础上换了名字

推荐命令：

```bash
rg -n "<axis1>|<axis2>|<axis3>" test_point/
```

必要时再补更具体的组合词，例如：

```bash
rg -n "memblock|retry|refault|upper-tail|boundary\\+15|BYTE7|mask" test_point/
```

命中后至少比较这三项：

- 怀疑点是否相同
- 场景轴是否相同
- 断言目标是否真的新增了可观测语义

可接受的新增理由示例：

- 旧点只覆盖 byte 级，本轮新增的是 halfword/word 级尾窗语义
- 旧点只覆盖当前容器文件，本轮发现全仓没有同一怀疑点
- 旧点虽然相近，但断言目标从“trap 元数据”扩展到了“boundary overlay 保真”

不可接受的新增理由示例：

- 只是换了更长的函数名
- 只是把同一场景换了页面枚举或常量值
- 只是把旧点文字改写成另一种描述

## 4. case 级相似检索

目标：

- 找到全仓最接近的已有 case，作为结构和断言参考
- 判断当前打算新增的 case 是否已经有高度相似实现

推荐命令：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/find_similar_cases.py \
  --repo-root $HYPTEST_HOME \
  --from-file <test_point_file> \
  --query <axis> --query <axis> \
  --show-snippet \
  --limit 5
```

复杂场景可用：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/find_similar_cases.py \
  --repo-root $HYPTEST_HOME \
  --from-file <test_point_file> \
  --query <axis> --query <axis> \
  --assert-only \
  --emit-reading-pack \
  --limit 3
```

注意：

- `find_similar_cases.py` 的搜索范围始终是全仓 `ai_test_cases/*.c` 与 `manual_test_cases/**/*.c`
- `--from-file` 只负责提取查询词，不会把搜索范围限制在当前 `test_point_file`

## 5. 精确唯一性检索

相似检索不能替代唯一性检索。

推荐快路径：

```bash
python3 $HYPTEST_WORKFLOW_SKILL_HOME/scripts/check_case_uniqueness.py \
  --repo-root $HYPTEST_HOME \
  --case <case_name> \
  --expect absent \
  --json
```

说明：

- `--expect absent` 用于写新 case 前，要求 `ai_test_cases/*.c` 和 `manual_test_cases/**/*.c` 中没有同名 `bool <case_name>(...)` 定义。
- 该脚本默认复用 `repo_evidence_index.py` 的缓存；如果 preflight pack 已经构建过索引，后续唯一性检查应是 cache hit，避免每次在 NFS 上冷扫源码。
- 写完 case 后仍由 `case_postcheck_pack.py` / `case_gate_pack.py` 复核 `definition_unique=true`，这是后置确认，不替代写前拦截。

仅在脚本不可用或需要人工二次核实时使用 `rg` 备用命令：

```bash
rg -n "^\s*(?:static\s+)?bool\s+<case_name>\s*\(" ai_test_cases manual_test_cases test_register.c
```

不要把备用命令写成 repo root 全量扫描；精确唯一性只需要覆盖 case 源目录和注册表。

结论规则：

- `check_case_uniqueness.py --expect absent` 通过，或备用 `rg` 无命中：可以作为“函数名未被占用”的证据
- 检查有命中：
  - 若是已有定义，禁止重复造同名 case
  - 若只在注释注册中命中，也要继续核对定义是否已存在

## 6. 输出时至少要说清楚

最终摘要里至少应能回答：

- 本轮覆盖范围是自动推导还是显式指定
- 是否做了全仓 `test_point` 覆盖检查；若没有，为什么只做局部检查
- 是否发现相近旧测试点
- 是否做了全仓 case 相似检索
- 唯一性检索证据是什么
- 最终为何仍选择新增 / 复用 / 不新增

## 7. 简版执行模板

### 补已有测试点

1. 锁定目标 `### PnX`
2. 默认按局部范围检查当前条目/文件内是否已覆盖
3. 用全仓 `find_similar_cases.py` 检查相似 case
4. 用 `check_case_uniqueness.py --expect absent` 检查函数名唯一性
5. 再决定补 case、复用 case 或不新增

### 新增测试点

1. 默认按全仓范围扫描 `test_point/**/*.md`
2. 判断是否已有近似测试点
3. 再做全仓 case 相似检索
4. 再做函数名唯一性检索；命名确定后先用 `check_case_uniqueness.py --expect absent`
5. 只有在“测试点未覆盖 + case 未重复”时才新增
