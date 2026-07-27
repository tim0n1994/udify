# Udify 开源优先架构 v3.0

> 本文在 `VISION.md`、`PLAN.md`、`ARCHITECTURE-v2.md`、`ARCHITECTURE-GAME-MOD-v1.md` 和 `ARCHITECTURE-GAME-MOD-v1.1-REVIEW.md` 基础上，吸收开源生态调研结果，给出下一阶段工程师可执行的优化架构。

---

## 0. v3 架构摘要

Udify v3 的一句话定义：

> **Udify 是一个开源工具编排之上的语义 Patch 编译器。**

它不再把每个能力都内建在核心包里，而是把开源工具接入为受控 capability。核心只负责：

1. 将内容提升为带证据和置信度的 `ContentGraph v3`。
2. 将用户意图编译为可验证、可回滚、可审计的 `CDLPatch v3`。
3. 在成本、风险、质量和人类确认点之间做规划。
4. 将 Patch 安全执行到 VFS、离线文件、运行时 Hook 或 ModPackage。
5. 通过静态验证、运行时探针、意图对齐和社区反馈形成闭环。

---

## 1. 架构原则

### P1. Diff-first, Evidence-first

所有输出必须是 Patch，所有语义判断必须有证据。

新增要求：

- 每个 graph node 和 property 必须带 `provenance`。
- 每个 LLM 语义标签必须带 `confidence` 和 `evidence_refs`。
- 每个 patch operation 必须能回答“为什么改、改哪里、怎么回滚、怎么验证”。

### P2. Tool-centric, Policy-gated

外部工具通过 Tool Adapter 接入，但每次调用都要过策略网关。

新增要求：

- Tool manifest 描述能力，不描述信任。
- OPA/Policy Engine 决定是否可调用。
- 高风险工具调用必须有 confirmation gate。

### P3. Local-first, Cloud-upgradable

Phase 1 默认本地可运行，Phase 2 才升级到服务化。

本地默认：

- NetworkX/SQLite/文件缓存。
- 本地工具 CLI。
- 简化事件总线。
- Playwright 本地浏览器验证。

生产升级：

- Temporal durable workflow。
- Neo4j + Qdrant。
- Redis Streams。
- gVisor/Firecracker。
- Object Store。

### P4. Human-in-the-loop by Risk

人类确认不是固定步骤，而由风险评分触发。

强制确认场景：

- 文件写入范围超过计划。
- 运行时 Hook。
- 脚本新增危险 API。
- 版权或 license 不确定资产。
- Patch 影响范围跨核心机制。
- 评分函数分歧大。

### P5. Benchmark-driven Autonomy

自动化程度必须由评测结果解锁。

示例：

- 某类 patch 在 UdifyBench 中 95% 通过，允许自动应用到 VFS。
- 90% 以下只能生成计划和预览。
- 80% 以下必须人工审阅。

---

## 2. v3 分层架构

```text
┌────────────────────────────────────────────────────────────┐
│ Presentation                                                │
│ CLI, API, Web UI, ReactFlow Plan Review, Udiface            │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│ ModJob Orchestration                                        │
│ Local Runner, Temporal Worker, LangGraph Agent State         │
│ confirmation gate, retry, compensation, checkpoint           │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│ Core Compiler                                                │
│ Intent Compiler, Perception, Semantic Lifter, Planner,       │
│ Patch Synthesizer, Validator, Evaluator, Feedback Learner    │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│ Secure Tool Gateway                                         │
│ MCP/FastMCP, Tool Registry, Policy Engine, Sandbox, Audit    │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│ Tool Adapters                                                │
│ miu2d, Tree-sitter, Playwright, AssetRipper, QuickBMS,       │
│ FModel, BepInEx/Harmony, Semgrep, Image/Audio/Video tools    │
└───────────────────────┬────────────────────────────────────┘
                        │
┌───────────────────────▼────────────────────────────────────┐
│ State and Knowledge                                          │
│ ContentGraph, CDLPatch, ModSession, ModStack, Memory,        │
│ Graph Store, Vector Store, Object Store, Audit Log           │
└────────────────────────────────────────────────────────────┘
```

