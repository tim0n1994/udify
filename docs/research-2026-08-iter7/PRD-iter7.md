# Udify iter7 PRD —— 接线迭代：让已建成的能力真正进入主路径

日期: 2026-08-13 | 基线实测: **800 passed / 1 failed / 2 skipped**；`udify/` 30,787 行 / `tests/` 11,362 行
研究依据: `RESEARCH-DESIGN-iter7.md` + `DEEP-RESEARCH-REPORT-iter7.md`
状态: 待评审

---

## 0. iter7 的产品目标

**一句话**：iter7 不造任何新能力。它把已经建成、已经有测试、但**生产调用者为零**的六个模块接进主路径，修掉接线后立刻暴露的三个真缺陷，并建立让"逻辑落地、接线展期"在结构上不可能再发生的门禁。

### 0.1 为什么必须是这一轮

实测取证（`grep` 生产引用 vs 测试文件）：

| 符号 | `udify/` 引用 | 测试文件 | 状态 |
|---|---|---|---|
| `GateOrchestrator` / `run_gates` | **0** | 1 | 孤儿 |
| `resolve_targets_grounded` | **0** | 1 | 孤儿 |
| `run_by_engine` | **0** | 1 | 孤儿 |
| `process_intent_timed` | **0** | 1 | 孤儿 |
| `execute_sandboxed` | **0** | 1 | 孤儿 |

`DeliveryTier`(15 引用) 与 `ClarificationRequest`(12 引用) 看似活跃，但引用**全部来自孤儿模块内部互引**——这是一个自洽的**孤儿簇**，整簇没有从 CLI/API 进入的入口。

> **2026-08-13 实测修正（M1 交付后回写）**：上表是对 iter5/iter6 点名符号的**抽样**。
> M1 门禁建成后做全量扫描，真实规模是 **147 条 = 44 个孤儿模块 + 103 个孤儿符号**，
> 约为抽样估计的 25 倍。整片 `tool_gateway`、`ingestion`、`real_merge`、`evaluation`、
> 以及 cognition 的 LLM 栈都不可从 CLI/API 到达。
> 影响：§2 的"六个模块全接线"目标**不成立**——iter7 只可能清掉主路径关键路径上的那批，
> 其余 147 条已冻结进 `.udify-reachability.toml`（2026-11-13 到期）强制季度复审。

历史轨迹：

- iter4 发现「让第一个 Boss 更难 → 改错 Hero」致命 bug
- iter5 PRD 的 PR3「接入主路径」×5 条线 → **全部展期**
- iter6 PRD 的 M1-PR2 / M2-PR1 / M2-PR2 接线 → **仅 M2-PR3 落地**
- 测试数 759 → 801（+42），**产品行为零变化**

**该 bug 在三份连续 PRD 中被宣布修复，至今仍活在主路径上。**

### 0.2 现有红线为何拦不住

红线 #10 是"新增代码全部带测试与类型注解，无幻觉资产"。孤儿簇**恰恰满足**这条红线——它有测试、有类型注解、ruff/mypy 全过。

缺的检查是：**「无主路径调用者的模块不许合并」**。iter7 必须补上。

---

> **2026-08-14 交付回写**：7A/7B/7C 已交付，见 `DELIVERY-REPORT-iter7-7A.md` 与
> `DELIVERY-REPORT-iter7-7B-7C.md`。**M2 的根因与本 PRD 的假设不同**：不只是「接地算法
> 未接线」，更深一层是 `action_space.py` 里 `priority_nodes` 过滤是一个空操作
> （两个分支都是 `pass`），且 `planner.plan()` 会重建 Intent 丢弃接地结果——三处断点
> 必须同时修。实测修复前规划触碰的是 `Harold`/`Therese`/`Slime`，**BossA 根本不在其中**。
> 剩余欠账：M5-PR2/PR3（LLM 意图接入）、M6-PR2（前端 EventSource）、M3-PR4
> （pass-to-pass 断言入 UdifyBench）。

## 1. 北极星与验收标准

### 1.1 北极星

```
在浏览器提交「让第一个 Boss 攻击力翻倍」
  → 主路径调用 resolve_targets_grounded，选中 BossA（不是 Hero、不是 Slime）
  → 五道闸门经 GateOrchestrator 编排运行，产出 JobVerdict.final_tier
  → 探针经 run_by_engine 按引擎分派，报告带 engine_coverage 诚实分级
  → diff 中只有 BossA.params[2] 一处改动，无同值噪声行
  → pass-to-pass 断言：Slime/BossC/全部 Actor 逐字节不变
  → SSE 实时推送每个阶段，断连重连自动补发缺失事件
  → CI 拒绝任何新增的无调用者模块
```

