# Udify iter7 深度研究设计

日期: 2026-08-13 | 基线: iter6 交付（宣称 801 passed, 2 skipped）
实测基线: **800 passed, 1 failed, 2 skipped**（`test_proposer_budget_exhausted_emits_budget_trace` 红）
代码规模: `udify/` 30,787 行 / `tests/` 11,362 行

---

## 0. 为什么是 iter7：一个比任何功能缺口都严重的结构性问题

iter7 的研究不能再按"下一批功能"来设计，因为实测发现了一个**跨两轮迭代重复发生的系统性失效模式**。

### 0.1 实测取证：孤儿簇（orphan cluster）

对关键公共符号做"生产调用者 vs 测试文件"计数（`grep -rn` 排除自身定义，`udify/` 与 `tests/` 分开统计）：

| 符号 | `udify/` 引用 | 专属测试文件 | 判定 |
|---|---|---|---|
| `GateOrchestrator` | **0** | 1 | 孤儿 |
| `run_gates` | **0** | 1 | 孤儿 |
| `resolve_targets_grounded` | **0** | 1 | 孤儿 |
| `run_by_engine` | **0** | 1 | 孤儿 |
| `process_intent_timed` | **0** | 1 | 孤儿 |
| `execute_sandboxed` | **0** | 1 | 孤儿 |
| `graph_from_manifests` | 2 | 0 | 已接线 ✅ |
| `build_seatbelt_profile` | 4 | 1 | 已接线 ✅ |
| `ScriptAnalyzer` | 3 | 1 | 已接线 ✅ |
| `ClarificationRequest` | 12 | 1 | 簇内引用 ⚠️ |
| `DeliveryTier` | 15 | 1 | 簇内引用 ⚠️ |

**六个符号有专属测试、有完整实现、有 ruff/mypy 通过，生产调用者为零。**

关键细节：`DeliveryTier`(15) 和 `ClarificationRequest`(12) 引用数很高，但这些引用**全部来自孤儿模块内部互引**。它们构成一个自洽的、互相调用的模块簇，整簇没有任何从 CLI/API 主路径进入的入口。

> **这是本轮最重要的技术判断**：朴素的"是否被 import"或"引用计数 > 0"检查会给这个孤儿簇开绿灯。唯一能抓住它的是**从入口点出发的可达性分析**（reachability from entrypoints），不是 import 计数。这一点直接决定了 W1 的技术选型。

### 0.2 失效模式的历史轨迹

| 迭代 | PRD 承诺 | 实际交付 | 接线 |
|---|---|---|---|
| iter4 | 发现「第一个 Boss 改错 Hero」致命 bug | 记录缺陷 | — |
| iter5 | PR3「接入主路径」×5 条线 | 数据结构 + 逻辑 + 测试 | **全部展期** |
| iter6 | M1-PR2 / M2-PR1 / M2-PR2 接线 | GateOrchestrator + fixture + sandbox 逻辑 | **仅 M2-PR3 落地** |
| iter7 | ← 现在 | | |

**「让第一个 Boss 更难」改错 Hero 这个 bug，在三份连续 PRD 里被宣布修复，至今仍活在主路径上**——因为 `resolve_targets_grounded` 从未被 `pipeline.py` 调用。

测试数从 759 → 801 增长（+42），但**产品行为零变化**：新增测试测的是孤儿模块，不是主路径。

### 0.3 为什么现有红线拦不住

ITERATION-PLAN-2026-08 红线 #10 是"新增代码全部带测试与类型注解，无幻觉资产"。这条红线对孤儿簇**完全失效**——孤儿模块恰恰是有测试、有类型注解的。

缺的那条检查是：**「无调用者的模块不许合并」**。

红线 #10 检查"有没有测试"，但真正要检查的是"有没有被主路径调用"。这是 iter7 必须补上的结构性缺口。

### 0.4 附带发现：一个真实的可观测性缺陷

`tests/cognition/test_intent_trace.py::test_proposer_budget_exhausted_emits_budget_trace` 当前失败：