---

## 3. 核心数据模型升级

### 3.1 ContentGraph v3

现有 `ContentGraph` 已经能表达节点、边、资产和语义。v3 需要补足生产语义：

```python
ContentGraphV3:
  graph_id: str
  media_type: MediaType
  engine: GameEngine
  version: GraphVersion
  nodes: dict[NodeId, ContentNodeV3]
  edges: list[ContentEdgeV3]
  assets: dict[AssetId, ContentAssetV3]
  overlays: list[GraphOverlayRef]
  indexes:
    structural: StructuralIndexRef
    semantic: VectorIndexRef
    source: SourceIndexRef
  stats: GraphStats
```

新增字段：

| 字段 | 作用 |
|---|---|
| `provenance` | 来源工具、文件、span、hash、工具版本 |
| `confidence` | 语义识别置信度 |
| `evidence_refs` | 支撑语义标签的证据 |
| `license_hint` | 资源版权或授权线索 |
| `sensitivity` | secret、个人数据、NSFW、版权风险 |
| `semantic_tags` | boss、quest_reward、dialog_branch 等领域标签 |
| `runtime_observations` | Playwright/trace/RL probe 观测到的状态 |

### 3.2 SourceSpan

`SourceLocation` 需要升级：

```python
SourceSpan:
  file_path: str
  byte_start: int | None
  byte_end: int | None
  line_start: int | None
  line_end: int | None
  column_start: int | None
  column_end: int | None
  ast_path: str | None
  archive_path: str | None
  asset_id: str | None
  extractor: ToolRunRef
  content_hash: str
```

### 3.3 CDLPatch v3

当前 `CDLPatch` 主要描述图操作。v3 需要覆盖四种执行形态：

| execution_mode | 场景 |
|---|---|
| `graph_only` | 只修改 ContentGraph，用于规划和预览 |
| `file_patch` | 修改 INI/JSON/Lua/DSL/二进制资源 |
| `runtime_hook` | BepInEx/Harmony/Lua hook/Godot autoload |
| `package_overlay` | VFS overlay 或 ModPackage |

```python
PatchOperationV3:
  op_id: str
  op_type: OpType
  execution_mode: ExecutionMode
  target: PatchTarget
  payload: dict
  source_anchor: SourceAnchor
  preconditions: list[Condition]
  postconditions: list[Condition]
  reverse: ReverseOperation
  validation_probes: list[ProbeSpec]
  risk: RiskScore
  cost_estimate: CostEstimate
  provenance: PlanningProvenance
```

### 3.4 ModJob

`ModSession` 表示交互会话，`ModJob` 表示一次可执行的工作流。

```python
ModJob:
  job_id: str
  session_id: str
  intent_id: str
  state: JobState
  graph_version: str
  plan_version: str
  patch_id: str | None
  checkpoints: list[Checkpoint]
  approvals: list[ApprovalRecord]
  tool_runs: list[ToolRunRef]
  audit_chain_head: str
```

状态机：

```text
created
  -> sanitized
  -> perceived
  -> intent_compiled
  -> planned
  -> risk_review_required
  -> approved
  -> applied_to_vfs
  -> statically_validated
  -> runtime_validated
  -> packaged
  -> published
  -> completed

任意状态 -> failed -> compensating -> rolled_back
任意状态 -> paused_for_human
```

---

## 4. 关键模块设计

### 4.1 Intent Compiler

职责：

- 将自然语言意图转为 `StructuredIntent v3`。
- 分解目标、约束、禁止路径、偏好、参考风格。
- 为每个目标生成可验证的 acceptance probe。

管线：

```text
raw intent
  -> InputSanitizer
  -> language detection
  -> intent classifier
  -> reference resolver
  -> constraint extractor
  -> ambiguity detector
  -> intent risk scorer
  -> StructuredIntentV3
```

输出示例：

