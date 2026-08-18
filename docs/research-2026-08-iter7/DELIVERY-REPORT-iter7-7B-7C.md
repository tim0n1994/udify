# Udify iter7 批次 7B + 7C 交付报告

日期: 2026-08-14 | 范围: **M2 接地接线 + M3 闸门/验证接线 + M5 降级正交化 + M6 SSE 断连恢复**
基线: 7A 交付后 842 passed → 交付后 **860 passed / 0 failed** / 2 skipped
授权边界: 未 commit / 未 push / 未部署

---

## 1. 核心成果：三轮未修的致命 bug 被真正修复

### 1.1 真实根因（与前三份 PRD 的归因都不同）

前三轮 PRD 把「让第一个 Boss 更难 → 改错 Hero」归因为「接地算法未接线」。接线时发现根因更深一层：

```python
# udify/core/planning/action_space.py（修复前）
for node in graph.nodes[:10]:
    if intent.priority_nodes and node.id in intent.priority_nodes:
        pass          # ← 两个分支都是空的
    else:
        pass
```

**规划层用来约束目标的 `priority_nodes` 机制是一个空操作**。动作空间对前 10 个节点无差别生成修改操作。这意味着：即使接地算法 100% 正确，规划层也不会看它。

因此这个 bug 有两个必须同时修的断点：

| 断点 | 位置 | 修复 |
|---|---|---|
| 接地结果到不了规划层 | `pipeline.py` 未调用 `resolve_targets_grounded` | M2-PR1 接入第 4b 步 |
| 规划层不看接地结果 | `action_space.py` 的 `priority_nodes` 是空操作 | M2-PR1 实现真实过滤 |
| 中途丢失 | `planner.plan()` 用 `Intent(description=...)` 重建意图，丢弃 `priority_nodes` | 改走 `plan_with_intent` |

第三个断点尤其隐蔽：即使前两处都修好，`plan()` 内部重建 Intent 也会把接地结果丢掉——接线断在任何一环都等于没接。

### 1.2 修复前后的实测对比（真实 RPGMV fixture）

| | 规划层实际触碰的节点 |
|---|---|
| **修复前** | `Harold`、`Therese`、`Slime` ← 两个玩家角色 + 小怪，**BossA 根本不在其中** |
| **修复后** | `BossA` |

修复前的行为比"改错 Hero"更糟：它改的是两个玩家角色**加上**一个小怪，唯独没改目标 Boss。

连续 5 次运行结果一致（成功判据 #1「同一意图连续运行得到稳定 Patch」）——已接地目标不再走 `random.random() < 0.3` 随机门。

---

## 2. 交付内容

### M2 — 接地接入主路径（WIRE-01..02）

- `pipeline.py` 第 4b 步调用 `resolve_targets_grounded`；歧义时记录警告而非猜测。
- `action_space.py` 实现 `priority_nodes` 真实过滤 + 接地目标确定性产动作。
- `pipeline.py` 改走 `planner.plan_with_intent` 保住接地结果。
- `tests/core/test_pipeline_grounding.py`：6 测试，含**反证测试**（不接地时确实扩散到玩家角色，证明这条线值得存在）。

### M3 — 闸门编排与验证分派接线（WIRE-03..05）

- `job_runner.approve()` 的 validating 阶段调用 `GateOrchestrator.run_gates`，产出 `JobVerdict`。
- 降级铁律落地：`final_tier` 为 `NONE` 时拒绝打包交付（`JOB_GATE_BLOCKED`）。
- `_run_probe_by_engine`：按引擎分派探针，每份报告都带**诚实的 `engine_coverage`**：
  - Godot（且存在 probe 脚本）→ `run_by_engine` 真跑，`NATIVE_HEADLESS`
  - RPGMV → `AUTOMATED_NON_HEADLESS`（NW.js 无真 headless）
  - 其它 → `UNVERIFIABLE`
- `report.json` 新增 `gate_verdict`（含每道闸门的 evidence 与 tier）与 `engine_coverage`。

### M5-PR1 — 降级原因正交化（COG-LLM）

7A 只做了半截（调换判定顺序）；本轮按研究结论 W3.3 完成正交化：