### 1.2 验收标准（逐条可验证）

| # | 标准 | 验证方式 | 可谈判 |
|---|---|---|---|
| 1 | 六个孤儿符号全部有主路径调用者，可达性检查通过 | `scripts/check_reachability.py` 退出码 0 | ❌ 不可谈判 |
| 2 | 「第一个 Boss 攻击力翻倍」端到端选中 BossA，Hero/Slime 字节不变 | E2E 测试 + 字节级断言 | ❌ 不可谈判 |
| 3 | CI 阻塞新增孤儿；存量 6 个进带过期日期的 baseline | CI 红/绿 + baseline 文件 | ❌ 不可谈判 |
| 4 | `degradation_reason` 改为原因集合，当前红测试转绿 | `pytest tests/cognition/` 全绿 | ✅ |
| 5 | ini/JSON patch 无同值噪声行；未修改字节逐字节不变 | diff 快照测试 | ✅ |
| 6 | SSE 推送阶段事件，`Last-Event-ID` 断连补发正确 | 契约测试 + 手动断连 | ✅ |
| 7 | `ValidationReport` 带 `engine_coverage`，UI 不把 UNVERIFIABLE 显示为绿 | API 契约测试 + UI 测试 | ✅ |
| 8 | 全量测试 ≥ 801 且 0 失败，覆盖率不低于基线 | CI | ❌ 不可谈判 |
| 9 | **零新模块**（除 §M1 已论证的可达性脚本） | 人工评审 diff | ❌ 不可谈判 |

---

## 2. 模块切分

六个模块，**M1-M3 为 P0 不可展期**，M4-M6 为 P1。

每个模块的 PR 都必须**同时包含接线与其验证**——不允许再出现"PR1 逻辑、PR2 接线"的切法，因为这个切法正是失效模式的载体。

---

## M1 — 可达性门禁（FIT-01..04）

**缺口**：无任何机制阻止孤儿模块合并。
**研究依据**：W1——`import-linter`（layers/independence/forbidden 三类契约）与 `vulture` 均无法检出孤儿簇，前者是禁止型约束语言，后者以符号级引用为判据而簇内互引即"已使用"。必须自建入口点可达性分析。这是 iter7 **唯一**被允许的新建（符合研究纪律 #4）。

### M1 技术设计

**判定算法**：

```
roots = CLI 子命令处理函数 ∪ FastAPI 路由处理函数（装饰器注册即入口）
reachable = BFS(roots, 边 = import 关系 + 模块级符号引用)
orphans = udify/ 下全部公共符号 − reachable − allowlist
gate: orphans ≠ ∅ → 退出码 1
```

实现约束：stdlib `ast` 做符号与引用抽取，图遍历用 dict-of-sets BFS。**不引入新依赖**（`networkx` 虽在依赖内但非必需）。规模约 60-100 行。

**框架感知（误报处理）**：

| 模式 | 处理 |
|---|---|
| FastAPI 路由处理函数 | 装饰器调用点即 root，纳入 roots 集合 |
| pytest fixture | 只扫 `udify/`，不扫 `tests/` |
| `Protocol` / ABC 实现 | allowlist，且必须有契约测试佐证 |
| `__all__` 公共 API | allowlist，且 docstring 必须写明消费者 |

**allowlist 条目强制三字段**（缺一即 CI 红）：

| 字段 | 约束 |
|---|---|
| `symbol` | 全限定名 |
| `reason` | 豁免理由，禁止空串 |
| `expires` | ISO 日期；**到期未清 = CI 红** |

> 过期日期是本设计的核心。它把"展期"从静默动作变成必须显式续签的动作，直接针对 iter5→iter6 的失效模式。

**渐进启用**：社区共识是一天内阻塞会瘫痪存量。因此支持 baseline 快照——冻结当前 6 个孤儿为已知债务，只阻塞**新增**孤儿；同时这 6 个的 `expires` 全部设为本轮结束日，强制在 M2/M3 清零。

### M1 PR 切分