```yaml
goal:
  type: difficulty_adjustment
  target_scope: boss_and_resource_pressure
constraints:
  - no_numeric_inflation
  - keep_first_hour_accessible
negative_preferences:
  - no_permadeath
references:
  - dark_souls:
      mapped_features: [stamina_pressure, punishment, boss_pattern_learning]
acceptance_probes:
  - boss_hp_not_more_than_1_35x
  - healing_item_drop_rate_reduced
  - tutorial_area_death_rate_threshold
```

### 4.2 Perception and Semantic Lifter

职责分成两层：

1. **Perception Adapter**：读取文件，提取结构。
2. **Semantic Lifter**：把结构提升为游戏语义。

```text
bytes/files/assets
  -> ResourceProvider
  -> Syntax/Schema nodes
  -> Reference graph
  -> Mechanism candidates
  -> Semantic labels with evidence
  -> GameWorldGraph
```

适配器优先级：

| 引擎 | Phase | 策略 |
|---|---|---|
| miu2d | P0 | 自研深度适配 |
| RPG Maker MV/MZ | P0/P1 | JSON/Data/System/Map/Event 结构化解析 |
| Unity | P1 | AssetRipper + BepInEx/Harmony |
| Godot | P1/P2 | PCK + scene/resource parser + autoload |
| Unreal | P2 | FModel/CUE4Parse + pak manifest |

### 4.3 Planner

规划器拆成四层，而不是一个 MCTS 黑箱：

```text
Action Schema Generator
  -> Constraint Filter
  -> Candidate Plan Search
  -> Plan Critic and Ranker
```

各层职责：

| 层 | 主要技术 | 说明 |
|---|---|---|
| Action Schema Generator | 规则 + graph query | 根据目标和子图生成候选动作 |
| Constraint Filter | 类型检查 + policy | 删除明显违法动作 |
| Candidate Plan Search | MCTS/beam search/OR-Tools | 搜索组合 |
| Plan Critic | LLM + rules + historical eval | 打分、解释、风险 |

MCTS 的使用边界：

- 适合多目标、多动作组合、长程影响场景。
- 不适合简单单文件数值修改。
- 每次搜索必须有预算、深度、模拟次数和 cache key。

### 4.4 Patch Synthesizer

职责：

- 把计划转换成 `CDLPatch v3`。
- 生成 reverse patch。
- 生成 static validators 和 runtime probes。
- 选择执行形态：file_patch、runtime_hook、package_overlay。

新增子模块：

| 子模块 | 职责 |
|---|---|
| AnchorResolver | 将 graph target 映射回 SourceSpan |
| PatchEmitter | 生成文件、AST、二进制或 hook patch |
| ReverseBuilder | 生成回滚信息 |
| ProbeGenerator | 生成验证探针 |
| RiskAnnotator | 标注风险和确认点 |

### 4.5 Secure Tool Gateway

必须成为所有外部工具调用的唯一入口。

```text
ToolCallRequest
  -> schema validation
  -> policy decision
  -> sandbox allocation
  -> resource quota
  -> tool execution
  -> output sanitizer
  -> audit append
  -> ToolCallResult
```

策略维度：

- 用户权限。
- session/job 状态。
- tool allowlist。
- 文件路径 allowlist。
- 网络权限。
- CPU/内存/时间预算。
- 输出文件大小。
- 风险等级和人工确认。

### 4.6 Validator and Evaluator

验证分四层：

| 层 | 是否确定性 | 示例 |
|---|---|---|
| Schema validation | 确定 | JSON/INI/Lua 语法、CDL schema |
| Semantic validation | 半确定 | 引用完整性、数值范围、任务链 |
| Runtime probe | 观测 | 游戏启动、场景载入、状态读取 |
| Intent evaluation | 概率 | 是否像魂系、是否不过度修改 |

必须输出：

```python
ValidationReportV3:
  passed: bool
  blocking_errors: list[Finding]
  warnings: list[Finding]
  evidence: list[Evidence]
  probe_results: list[ProbeResult]
  confidence: float
  recommended_action: approve | revise | human_review | reject
```

### 4.7 Feedback and Memory

记忆分四类：