- `IntentDecisionTrace` 新增 `degradation_reasons` 元组 + `_REASON_PRIORITY` 主因优先级表。
- `__post_init__` 让单值主因与集合双向自洽，**既有构造点全部向后兼容**。
- `llm_intent.propose` 改为独立判定凭证与预算，全部成立的原因都记录。

实测：无 Key + 预算耗尽时，`degradation_reason=BUDGET_EXHAUSTED`，`degradation_reasons=['BUDGET_EXHAUSTED','NO_KEY']`——**两个事实同时可见**，不再互相掩盖。

### M6 — SSE 断连恢复（SSE-01..04）

发现 SSE 端点其实已注册（iter4 交付），真实缺口是研究 W4.2 指出的那条：

- **无 `id:` 字段**：EventSource 会自动重连，但无从告知断点，断连期间事件永久丢失。
- **不读 `Last-Event-ID` 头**：只认 `?after_seq=` 查询参数，而浏览器自动重连发的是请求头。

修复：每条事件带 `id:`（= `progress_events.seq`）、发 `retry:` 提示、`_route` 优先读 `Last-Event-ID` 头并与查询参数取大（不回退重放），非法头部值忽略而不中断连接。

**零新增存储**——`progress_events` 本就 append-only 带单调 seq，断连补发直接映射 `WHERE seq > :last_id`。

`tests/api/test_sse_resume.py`：11 测试。

---

## 3. 门禁验证（全部为 CI 同款命令）

| 门禁 | 结果 |
|---|---|
| pytest | **860 passed, 2 skipped, 0 failed** |
| 覆盖率 | **69.75%**（门槛 62%） |
| ruff check（全树） | All checks passed |
| ruff format（全树） | 205 files already formatted |
| mypy（CI blocking 15 文件） | Success: no issues |
| 可达性门禁 | 退出码 0 |
| UdifyBench 10 golden cases | 4 passed |
| bench-gate 退化检测 | PASS，9 项指标 delta 全为 0 |

**CI 现在是真绿的**——7A 遗留的 74 个未格式化文件已随本轮全树格式化清零（另修 7 个 lint 错误：2 个我引入的 SIM105，5 个前序存量 B017/C408）。

---

## 4. 可达性门禁三次证明了自己

门禁在本轮**三次**主动拦下过期断言，每次都是接线真实生效的独立证据：

1. M2 接线后 → `target_resolver` 不再是孤儿，旧断言失效。
2. M3 接线后 → `run_by_engine` 不再是孤儿，旧断言失效。
3. 模块变可达后 → 其**内部**死符号（`needs_clarification`、`is_combatant`）第一次暴露。

第 3 点是意料之外的收益：孤儿模块内部的死代码此前被整模块的不可达性"遮蔽"，接线反而让它们浮出水面。

孤儿数：147 → **143**（44 模块 → 39 模块）。基线已重算。

---

## 5. 未完成与风险（不改写成功定义）

1. **143 条孤儿仍只冻结未清偿**，2026-11-13 到期。iter7 只清了主路径关键项。
2. **M5-PR2/PR3 未做**：LLM 意图路径接入（Haiku 4.5 + prompt caching + 本地 llama.cpp GBNF）与三引擎对照报告仍欠。`LLMClient` 至今仅在 `value_function.py` 一处实例化。
3. **M6-PR2 前端未做**：EventSource 接入 + `setQueryData` 协同 + 轮询降级属于 web/ 侧，本轮只完成后端契约。
4. **M4 的 pass-to-pass 断言未纳入 UdifyBench**（M3-PR4）：字节保真已具备（7A），但 golden case 尚未逐条加上「意图外实体逐字节不变」断言。
5. **`_JobGateContext` 的部分闸门输入是保守常量**（`sandboxed=True`、`dependency_conflicts=[]`）——闸门已接线且会真实裁决，但这两项的真实数据源（沙箱执行状态、安装期依赖图）需 `execute_sandboxed` 与 install 路径接线后才能填真值。这是**诚实的半接线**，已在代码注释标注。
6. 未 commit/push。