| PR | 内容 | 验收 |
|---|---|---|
| M1-PR1 | 可达性脚本 + baseline 生成 + allowlist schema + 自测 | 对当前代码库运行，精确报出已知的 6 个孤儿，无误报 FastAPI 路由 |
| M1-PR2 | CI 集成（阻塞新增孤儿）+ 过期日期检查 | 构造一个新孤儿 → CI 红；构造一个过期 allowlist 条目 → CI 红 |

**owned**: `scripts/check_reachability.py`、`.udify-reachability.toml`、`.github/workflows/ci.yml`、`tests/infrastructure/test_reachability.py`

---

## M2 — 接地接入主路径（WIRE-01..02）

**缺口**：`resolve_targets_grounded` 零调用者；`pipeline.py` 无 `resolve_reference` 痕迹。三轮未修的致命 bug 的根因。
**研究依据**：W2——**「第一个 Boss」不需要 LLM**，它是两阶段确定性算法。把它归因为"等 LLM 接入"是错误归因，也是拖三轮的原因之一。

### M2 技术设计

**两阶段接地**（不可合并为一步）：

```
阶段1 语义过滤：全体实体 → 类别子集
                依据 = semantic_tags（SemanticLifter 产出）
阶段2 子集内选择：
      序数（第一个/最后一个）→ 子集内出现序，非全局数组下标
      最高级（最强/最弱）    → 指定数值字段排序
```

关键：`Enemies.json[0]=Slime, [1]=BossA, [2]=BossC`，「第一个 Boss」= **boss 子集内的 index 0** = BossA（全局下标 1）。用全局下标会选中 Slime。这正是 iter6 E2E 测试的断言口径（`db_index=0 in bosses`）。

**"最强"的口径固定**：绑定 `params[2]`（attack），并在 UI 明示口径。理由：「最强」在游戏语义中可指 attack/HP/综合，交给 LLM 自由裁量会导致口径漂移，而口径漂移在回归测试里不可见。

**歧义判定表**（决定何时产 `ClarificationRequest` 而非猜测）：

| 条件 | 判定 |
|---|---|
| 阶段1 子集为空 | 拒绝 + ClarificationRequest：找不到该类别 |
| 阶段2 排序键字段不存在 | 拒绝，**不得回退到数组下标** |
| 最高级引用出现并列第一 | 拒绝 + 列出并列候选 |
| 引用未指明类别 | 拒绝 + 要求澄清 |
| 子集唯一元素 | 直接选中 |

**无 LLM 能力矩阵（诚实声明）**：

| 引用类型 | 纯规则 | 说明 |
|---|---|---|
| 显式命名 | ✅ | 精确匹配 |
| 序数 | ✅ | 两阶段算法 |
| 最高级 | ✅ | 固定字段排序 |
| 模糊描述 | ❌ | 需 LLM 或澄清 |
| 跨语言同义 | ⚠️ | 依赖同义词表覆盖度 |

### M2 PR 切分

| PR | 内容 | 验收 |
|---|---|---|
| M2-PR1 | `pipeline.py` 第 4 步改调 `resolve_targets_grounded`；旧 Intent 无 ReferenceSpec 时走原确定性路径（向后兼容） | 「第一个 Boss 攻击力翻倍」选中 BossA；`Enemies.json[0]` Slime 与全部 Actor 字节不变 |
| M2-PR2 | 歧义判定表落地 + ClarificationRequest 贯通到 API/UI | 并列第一场景产澄清请求而非猜测；UI 呈现候选列表 |

**owned**: `udify/core/pipeline.py`、`udify/core/cognition/target_resolver.py`、`tests/core/test_pipeline_grounding.py`、`tests/e2e/test_e2e_grounding.py`

---

## M3 — 闸门编排与验证分派接入（WIRE-03..05）

**缺口**：`GateOrchestrator`/`run_gates` 零调用者；`run_by_engine` 零调用者，`job_runner.py` 仍 import 旧 `HeadlessRuntimeProbe.run`；`process_intent_timed` 零调用者，延迟不可观测。

### M3 技术设计

**编排接入点**：`JobRunner.process_job` 在规划完成后调用 `GateOrchestrator.run_gates(graph, intent, patch, manifests) -> JobVerdict`，按 `final_tier` 决定安装 / 标注 / 拒绝。

**降级铁律（继承 iter6，不得弱化）**：`final_tier = min(所有阻断闸门的 delivery_tier)`；LATENCY 为横切控制型，只标注 degraded 不阻断；沙箱失败降级到 `STATIC_ONLY`，**不得降级到裸执行**。`NEEDS_CLARIFICATION` 立即暂停，后续闸门 `PENDING`。