| 类型 | 示例 | 用途 |
|---|---|---|
| user preference | 不喜欢 permadeath | 个性化规划 |
| successful pattern | Boss 难度提升模板 | 复用 |
| failure signature | 某 DSL 命令组合会崩溃 | 避坑 |
| ecosystem signal | 某 ModStack 冲突率高 | 推荐和兼容性 |

---

## 5. 引擎适配架构

### 5.1 EngineAdapter 接口

```python
class EngineAdapter(Protocol):
    engine_id: str
    supported_versions: list[str]

    def detect(self, game_root: Path) -> DetectionResult: ...
    def perceive(self, game_root: Path, options: PerceptionOptions) -> ContentGraphV3: ...
    def get_action_schemas(self, graph: ContentGraphV3) -> list[ActionSchema]: ...
    def emit_patch(self, op: PatchOperationV3) -> FilePatchBundle: ...
    def build_runtime_probes(self, patch: CDLPatchV3) -> list[ProbeSpec]: ...
    def package_mod(self, patch: CDLPatchV3) -> ModPackage: ...
```

### 5.2 miu2d Adapter

必须深做：

- INI/OBJ/NPC/Lua/DSL parser。
- 二进制资源 converter 接入。
- Dashboard schema 对齐。
- Playwright runtime probe。
- 游戏机制 ontology。

### 5.3 RPG Maker MV/MZ Adapter

应作为第二个首攻，因为结构化 JSON 友好：

- `data/Actors.json`
- `data/Enemies.json`
- `data/Skills.json`
- `data/Items.json`
- `data/MapXXX.json`
- `data/CommonEvents.json`
- `js/plugins/*.js`

核心动作：

- 数值调整。
- 事件页修改。
- 对话和奖励修改。
- 插件参数修改。
- 地图事件引用校验。

### 5.4 Unity Adapter

两条路径：

1. **资源导出和离线 Patch**：AssetRipper/AssetStudio。
2. **运行时 Hook**：BepInEx/Harmony。

Unity 的首选策略应是运行时 Hook，因为许多商业 Unity 项目重新打包成本高且法律风险更高。

### 5.5 Unreal Adapter

Phase 2 才做：

- pak/utoc/ucas manifest。
- asset reference graph。
- 蓝图和 DataTable 优先。
- C++ 行为不做自动修改，只做探测和建议。

---

## 6. 工作流架构

### 6.1 本地 MVP Runner

本地 runner 继续用现有 Python 模块，目标是低依赖：

```text
AutomatedModPipeline
  -> EventBus in memory
  -> VFS preview
  -> local cache
  -> local audit log
```

### 6.2 生产 Durable Workflow

生产改用 Temporal：

```text
ModJobWorkflow
  sanitize_intent
  perceive_content
  compile_intent
  generate_plan
  wait_for_approval_if_needed
  apply_to_vfs
  validate_static
  validate_runtime
  package_mod
  publish_or_export
  collect_feedback
```

Temporal Activity 用于所有副作用：

- 文件读取。
- 外部工具调用。
- LLM 调用。
- 浏览器验证。
- 包发布。

### 6.3 LangGraph Agent State

LangGraph 只用于推理型子流程：

- 参考解析。
- 计划批评。
- 失败根因诊断。
- 用户澄清问题生成。

它不负责写文件，不直接调用高风险工具。

---

## 7. 安全架构

### 7.1 风险分级

| 等级 | 示例 | 默认策略 |
|---|---|---|
| R0 | 读取 manifest、解析文本 | 自动 |
| R1 | 修改 VFS 中的配置 | 自动，但记录 |
| R2 | 写入工作区文件 | 需要验证通过 |
| R3 | 执行外部工具、运行脚本 | 沙箱 + 策略 |
| R4 | 运行时 Hook、网络、发布 | 人工确认 |

### 7.2 Tool Lockfile

每个项目应生成：

```yaml
tools:
  tree-sitter-lua:
    version: 0.x
    sha256: ...
  miu2d-converter:
    version: ...
    sha256: ...
    signature: ...
policies:
  allow_network: false
  allowed_roots:
    - game_root
    - workspace_cache
```

### 7.3 Prompt Injection 防线

自然语言意图、游戏文本、脚本注释、README 都可能包含注入内容。

防线：