```
assert result.trace.degradation_reason.value == "BUDGET_EXHAUSTED"
E  AssertionError: assert 'NO_KEY' == 'BUDGET_EXHAUSTED'
```

降级原因的判定优先级有误：无 Key 检查短路了预算耗尽检查。后果是**预算耗尽这一事件在生产中永远不可见**——运维看到的永远是 NO_KEY。这违反 iter6 确立的「诚实降级」原则（不能用一个降级原因掩盖另一个）。

---

## 1. iter7 的研究命题

iter7 **不研究新功能**。北极星是：**零新模块，全部接线，并建立结构性防复发机制**。

研究要回答的是：接线过程中会暴露什么真问题，以及如何让这个失效模式在结构上不可能再发生。

### W1 — 接线的结构性强制（WIRING-ENFORCEMENT）

**缺口**：红线 #10 只查"有测试"，查不出孤儿簇；无任何机制阻止"逻辑落地、接线展期"再次发生。

**研究目标**：
- 可达性分析的真实技术选型：`import-linter` 契约类型（layers / independence / forbidden）能否表达"必须被调用"？不能则需要什么补充？
- `vulture` / `deadcode` 的误报特征与框架感知（FastAPI 路由、pytest fixture、Protocol 实现都是"看似无调用者"的合法模式）
- 孤儿簇（互引但整簇不可达）的检测算法：入口点定义 → import graph → 可达闭包 → 差集
- CI 门禁的渐进式启用策略（一天内阻塞会瘫痪存量）
- 允许列表（allowlist）的治理：什么模块可以合法地暂时无调用者，如何强制它带过期日期

**接地要求**：必须基于 `import-linter` 官方契约类型文档的真实能力边界，不能臆造契约语义。

### W2 — 引用接地的正确性（REFERENCE-GROUNDING）

**缺口**：主路径仍用关键词表，「第一个 Boss」会命中 Hero。这是**产品级致命缺陷**，也是接线后第一个要验证的行为。

**研究目标**：
- 序数/最高级引用（"第一个"/"最强的"/"最后一个 Boss"）的确定性接地算法：排序键从哪来（db_index？params？troops 出现序？），歧义如何定义
- 语法约束解码（grammar-constrained decoding）在实体消歧上的真实增益与代价
- schema 设计对抽取可靠性的影响（PARSE 类工作的结论）
- "格式税"（format tax）：约束解码的性能损失究竟来自采样约束还是 prompt 层
- 消歧失败时产 `ClarificationRequest` 而非猜测的判定阈值
- 无 LLM 时纯规则能接地到什么程度（能力矩阵的诚实边界）

**接地要求**：基于 `tests/fixtures/rpgmv/minimal/` 的真实结构（Slime/BossA/BossC 的 params 与 db_index），不能臆造 fixture。

### W3 — 模型路由与成本护栏（MODEL-ROUTING）

**缺口**：`LLMClient` 全项目仅在 `value_function.py:259` 实例化一处，意图路径完全没有 LLM。COG-LLM-01/02/03 三个任务 ID 从未落地。

**研究目标**：
- 2026-08 当前 Claude 模型族的真实定价与能力分层，意图解析这类"短输入、结构化短输出"任务的正确档位
- prompt caching / batch API 的适用性（意图解析是低延迟交互，batch 不适用；caching 对固定 schema 前缀有效）
- 本地模型路径：llama.cpp GBNF 语法约束 vs MLX 的能力差异——这决定"无 Key 时能否有 LLM 级接地"
- 预算护栏的真实设计：每 job 调用上限、token 上限、超时降级，以及**降级原因的正交记录**（直接对应 §0.4 缺陷）
- 三源隔离（user instruction / game content / tool output）在真实 prompt 组装中的落地形态

**接地要求**：定价与模型 ID 必须核对官方文档；本地模型能力必须区分 llama.cpp 与 MLX 的真实差异。

### W4 — 流式可观测性（STREAMING-OBSERVABILITY）