**引擎覆盖矩阵（诚实分级）**：

| 引擎 | 等级 | 技术依据 |
|---|---|---|
| Godot | `NATIVE_HEADLESS` | `--headless` 原生支持；GUT/gdUnit4 提供 CLI + JUnit XML |
| RPGMV | `AUTOMATED_NON_HEADLESS` | NW.js 无真 headless |
| 商业未植入 | `UNVERIFIABLE` | 无注入点，仅静态分析 |

Godot headless 的真实标志组合：`--headless --display-driver headless --audio-driver Dummy --disable-render-loop`；**CI 必须先做一次 headless 预导入再跑测试**（两步法），否则资源未导入导致假失败。这是最容易踩的坑。

**pass-to-pass 回归断言（本轮新增的关键纪律）**：

借 APR 领域的补丁验证方法论（SWE-bench 的 fail-to-pass / pass-to-pass 双向断言）：

| APR 概念 | Udify 对应 | 断言 |
|---|---|---|
| fail-to-pass | 意图达成 | `BossA.params[2]` 50 → 100 |
| pass-to-pass | 回归安全 | Slime/BossC/全部 Actor **逐字节不变** |

现有探针只验证"游戏能启动"，不验证"没改坏别的"。**「探针 6/6 通过」若不含 pass-to-pass 断言，含金量有限。**

> 依赖警告：pass-to-pass 的"逐字节不变"断言**依赖 M4 完成**。若 ini 重写仍产生同值噪声，该断言根本无法成立。M4 因此是 M3 的前置，不是并行项。

### M3 PR 切分

| PR | 内容 | 验收 |
|---|---|---|
| M3-PR1 | `JobRunner.process_job` 接入 `run_gates`，按 `final_tier` 分支 | 五道闸门按序运行；沙箱失败降级 STATIC_ONLY 不裸执行；NEEDS_CLARIFICATION 暂停 |
| M3-PR2 | `run_by_engine` 接入，`ValidationReport` 增 `engine_coverage` | 报告带诚实分级；API 契约测试 |
| M3-PR3 | `process_intent_timed` 成为默认入口，阶段耗时进 `job_events` | 时间线显示各阶段真实耗时 |
| M3-PR4 | pass-to-pass 回归断言纳入 UdifyBench 全部 golden case | 任一 case 出现意图外字节改动 → 测试红 |

**owned**: `udify/core/orchestration/job_runner.py`、`udify/core/validation/runtime_probe.py`、`udify/core/pipeline.py`、`tests/core/orchestration/test_job_runner_gates.py`、`benchmarks/`

---

## M4 — 补丁保真（PATCH-SYN-10，从 P1 升 P0）

**缺口**：ini 重写产生同值 remove/add 噪声（`Defense=10` 一删一增），批次 5B 登记后未修。
**研究依据**：W6——**这不是体验优化，它是 M3 pass-to-pass 回归断言的前置条件**。若未涉及实体的字节都会变，"逐字节不变"这个最强回归断言无法成立。

### M4 技术设计

**策略**：只重写被修改的行区间，其余字节原样透传——与 `SourceSpan` 的 `byte_start/byte_end` 设计天然吻合。项目已有 `SourceSpan`，缺的是让 emitter 真正基于它做**局部替换**而非全量重写。

**附带清偿一笔旧债**：批次 5B 记录"SourceSpan 只到文件级，`line_start/line_end` 为空，UI 显示 `可定位 SourceSpan 0/2`"。做局部替换时**必须**有行/字节偏移，因此这笔数据质量债被强制解决。两笔债共用一个修复。

**格式保真检查清单**：键序、缩进、尾随空白、行尾符（CRLF/LF）、编码（BOM）。

### M4 PR 切分

| PR | 内容 | 验收 |
|---|---|---|
| M4-PR1 | ini emitter 改局部字节替换 + SourceSpan 补行号/字节偏移 | 改一个键 → diff 恰好 1 行；未修改行字节级相同 |
| M4-PR2 | JSON emitter 同等保真 + UI 显示真实行号证据 | RPGMV JSON 改一个值 → diff 最小；UI 显示 `可定位 SourceSpan 2/2` |

**owned**: `udify/core/execution/patch_executor.py`、`udify/models/source.py`、`web/features/jobs/review/`、`tests/core/execution/`

---

## M5 — 降级原因正交化 + LLM 意图接入（COG-LLM-01..03）