- 输入分级：user instruction、game content、tool output 严格分离。
- LLM 输出只能生成候选计划，不能越过 schema。
- 工具调用参数由程序构造，不直接使用模型原文。
- 高风险调用必须由 Policy Engine 决策。

---

## 8. 可观测性和质量门槛

每个 `PatchOperation` 必须携带 trace：

```text
trace_id
session_id
job_id
intent_id
plan_id
patch_id
op_id
tool_run_id
graph_version
```

核心 SLI：

| 指标 | 目标 |
|---|---|
| intent_compile_latency_p95 | < 3s |
| incremental_perception_p95 | < 5s for small game |
| plan_generation_p95 | < 15s for simple mod |
| static_validation_pass_rate | > 98% |
| runtime_probe_flake_rate | < 3% |
| patch_rollback_success_rate | 100% |
| cost_per_simple_mod | < $1 |
| cost_per_complex_mod | < $10 |

---

## 9. 架构决策变更

### ADR-v3-001: 工具优先，不重写成熟生态

状态：建议接受。

决策：Unity/Unreal/归档/静态扫描/浏览器验证优先通过开源工具集成。

理由：资源提取是已解决问题，Udify 的差异化在语义和闭环。

### ADR-v3-002: Workflow 二层化

状态：建议接受。

决策：Temporal 管副作用和长任务；LangGraph 管 Agent 推理；Prefect 保留给离线数据流。

理由：Mod 生成需要可回放、补偿、人工确认和幂等。

### ADR-v3-003: Secure Tool Gateway 是强制边界

状态：建议接受。

决策：所有外部工具调用必须经过 schema、policy、sandbox、audit。

理由：MCP 和外部 CLI 能力越强，攻击面越大。

### ADR-v3-004: ContentGraph v3 必须 Evidence-first

状态：建议接受。

决策：所有语义标签和图谱属性必须携带 evidence 和 confidence。

理由：没有证据链，语义图不可调试、不可审计、不可被社区信任。

### ADR-v3-005: Runtime Hook 成为一等 Patch 类型

状态：建议接受。

决策：CDLPatch 支持 file_patch 和 runtime_hook 双执行模型。

理由：Unity/.NET 生态中运行时 Patch 更安全、更可逆、更贴近社区习惯。

### ADR-v3-006: Job 持久化用 stdlib sqlite3 + 文件工件（2026-08）

状态：已接受。

决策：ModJob 状态与事件流存 sqlite3（WAL），工件（graph/patch/vfs 快照/package/report）落 `.udify/jobs/<id>/`；不引入 ORM 与迁移框架，schema_version 表手工管理。

理由：零新依赖满足"本地模式必须成立"红线；事件表同时充当 OBS-01 trace schema，一份数据两用。

### ADR-v3-007: 薄 API 单用户免认证（2026-08）

状态：已接受。

决策：FastAPI + Pydantic v2，默认绑定 127.0.0.1:8765；统一响应信封 `{success,data,error,meta}`；错误体为 ErrorRecord（code=DOMAIN_CATEGORY_DETAIL、owner_module、retryable、suggested_action）。

理由：当前安全模型是本机单用户，认证/多租户是未验证阶段的过早复杂度；信封与错误码沿用已冻结文档中经得起复用的部分。

### ADR-v3-008: 进度通信轮询先行（2026-08）

状态：已接受。

决策：前端以 1s 轮询 `GET /jobs/{id}` 获取进度；SSE/WebSocket（API-06）推迟到轮询被实测证明不够。

理由：最短可用路径；job_events 表天然支持增量拉取。

### ADR-v3-009: 前端栈 Next.js 15 + TS strict + Tailwind 4 + TanStack Query（2026-08）

状态：已接受。

决策：目录 `web/`，pnpm 管理；不引入 Zustand/ReactFlow/Yjs；API client 手写薄封装，不上代码生成。

理由：与既有文档方向一致并做减法——v0 只有审阅切片，无 DAG 编辑、无协作、无复杂客户端态。

### ADR-v3-010: LLM 是可选增强层（2026-08）

状态：已接受。