**缺口**：iter6 的 V2 研究了 SSE 但**从未交付**；API 至今 `grep StreamingResponse` 零命中。前端只能 1s 轮询，看不到"正在感知第 N 个文件"。

**研究目标**：
- SSE vs WebSocket 在本产品（单向、进度推送、单用户回环）的选型定论
- 断连恢复：`Last-Event-ID` 头 + 事件 `id:` 字段的真实契约，与现有 `job_events` 表（append-only、有 seq）的天然对应
- 心跳与代理超时（`: heartbeat` 注释行的间隔）
- 与 TanStack Query 的集成模型：SSE 推送如何与 query cache 协同（invalidate vs setQueryData）
- 回压与前端渲染：阶段卡片、内联错误、澄清请求弹窗
- 降级：SSE 不可用时回退轮询的判定

**接地要求**：基于现有 `job_events` 表 schema 与 `web/lib/api/` 的 envelope 解码层，不能另起炉灶。

### W5 — 验证的诚实分级（VALIDATION-HONESTY）

**缺口**：`run_by_engine` 是孤儿，主路径仍走旧 `run(graph)`，引擎分派是死代码；「探针 6/6 通过」的含金量存疑。

**研究目标**：
- 自动程序修复（APR）领域的补丁验证纪律：fail-to-pass / pass-to-pass 双向断言如何映射到 Mod 场景（"改动生效"+"没改坏别的"）
- Godot headless 的真实 CI 形态（`--headless` 标志组合、GUT/gdUnit4 的 CLI 与 JUnit XML 导出）
- RPGMV 的可验证边界（NW.js 非 headless 的现实约束）
- 引擎覆盖矩阵的诚实声明：NATIVE_HEADLESS / AUTOMATED_NON_HEADLESS / UNVERIFIABLE 各自的证据强度
- 回归安全：Patch 应用后"未被意图涉及的实体必须逐字节不变"如何断言

**接地要求**：Godot 标志与测试框架 CLI 必须核对官方/社区真实用法。

### W6 — 补丁噪声与序列化保真（PATCH-FIDELITY）

**缺口**：`PATCH-SYN-10` 自批次 5B 登记后未修复——ini 重写产生同值 remove/add 噪声行（`Defense=10` 一删一增），污染 diff 审阅体验。

**研究目标**：
- 格式保持型序列化（format-preserving serialization）：未修改行必须逐字节不变的实现策略
- ini / JSON 各自的保真难点（键序、缩进、尾随空白、编码）
- 与审阅 UI 的关系：噪声行如何破坏"最小可信 diff"这一产品承诺
- 与 W5 回归断言的耦合：字节级不变性本身就是最强的回归断言

**接地要求**：基于 `patch_executor.py` 真实序列化路径与批次 5B 记录的真实噪声样例。

---

## 2. 研究纪律（继承 iter2-iter6，iter7 强化"接线诚实"）

1. **不臆造契约**：工具能力边界、模型定价、协议字段必须 grounding 在官方文档。
2. **可达性优先于覆盖率**：任何"已完成"声明必须能回答"主路径哪一行调用它"。
3. **诚实 fail-closed**：安全/验证/接地相关宁可拒绝也不静默降级；降级原因必须正交、不互相掩盖。
4. **零新模块红线**：iter7 研究产出若指向"新建模块"，必须先证明现有模块无法承载。
5. **产物落盘**：研究报告与 PRD 入 `docs/research-2026-08-iter7/`。

---

## 3. 与既有文档的关系

- 本文不取代 `ITERATION-PLAN-2026-08.md`（仍为活跃北极星），而是为其**批次 7** 提供研究依据。
- §0 的孤儿簇发现需回写 ITERATION-PLAN-2026-08 §9 执行日志，并新增红线 #16。
- 新任务 ID（WIRE-01..06、FIT-01..04、SSE-01..04、PATCH-SYN-10 复活）登记进 `MODULE-ATTACK-MAP-v3.md` §21。