**缺口**：当前红测试 `degradation_reason == 'NO_KEY' != 'BUDGET_EXHAUSTED'`；`LLMClient` 全项目仅 `value_function.py:259` 一处实例化，意图路径无 LLM。

### M5 技术设计

**降级原因改为正交集合**（修红测试的正解，非改断言）：

| 维度 | 取值 | 判定 |
|---|---|---|
| 凭证 | HAS_KEY / NO_KEY | 独立 |
| 预算 | WITHIN_BUDGET / BUDGET_EXHAUSTED | 独立 |
| 延迟 | WITHIN_TIMEOUT / TIMED_OUT | 独立 |
| 结果 | LLM_USED / RULE_FALLBACK | 派生 |

**所有成立的原因都要记录**，显示层按优先级挑主因。当前单值短路导致"无 Key 且预算耗尽"时 BUDGET_EXHAUSTED 被永久掩盖，运维视角下预算耗尽事件不可见。

**模型路由**（2026-08 实时定价核对）：

| 模型 | 输入/输出 $/M | 用途 |
|---|---|---|
| Haiku 4.5 | 1 / 5 | **意图解析默认档** |
| Sonnet 5 | 2 / 10（至 8/31，9/1 起 3/15） | 低置信升级档 |
| Opus 5 | 5 / 25 | 计划批评，非意图解析 |

- **prompt caching**：✅ 采用。schema + 系统指令 + 本体表是固定前缀，命中价为标准输入的 10%。
- **Batch API**：❌ 不采用。意图解析是交互式低延迟路径，batch 是异步非紧急负载手段。

**本地路径（无 Key 红线）**：选 **llama.cpp / Ollama 而非裸 MLX**。MLX 在 Apple Silicon 吞吐更高（部分场景 21%-87%），但**核心栈无 GBNF 等价物**，需外接 outlines/lm-format-enforcer；llama.cpp 的 GBNF 与 JSON schema 是内建能力，逐 token 屏蔽非法 token。**结构化保证优先于吞吐。**

**LLM 的职责边界（三层防御）**：约束解码只挡语法与结构两类失败，语义错误必须靠规则层裁决。因此 LLM 只产**候选 + 置信度**，M2 的确定性算法做**最终裁决**。schema 需为 LLM 优化（扁平、枚举优先、避免深嵌套），而非直接复用内部 dataclass 形状。

### M5 PR 切分

| PR | 内容 | 验收 |
|---|---|---|
| M5-PR1 | 降级原因改集合 + 显示优先级 | 当前红测试转绿；"无 Key 且预算耗尽"两个原因都可见 |
| M5-PR2 | `IntentClassifier` LLM 路径接入 + caching + 预算护栏 | 无 Key 时全部测试不触网全绿；有 Key 时手测 3 条圈外意图 |
| M5-PR3 | UdifyBench `--intent-engine=heuristic\|llm\|local` 三路对照 | 对照报告入 docs，不进 CI 阻塞 |

**owned**: `udify/core/cognition/`、`udify/core/llm_client.py`、`benchmarks/`

---

## M6 — SSE 流式可观测（SSE-01..04）

**缺口**：iter6 V2 研究了 SSE 但从未交付；`grep StreamingResponse` 零命中；前端只能 1s 轮询。

### M6 技术设计

**选型定论：SSE**。单向（服务端推进度）、单用户、127.0.0.1 回环——社区共识明确单向场景 SSE 优于 WebSocket。决定性优势是 **EventSource 内建自动重连**，WebSocket 重连逻辑必须手写。

**断连恢复零新增存储**（本轮最省力的架构契合点）：

```
SSE  id: 字段      ←直接映射→  job_events.seq
Last-Event-ID 头   ←直接映射→  WHERE seq > :last_id ORDER BY seq
```

`job_events` 表已是 append-only 且带 seq（iter4A 设计）。**无需新表、无需事件缓冲区**——这是 SSE 相对 WebSocket 的又一优势（WebSocket 需自建补发机制）。

**工程细节**：

| 项 | 决策 |
|---|---|
| 心跳 | 每 15-30s 发 `: heartbeat` 注释行，防代理超时；本地虽无代理，但可让前端区分"卡住"与"无新事件" |
| 字段 | `event:`（事件名）、`id:`（= seq）、`retry:`（重连毫秒） |
| 前端协同 | 事件到达用 `setQueryData` 局部更新，**不用** `invalidateQueries`（避免每事件打一次 API）；仅终态事件 invalidate 拉完整结果 |
| 降级 | SSE 失败回退现有 1s 轮询；轮询代码已存在，零成本保留 |