决策：LLM 仅用于意图解析点位；Anthropic 结构化输出强约束到 StructuredIntent；每 job 调用次数与 token 预算封顶；游戏内容/工具输出只作为数据段（三源隔离）；无 API key 时代码路径完全不触网、全启发式降级。

理由：把"关键词驱动"补成真"意图驱动"，同时不违反"本地必须成立""LLM 只产候选"两条红线。

---

## 10. 与现有代码映射

| v3 模块 | 现有文件 | 状态 | 攻坚方向 |
|---|---|---|---|
| ContentGraph v3 | `udify/models/content_graph.py` | 基础版 | provenance、confidence、SourceSpan |
| CDLPatch v3 | `udify/models/cdl_patch.py` | 基础版 | execution_mode、probe、risk、reverse |
| Intent Compiler | `core/cognition/*` | 初版 | StructuredIntent v3、acceptance probe |
| Semantic Lifter | `core/perception/*` | 缺口 | 语义标签和证据链 |
| Planner | `core/planning/*` | 初版 | action schema、constraint filter、ranker |
| Secure Tool Gateway | `core/execution/tool_registry.py`, `mcp_server.py` | 初版 | policy、sandbox、audit、tool lock |
| Validator | `core/validation/enhanced_validator.py` | 初版 | runtime probe、semantic validation |
| Evaluator | `core/evaluation/intent_alignment.py` | 初版 | benchmark 化、可回归 |
| ModJob | `core/session/session_manager.py`, `pipeline_v2.py` | 缺口 | durable job state |
| Toolchain | `core/toolchain/__init__.py` | 初版 | adapter contract 和真实工具测试 |

---

## 11. 迁移路线

### Step 1: 不破坏现有代码的数据模型扩展

- 新增 `SourceSpan`、`Provenance`、`Confidence`。
- 保持 `to_dict/from_dict` 兼容。
- 新增测试覆盖旧数据可读取。

### Step 2: EngineAdapter 和 ToolAdapter 协议

- 先把现有 parser 包装为 miu2d adapter。
- ToolchainManager 拆为多个 adapter。
- 加 adapter contract test。

### Step 3: PatchOperation v3

- 加 `execution_mode`，默认 `graph_only`。
- 加 `validation_probes`，先为空。
- 加 `risk`，先用启发式。

### Step 4: Runtime Probe

- Playwright 验证 miu2d。
- probe spec 标准化。
- 失败报告归因。

### Step 5: Secure Tool Gateway

- 最先实现本地 policy，不急于完整 OPA。
- 所有外部 CLI 通过 gateway。
- 记录 tool_run audit。

### Step 6: UdifyBench

- 每个 bug fix 都要沉淀成 benchmark。
- 每类 Mod 至少 10 个 golden case 才提升自动化等级。

---

## 12. 最小可行 v3 目标

第一个 v3 MVP 不追求多引擎，而追求“闭环真实”：

```text
miu2d sample game
  + natural language intent
  + semantic graph with evidence
  + patch plan with risk score
  + VFS preview
  + static validation
  + Playwright runtime probe
  + intent alignment score
  + reversible ModPackage
```

验收示例：

1. 输入：“让第一个 Boss 更难，但不要单纯翻倍血量。”
2. 系统定位 Boss 配置、技能、脚本、奖励。
3. 生成 2 到 3 个候选计划。
4. 解释每个计划的风险和体验差异。
5. 应用到 VFS。
6. 静态验证引用和数值。
7. Playwright 启动游戏并确认 Boss 实际状态。
8. 输出可回滚 ModPackage。

---

## 13. 文档关系

- 开源集成依据：`docs/RESEARCH-OSS-INTEGRATION-2026.md`
- 模块攻坚任务：`docs/MODULE-ATTACK-MAP-v3.md`
- 原始愿景：`docs/VISION.md`
- 当前总体架构：`docs/ARCHITECTURE-v2.md`
- 游戏特化架构：`docs/ARCHITECTURE-GAME-MOD-v1.md`
- 盲点审查：`docs/ARCHITECTURE-GAME-MOD-v1.1-REVIEW.md`