### M6 PR 切分

| PR | 内容 | 验收 |
|---|---|---|
| M6-PR1 | `GET /api/v0/jobs/{id}/events` SSE 端点 + Last-Event-ID 续传 | 断连后重连补齐缺失事件，无重复无遗漏 |
| M6-PR2 | 前端 EventSource 接入 + setQueryData 协同 + 轮询降级 | 阶段进度实时刷新；杀掉 SSE 端点后自动回退轮询 |

**owned**: `udify/api/app.py`、`web/lib/api/`、`web/features/jobs/review/`、`tests/api/test_sse.py`

---

## 3. 依赖序与排期

```
M1（门禁）──────────── 可并行，但必须最先合并（否则后续 PR 无门禁保护）
   │
M4（补丁保真）──────── M3-PR4 的前置
   │
M2（接地）───┬──────── 独立
M3（编排/验证）┘─────── 依赖 M4
   │
M5（降级/LLM）───────── 独立，可最后
M6（SSE）─────────────── 独立，可最后
```

| 批次 | 模块 | 预估 | 优先级 |
|---|---|---|---|
| 7A | M1 + M4 | ~1 周 | P0 |
| 7B | M2 + M3 | ~1-2 周 | P0 |
| 7C | M5 + M6 | ~1-2 周 | P1 |

**7A/7B 不得展期。** 若 7C 需展期，必须在 `TECHNICAL-DOCUMENTATION-INDEX.md` 明文记录展期理由与新日期，不许静默。

---

## 4. 红线（继承 15 条，新增 3 条）

继承 ITERATION-PLAN-2026-08 红线 1-15，**新增**：

16. **无主路径调用者的模块不许合并**——可达性检查是阻塞门禁；allowlist 条目必须带过期日期，到期未清 = CI 红。
17. **不许再用"PR1 逻辑 / PR2 接线"的切法**——每个 PR 必须自带接线与验证。这个切法是 iter5/iter6 失效模式的载体。
18. **不许用"等 LLM"作为确定性缺陷的归因**——「第一个 Boss」是两阶段确定性算法问题，与 LLM 无关。凡声称"需要 LLM 才能修"的缺陷，必须先证明纯规则无法解决。

---

## 5. 与既有文档的同步

| 动作 | 目标文档 |
|---|---|
| 孤儿簇发现 + 红线 16/17/18 | `ITERATION-PLAN-2026-08.md` §9 执行日志、§7 红线 |
| 新任务 ID（FIT-01..04、WIRE-01..05、SSE-01..04、PATCH-SYN-10 升 P0） | `MODULE-ATTACK-MAP-v3.md` §21 |
| 可达性门禁作为架构约束 | `ARCHITECTURE-OSS-OPTIMIZED-v3.md` 新增 ADR-v3-011 |
| iter7 研究三件套归档 | `TECHNICAL-DOCUMENTATION-INDEX.md` |

**ADR-v3-011 建议措辞**：入口点可达性检查作为强制架构门禁；`import-linter`（禁止型约束）与 `vulture`（符号级引用）均无法检出孤儿簇，故自建约 60-100 行 stdlib 实现；allowlist 强制过期日期以杜绝静默展期。

---

## 6. 一页纸总结

- **问题**：六个模块有实现、有测试、有类型注解、ruff/mypy 全过，**生产调用者为零**；它们互相引用构成孤儿簇，朴素 import 检查会漏判。三份连续 PRD 宣布修复的「第一个 Boss 改错 Hero」bug 至今仍在主路径上。测试数 +42 而产品行为零变化。
- **根因**：红线 #10 只查"有测试"，查不出"无调用者"；"PR1 逻辑 / PR2 接线"的切法让接线可以被静默展期。
- **动作**：M1 建可达性门禁（唯一被允许的新建，因现有工具证明无法承载）→ M4 补丁保真（M3 前置）→ M2 接地接线（纯确定性算法，不需 LLM）→ M3 闸门与验证分派接线 + pass-to-pass 回归断言 → M5/M6 降级正交化与 SSE。
- **判据**：§1.2 九条，其中 #1/#2/#3/#8/#9 不可谈判。
- **纪律**：零新模块；每个 PR 自带接线与验证；allowlist 必须带过期日期。

> iter7 的成功不看新增了什么，看**孤儿集是否归零**、以及「第一个 Boss」是否终于选对。
