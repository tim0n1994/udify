# Udify v3 模块攻坚地图

> 给代码工程师的施工指南。本文把 `ARCHITECTURE-OSS-OPTIMIZED-v3.md` 细化到模块、任务、接口、算法、验收和测试粒度。默认优先完成游戏 Mod 自动化，尤其是 miu2d，然后扩展 RPG Maker MV/MZ、Unity、Godot、Unreal。

---

## 0. 使用方式

每个任务都有稳定 ID：

```text
领域-模块-序号
例如 DATA-CG-01 表示数据层 ContentGraph 第 1 个任务
```

优先级：

- **P0**：v3 MVP 必须完成。
- **P1**：MVP 后立即增强。
- **P2**：多引擎和平台化前完成。
- **P3**：生态扩张阶段。

完成定义：

- 有类型注解和 Google-style docstring。
- 有单元测试。
- 跨模块行为有集成测试。
- 高风险模块有 golden case。
- 文档中的输入输出契约不被破坏。

---

## 1. 总体攻坚路线

### Milestone V3-M0：架构地基，1 周

目标：不改变用户功能，先把数据模型和 adapter 边界补上。

必须完成：

- `SourceSpan`、`Provenance`、`Confidence` 数据结构。
- `EngineAdapter`、`ToolAdapter` 协议。
- `PatchOperation.execution_mode`。
- Tool run audit 结构。
- 旧测试保持通过。

### Milestone V3-M1：miu2d 闭环，2 到 3 周

目标：自然语言到可回滚 ModPackage 的真实闭环。

必须完成：

- miu2d adapter。
- Semantic Lifter 初版。
- ActionSchema。
- VFS preview。
- static validator。
- Playwright runtime probe。
- intent alignment benchmark。

### Milestone V3-M2：开源工具接入，3 到 4 周

目标：接入 Tree-sitter、Playwright、NetworkX、Semgrep/规则扫描、MCP/FastMCP。

必须完成：

- Tool lockfile。
- Secure Tool Gateway。
- 外部 CLI contract test。
- 失败归因报告。

### Milestone V3-M3：第二引擎，4 到 6 周

目标：RPG Maker MV/MZ 作为第二个结构化引擎。

必须完成：

- RPG Maker detector。
- JSON data parser。
- event graph。
- patch emitter。
- runtime probe 或静态替代 probe。

### Milestone V3-M4：生产化底座，6 到 10 周

目标：从本地 pipeline 升级到服务化能力。

必须完成：

- Temporal workflow 或等价 durable runner。
- OPA policy。
- Qdrant/Neo4j 可选后端。
- UdifyBench。
- compatibility CI。

---

## 2. 数据层

### DATA-CG：ContentGraph v3

| ID | 优先级 | 任务 | 输入 | 输出 | 验收 |
|---|---|---|---|---|---|
| DATA-CG-01 | P0 | 新增 `SourceSpan` | file path、line、column、hash | source span object | 支持文本和归档内文件 |
| DATA-CG-02 | P0 | 新增 `Provenance` | tool id、version、args、input hash | provenance object | 能追踪每个属性来源 |
| DATA-CG-03 | P0 | 新增 `Confidence` | score、method、evidence | confidence object | 所有语义标签必须可带置信度 |
| DATA-CG-04 | P0 | 为 `ContentNode` 增加 `semantic_tags` | tags | node metadata | tag 可序列化和查询 |
| DATA-CG-05 | P0 | 为 `ContentAsset` 增加 `license_hint` | detected source | license hint | 未知时显式 unknown |
| DATA-CG-06 | P1 | 增加 `runtime_observations` | probe result | observation refs | 支持同一节点多次观测 |
| DATA-CG-07 | P1 | 子图导出 | node ids、depth | ContentGraph | 用于影响分析和 prompt 压缩 |
| DATA-CG-08 | P1 | graph checksum | graph | stable hash | patch 前后可做一致性校验 |
| DATA-CG-09 | P2 | overlay graph | base、mod overlay | merged graph | 支持 ModStack 叠加 |
| DATA-CG-10 | P2 | graph migration | old graph version | new graph version | 旧 session 可读取 |

测试：

- `tests/models/test_content_graph_v3.py`
- round-trip 序列化。
- 旧格式兼容。
- graph checksum 稳定。

### DATA-PATCH：CDLPatch v3

| ID | 优先级 | 任务 | 输入 | 输出 | 验收 |
|---|---|---|---|---|---|
| DATA-PATCH-01 | P0 | 增加 `execution_mode` | operation | mode | 默认 `graph_only` |
| DATA-PATCH-02 | P0 | 增加 `PatchTarget` | graph node/source span | target | 可映射到文件和图节点 |
| DATA-PATCH-03 | P0 | 增加 `preconditions` | graph/file state | conditions | 应用前校验失败则拒绝 |
| DATA-PATCH-04 | P0 | 增加 `postconditions` | expected state | conditions | 应用后校验失败则回滚 |
| DATA-PATCH-05 | P0 | 增加 `reverse` | op | reverse op | 所有 P0 op 可回滚 |
| DATA-PATCH-06 | P0 | 增加 `validation_probes` | patch | probe list | patch 自带验证需求 |
| DATA-PATCH-07 | P1 | 增加 `risk` | op | score + reasons | 高风险触发确认 |
| DATA-PATCH-08 | P1 | patch idempotency key | op target + payload | stable key | 重复应用不重复修改 |
| DATA-PATCH-09 | P1 | patch compatibility check | two patches | conflict list | 能检测同属性冲突 |
| DATA-PATCH-10 | P2 | semantic three-way merge | base、A、B | merged/conflicts | 支持可组合数值策略 |

测试：

- `tests/models/test_cdl_patch_v3.py`
- reverse patch property-based test。
- idempotency test。
- compatibility golden cases。

---

## 3. 适配器层

### ADAPT-ENGINE：EngineAdapter

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| ADAPT-ENGINE-01 | P0 | 定义 `EngineAdapter` Protocol | mypy 可检查 |
| ADAPT-ENGINE-02 | P0 | detector 返回置信度和证据 | 错误检测不超过 warning |
| ADAPT-ENGINE-03 | P0 | adapter capability manifest | UI/API 可展示支持能力 |
| ADAPT-ENGINE-04 | P0 | adapter contract test suite | 新引擎必须通过 |
| ADAPT-ENGINE-05 | P1 | adapter versioning | 支持兼容性声明 |
| ADAPT-ENGINE-06 | P2 | adapter plugin discovery | 可从外部包加载 |

接口：

```python
DetectionResult:
  engine_id: str
  confidence: float
  evidence: list[Evidence]
  supported_operations: list[str]
```

### ADAPT-MIU2D：miu2d Adapter

| ID | 优先级 | 任务 | 细节 | 验收 |
|---|---|---|---|---|
| ADAPT-MIU2D-01 | P0 | 封装现有 INI parser | 输出 SourceSpan | 所有样例 INI 解析 |
| ADAPT-MIU2D-02 | P0 | 封装 OBJ parser | 输出 resource nodes | 引用路径可追踪 |
| ADAPT-MIU2D-03 | P0 | 封装 NPC parser | 输出 character nodes | NPC 属性齐全 |
| ADAPT-MIU2D-04 | P0 | Tree-sitter Lua 接入 | 函数、调用、危险 API | Lua AST golden test |
| ADAPT-MIU2D-05 | P0 | DSL 命令表 | 218 命令 schema | 未知命令标 warning |
| ADAPT-MIU2D-06 | P0 | GameWorldGraph builder | config + script | 角色、物品、技能、地图关系 |
| ADAPT-MIU2D-07 | P0 | action schemas | numeric/script/reward | Planner 可消费 |
| ADAPT-MIU2D-08 | P0 | patch emitter | INI/OBJ/Lua/DSL | VFS 中可应用 |
| ADAPT-MIU2D-09 | P0 | Playwright probe builder | start/read state | 能启动样例 |
| ADAPT-MIU2D-10 | P1 | converter tool adapter | binary assets | 记录 tool provenance |
| ADAPT-MIU2D-11 | P1 | Dashboard schema alignment | zod/schema | UI 可复用 |
| ADAPT-MIU2D-12 | P1 | map reachability analyzer | map graph | 修改障碍后可达性验证 |

### ADAPT-RMMV：RPG Maker MV/MZ Adapter

| ID | 优先级 | 任务 | 细节 | 验收 |
|---|---|---|---|---|
| ADAPT-RMMV-01 | P1 | detector | `www/data/System.json` 等 | 置信度 > 0.9 |
| ADAPT-RMMV-02 | P1 | database parser | Actors/Enemies/Skills/Items | 生成 typed nodes |
| ADAPT-RMMV-03 | P1 | map parser | MapXXX events | event graph |
| ADAPT-RMMV-04 | P1 | common event parser | triggers/switches | 引用完整性 |
| ADAPT-RMMV-05 | P1 | plugin parser | `js/plugins.js` | plugin params |
| ADAPT-RMMV-06 | P1 | action schemas | stats/event/reward/dialog | 可规划 |
| ADAPT-RMMV-07 | P1 | patch emitter | JSON patch | 保持格式稳定 |
| ADAPT-RMMV-08 | P1 | static validator | switches/variables refs | 检测悬空引用 |
| ADAPT-RMMV-09 | P2 | NW.js runtime probe | launch + console | 启动 smoke test |

### ADAPT-UNITY：Unity Adapter

| ID | 优先级 | 任务 | 细节 | 验收 |
|---|---|---|---|---|
| ADAPT-UNITY-01 | P2 | detector | UnityPlayer.dll/globalgamemanagers | engine version |
| ADAPT-UNITY-02 | P2 | AssetRipper wrapper | asset manifest | 资源清单标准化 |
| ADAPT-UNITY-03 | P2 | BepInEx profile generator | plugin skeleton | 可生成空 Mod |
| ADAPT-UNITY-04 | P2 | Harmony patch operation | runtime_hook | risk R4 |
| ADAPT-UNITY-05 | P2 | C# semantic scan | Roslyn | method refs |
| ADAPT-UNITY-06 | P3 | runtime smoke probe | launch game | 读取日志 |

---

## 4. 工具网关层

### TOOL-GW：Secure Tool Gateway

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| TOOL-GW-01 | P0 | 定义 `ToolAdapter` Protocol | 支持 schema、run、health |
| TOOL-GW-02 | P0 | tool manifest | name、version、capabilities、risk |
| TOOL-GW-03 | P0 | path allowlist | 越权路径拒绝 |
| TOOL-GW-04 | P0 | output sanitizer | 超大输出截断并落盘 |
| TOOL-GW-05 | P0 | tool run audit | 每次调用可回放 |
| TOOL-GW-06 | P0 | timeout and quota | 超时终止 |
| TOOL-GW-07 | P1 | tool lockfile | hash pin |
| TOOL-GW-08 | P1 | local policy engine | 输入 request 输出 allow/deny |
| TOOL-GW-09 | P1 | sandbox profile | read-only/read-write/network |
| TOOL-GW-10 | P2 | OPA integration | policy 可热更新 |
| TOOL-GW-11 | P2 | signature verify | cosign/sigstore |

Tool call schema：

```python
ToolCallRequest:
  tool_id: str
  capability: str
  args: dict
  job_id: str
  requested_paths: list[Path]
  risk: RiskScore
```

### TOOL-MCP：MCP/FastMCP 接入

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| TOOL-MCP-01 | P1 | 现有 MCP server schema 对齐 | list_tools 输出标准 |
| TOOL-MCP-02 | P1 | tool call 走 Secure Gateway | 无直连执行 |
| TOOL-MCP-03 | P1 | MCP resource exposing | graph summary、patch preview |
| TOOL-MCP-04 | P2 | FastMCP server prototype | 内部工具可快速发布 |
| TOOL-MCP-05 | P2 | prompt injection test | 工具输出不能越权 |

---

## 5. 感知和语义层

### PER-SCAN：文件扫描和增量感知

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| PER-SCAN-01 | P0 | file inventory | path、size、hash、mtime | 快照稳定 |
| PER-SCAN-02 | P0 | incremental diff | old/new inventory | changed paths |
| PER-SCAN-03 | P0 | dependency invalidation | changed file | affected nodes |
| PER-SCAN-04 | P1 | archive inventory | pak/zip/custom | archive_path |
| PER-SCAN-05 | P1 | background precompute | startup job | cache hit |
| PER-SCAN-06 | P2 | partial graph loading | query scope | lazy subgraph |

### PER-LIFT：Semantic Lifter

| ID | 优先级 | 任务 | 输入 | 输出 | 验收 |
|---|---|---|---|---|---|
| PER-LIFT-01 | P0 | domain ontology 初版 | game terms | ontology file | boss/item/skill/quest/map |
| PER-LIFT-02 | P0 | rule-based tagging | parsed nodes | semantic_tags | miu2d golden tags |
| PER-LIFT-03 | P0 | evidence builder | tag source | evidence refs | 每个 tag 有来源 |
| PER-LIFT-04 | P0 | confidence scoring | rule/LLM/runtime | score | 低置信标签可过滤 |
| PER-LIFT-05 | P1 | LLM label proposer | ambiguous node | candidate tags | 不能直接写入 final |
| PER-LIFT-06 | P1 | graph pattern mining | refs/calls/co-occurrence | mechanism candidates | 输出解释 |
| PER-LIFT-07 | P1 | runtime observation merge | probe result | node observations | 更新 confidence |
| PER-LIFT-08 | P2 | cross-engine ontology mapping | engine tags | canonical tags | RPG/Unity 可复用 |

关键算法：

```text
semantic_confidence =
  rule_confidence * 0.45
  + schema_confidence * 0.20
  + graph_context_confidence * 0.20
  + runtime_observation_confidence * 0.15
```

---

## 6. 认知层

### COG-INTENT：Intent Compiler

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| COG-INTENT-01 | P0 | StructuredIntent v3 | goal、constraints、negative prefs |
| COG-INTENT-02 | P0 | ambiguity detector | 模糊目标要求澄清或降级 |
| COG-INTENT-03 | P0 | reference feature mapper | 魂系等参考映射到机制 |
| COG-INTENT-04 | P0 | forbidden implementation path | “不要数值膨胀”可表达 |
| COG-INTENT-05 | P0 | acceptance probe spec | 每个目标至少一个验证建议 |
| COG-INTENT-06 | P1 | multilingual normalization | 中英混合稳定 |
| COG-INTENT-07 | P1 | user preference merge | Memory 融合 |
| COG-INTENT-08 | P2 | clarification question generator | risk 高且不确定时提问 |

### COG-CONFLICT：意图冲突检测

| ID | 优先级 | 任务 | 验收 |
|---|---|---|
| COG-CONFLICT-01 | P0 | hard constraint conflict | 检出互斥 |
| COG-CONFLICT-02 | P0 | reference conflict | 多参考矛盾 |
| COG-CONFLICT-03 | P1 | user preference conflict | 与历史偏好冲突 |
| COG-CONFLICT-04 | P1 | scope conflict | 修改范围过大 |
| COG-CONFLICT-05 | P2 | explainable conflict report | 给 UI 展示 |

---

## 7. 规划层

### PLAN-ACTION：Action Schema

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| PLAN-ACTION-01 | P0 | 定义 `ActionSchema` | target type、params、constraints |
| PLAN-ACTION-02 | P0 | numeric scale schema | HP/MP/ATK/drop 等 |
| PLAN-ACTION-03 | P0 | script insert schema | location、guard、body |
| PLAN-ACTION-04 | P0 | reward modify schema | item/exp/gold |
| PLAN-ACTION-05 | P1 | map edit schema | tile/block/trigger |
| PLAN-ACTION-06 | P1 | runtime hook schema | Unity/Harmony |
| PLAN-ACTION-07 | P1 | asset replace schema | image/audio/binary |
| PLAN-ACTION-08 | P2 | schema registry | engine adapter 提供 |

### PLAN-SEARCH：Plan Search

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| PLAN-SEARCH-01 | P0 | simple deterministic planner | 单目标数值类不走 MCTS |
| PLAN-SEARCH-02 | P0 | constraint filter | 违反 hard constraints 删除 |
| PLAN-SEARCH-03 | P0 | impact scope calculator | 输出 affected subgraph |
| PLAN-SEARCH-04 | P0 | plan ranker | score + reasons |
| PLAN-SEARCH-05 | P1 | MCTS budget control | max depth/cost/time |
| PLAN-SEARCH-06 | P1 | beam search fallback | 低成本多候选 |
| PLAN-SEARCH-07 | P1 | historical pattern reuse | MemoryStore suggestions |
| PLAN-SEARCH-08 | P2 | OR-Tools constraint optimization | 多目标数值平衡 |

### PLAN-RISK：风险和确认点

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| PLAN-RISK-01 | P0 | risk scoring | R0-R4 |
| PLAN-RISK-02 | P0 | confirmation gate decision | 高风险暂停 |
| PLAN-RISK-03 | P1 | plan diff explanation | 人类可读 |
| PLAN-RISK-04 | P1 | cost estimate | LLM/tool/runtime |
| PLAN-RISK-05 | P2 | uncertainty-aware planning | 多评估器分歧触发审阅 |

---

## 8. Patch 合成和执行层

### PATCH-SYN：Patch Synthesizer

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| PATCH-SYN-01 | P0 | graph target to source anchor | SourceSpan 精确 |
| PATCH-SYN-02 | P0 | INI emitter | 格式保持 |
| PATCH-SYN-03 | P0 | OBJ emitter | 引用不丢 |
| PATCH-SYN-04 | P0 | Lua safe insert | AST/语法验证 |
| PATCH-SYN-05 | P0 | DSL command emitter | 命令 schema 校验 |
| PATCH-SYN-06 | P0 | reverse builder | 全部 P0 op 可回滚 |
| PATCH-SYN-07 | P1 | binary asset emitter | 调 converter |
| PATCH-SYN-08 | P1 | JSON patch emitter | RPG Maker |
| PATCH-SYN-09 | P2 | runtime hook emitter | BepInEx/Harmony |

### EXEC-VFS：VFS Preview

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| EXEC-VFS-01 | P0 | overlay read/write | 不碰原文件 |
| EXEC-VFS-02 | P0 | diff preview | file-level diff |
| EXEC-VFS-03 | P0 | apply patch to VFS | CDLPatch 执行 |
| EXEC-VFS-04 | P0 | rollback VFS | snapshot restore |
| EXEC-VFS-05 | P1 | export overlay | ModPackage 输入 |
| EXEC-VFS-06 | P1 | multi overlay stack | ModStack 组合 |

### EXEC-SCHED：Execution Scheduler

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| EXEC-SCHED-01 | P0 | op dependency graph | topological order |
| EXEC-SCHED-02 | P0 | atomic apply | 失败回滚 |
| EXEC-SCHED-03 | P0 | retry policy | 可配置 |
| EXEC-SCHED-04 | P1 | checkpoint | partial rollback |
| EXEC-SCHED-05 | P1 | parallel safe ops | 不同文件并行 |
| EXEC-SCHED-06 | P2 | Temporal activity wrapper | 生产可回放 |

---

## 9. 验证和评估层

### VAL-STATIC：静态验证

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| VAL-STATIC-01 | P0 | schema validation | patch/file schema |
| VAL-STATIC-02 | P0 | reference integrity | 悬空引用 |
| VAL-STATIC-03 | P0 | numeric range | engine-specific range |
| VAL-STATIC-04 | P0 | syntax reparse | 修改后重新解析 |
| VAL-STATIC-05 | P0 | dangerous API scan | Lua/DSL |
| VAL-STATIC-06 | P1 | semantic invariant check | 任务链/地图 |
| VAL-STATIC-07 | P1 | mod compatibility check | 同文件/同属性 |
| VAL-STATIC-08 | P2 | Semgrep integration | 规则外置 |

### VAL-RUNTIME：运行时探针

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| VAL-RUNTIME-01 | P0 | `ProbeSpec` schema | action/assert/timeout |
| VAL-RUNTIME-02 | P0 | Playwright launcher | miu2d sample 启动 |
| VAL-RUNTIME-03 | P0 | console error capture | 报错归档 |
| VAL-RUNTIME-04 | P0 | state read bridge | 读取 HP/item/map |
| VAL-RUNTIME-05 | P0 | probe result report | passed/evidence |
| VAL-RUNTIME-06 | P1 | probe generator from patch | 自动最小 probe |
| VAL-RUNTIME-07 | P1 | flake retry | 降低误报 |
| VAL-RUNTIME-08 | P2 | pathfinding probe | 地图可达性 |
| VAL-RUNTIME-09 | P2 | RL environment adapter | Gymnasium |

### EVAL-INTENT：意图对齐评估

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| EVAL-INTENT-01 | P0 | golden case format | intent、expected、forbidden |
| EVAL-INTENT-02 | P0 | goal achievement score | 可解释 |
| EVAL-INTENT-03 | P0 | constraint satisfaction score | hard constraint 失败即 reject |
| EVAL-INTENT-04 | P0 | scope control score | 过度修改扣分 |
| EVAL-INTENT-05 | P1 | reference feature score | 风格映射 |
| EVAL-INTENT-06 | P1 | LLM judge as optional | 不能单独决定通过 |
| EVAL-INTENT-07 | P1 | eval regression runner | CI 可跑 |
| EVAL-INTENT-08 | P2 | UdifyBench dashboard | 趋势可视化 |

---

## 10. 记忆、反馈和知识

### MEM-STORE：Memory Store

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| MEM-STORE-01 | P0 | successful pattern schema | intent、patch、score |
| MEM-STORE-02 | P0 | failure signature schema | error、root cause、fix |
| MEM-STORE-03 | P1 | vector index adapter | local embedding |
| MEM-STORE-04 | P1 | similar pattern search | evidence refs |
| MEM-STORE-05 | P1 | user preference merge | planning 可用 |
| MEM-STORE-06 | P2 | Qdrant backend | 可切换 |
| MEM-STORE-07 | P2 | retention and privacy policy | 可删除 |

### KG-GAME：Game Knowledge Graph

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| KG-GAME-01 | P0 | miu2d rules | 数值、引用、机制 |
| KG-GAME-02 | P0 | style reference rules | 魂系等 |
| KG-GAME-03 | P1 | RPG Maker ontology | actors/events/switches |
| KG-GAME-04 | P1 | rule explanation | 每条 warning 有原因 |
| KG-GAME-05 | P2 | Neo4j backend | 可选生产存储 |

### FB-LOOP：反馈闭环

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| FB-LOOP-01 | P0 | explicit user feedback | rating/comment |
| FB-LOOP-02 | P0 | implicit feedback | rollback/playtime/error |
| FB-LOOP-03 | P1 | feedback to pattern | 高评分沉淀 |
| FB-LOOP-04 | P1 | feedback to risk | 高频失败加风险 |
| FB-LOOP-05 | P2 | community quality score | 平台排序 |

---

## 11. Mod 管理和生态

### MOD-STACK：Multi Mod Manager

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| MOD-STACK-01 | P0 | ModManifest v3 | dependency、engine、patch ids |
| MOD-STACK-02 | P0 | install to VFS | 不写原文件 |
| MOD-STACK-03 | P0 | conflict detection | 同 target |
| MOD-STACK-04 | P1 | load order resolver | topological |
| MOD-STACK-05 | P1 | semantic compatibility | 机制冲突 |
| MOD-STACK-06 | P1 | ModPackage export | zip + manifest |
| MOD-STACK-07 | P2 | compatibility matrix | pairwise CI |
| MOD-STACK-08 | P2 | migration planner | game version update |

### MARKET：Udiface 预备

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| MARKET-01 | P2 | publish metadata schema | title、intent、license |
| MARKET-02 | P2 | quality report schema | validation + eval |
| MARKET-03 | P2 | template extraction | 成功 Mod -> template |
| MARKET-04 | P3 | semantic search | intent -> mods |
| MARKET-05 | P3 | moderation queue | policy findings |
| MARKET-06 | P3 | creator attribution | provenance chain |

---

## 12. 安全和合规

### SEC-POLICY：Policy

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| SEC-POLICY-01 | P0 | risk model | R0-R4 |
| SEC-POLICY-02 | P0 | local policy file | yaml/json |
| SEC-POLICY-03 | P0 | high risk confirmation | job pause |
| SEC-POLICY-04 | P1 | OPA policy adapter | allow/deny |
| SEC-POLICY-05 | P1 | policy test suite | prompt injection cases |
| SEC-POLICY-06 | P2 | per-user RBAC | owner/editor/viewer |

### SEC-SUPPLY：供应链

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| SEC-SUPPLY-01 | P1 | tool lockfile | hash/version |
| SEC-SUPPLY-02 | P1 | tool provenance in audit | 每次调用记录 |
| SEC-SUPPLY-03 | P2 | SBOM generation | tool/package |
| SEC-SUPPLY-04 | P2 | signature verification | cosign |
| SEC-SUPPLY-05 | P2 | vulnerability scan | grype/similar |

### SEC-CONTENT：内容安全和版权

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| SEC-CONTENT-01 | P1 | secret scanner | API key/private data |
| SEC-CONTENT-02 | P1 | license hint | unknown 标记 |
| SEC-CONTENT-03 | P2 | asset fingerprint | 重复/版权风险 |
| SEC-CONTENT-04 | P2 | publish policy gate | 高风险不可发布 |
| SEC-CONTENT-05 | P3 | appeal workflow | 社区治理 |

---

## 13. 工作流和基础设施

### ORCH-JOB：ModJob

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| ORCH-JOB-01 | P0 | ModJob state model | 状态枚举 |
| ORCH-JOB-02 | P0 | checkpoint record | graph/patch/vfs |
| ORCH-JOB-03 | P0 | pause/resume | human gate |
| ORCH-JOB-04 | P0 | audit chain link | hash chain |
| ORCH-JOB-05 | P1 | local durable persistence | JSON/SQLite |
| ORCH-JOB-06 | P2 | Temporal workflow | replay-safe |
| ORCH-JOB-07 | P2 | WebSocket progress | UI |

### OBS：可观测性

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| OBS-01 | P0 | trace context schema | job/session/patch/op |
| OBS-02 | P0 | structured logs | JSON |
| OBS-03 | P1 | metrics collector | latency/cost/pass rate |
| OBS-04 | P1 | failure taxonomy | root cause |
| OBS-05 | P2 | OpenTelemetry | traces |
| OBS-06 | P2 | dashboard | Grafana |

---

## 14. 前端/API 预留

### API

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| API-01 | P1 | REST schema for session/job | OpenAPI |
| API-02 | P1 | create mod job | returns job id |
| API-03 | P1 | get plan preview | patch + risk |
| API-04 | P1 | approve/reject gate | state transition |
| API-05 | P1 | export package | downloadable |
| API-06 | P2 | streaming progress | WebSocket/SSE |

### UI

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| UI-01 | P2 | intent input | Chinese/English |
| UI-02 | P2 | plan diff viewer | file + graph |
| UI-03 | P2 | risk review panel | approve/reject |
| UI-04 | P2 | runtime probe report | evidence |
| UI-05 | P2 | ReactFlow plan DAG | op dependencies |
| UI-06 | P3 | Mod marketplace page | quality score |

---

## 15. UdifyBench

### BENCH：评测数据集

目录建议：

```text
benchmarks/
  miu2d/
    boss_difficulty_no_hp_inflation/
      input_game/
      intent.md
      expected_patterns.yaml
      forbidden_patterns.yaml
      probes.yaml
      scoring.yaml
```

任务：

| ID | 优先级 | 任务 | 验收 |
|---|---|---|---|
| BENCH-01 | P0 | benchmark case schema | 可加载 |
| BENCH-02 | P0 | 10 个 miu2d golden cases | 覆盖数值/脚本/奖励 |
| BENCH-03 | P0 | benchmark runner | CI 可跑 |
| BENCH-04 | P1 | failure snapshot | 失败可复现 |
| BENCH-05 | P1 | scoring report | markdown/json |
| BENCH-06 | P2 | 20 个 RPG Maker cases | 第二引擎 |
| BENCH-07 | P2 | regression threshold | 不达标阻塞合并 |

首批 golden cases：

1. 初始角色 HP 修改。
2. Boss 难度提升但 HP 不超过 1.35 倍。
3. NPC 对话奖励技能。
4. 物品掉落率提高。
5. 治疗道具削弱。
6. 新增商店物品。
7. 地图入口到出口可达性保持。
8. 禁止危险 Lua API。
9. 多 Mod 同属性冲突。
10. Patch 回滚后 graph checksum 一致。

---

## 16. 工程实施顺序

### 第一批 PR

1. DATA-CG-01 到 DATA-CG-05。
2. DATA-PATCH-01 到 DATA-PATCH-06。
3. ADAPT-ENGINE-01 到 ADAPT-ENGINE-04。
4. TOOL-GW-01 到 TOOL-GW-06。

### 第二批 PR

1. ADAPT-MIU2D-01 到 ADAPT-MIU2D-08。
2. PER-LIFT-01 到 PER-LIFT-04。
3. PLAN-ACTION-01 到 PLAN-ACTION-04。
4. PATCH-SYN-01 到 PATCH-SYN-06。

### 第三批 PR

1. VAL-STATIC-01 到 VAL-STATIC-05。
2. VAL-RUNTIME-01 到 VAL-RUNTIME-05。
3. EVAL-INTENT-01 到 EVAL-INTENT-04。
4. BENCH-01 到 BENCH-03。

### 第四批 PR

1. ORCH-JOB-01 到 ORCH-JOB-05。
2. MOD-STACK-01 到 MOD-STACK-06。
3. MEM-STORE-01 到 MEM-STORE-05。
4. OBS-01 到 OBS-04。

### 第五批 PR

1. ADAPT-RMMV-01 到 ADAPT-RMMV-09。
2. TOOL-MCP-01 到 TOOL-MCP-05。
3. SEC-POLICY-01 到 SEC-POLICY-05。
4. API-01 到 API-05。

---

## 17. 不要提前做的事

这些事有价值，但现在做会拖慢主线：

1. 不要先做完整前端。先让 CLI/API 的 v3 闭环真实跑通。
2. 不要先接 Unreal。Unreal 资产提取可做，但机制修改成本高。
3. 不要做通用自动试玩 AI。先做最小探针。
4. 不要过早上 Neo4j/Qdrant 强依赖。本地模式必须成立。
5. 不要让 LLM 直接写文件。必须走 Patch 和 Tool Gateway。
6. 不要把 MCP 当安全边界。MCP 是协议，不是权限系统。
7. 不要把所有计划都走 MCTS。简单任务用确定性规划。
8. 不要用“通过 LLM 评估”替代运行时验证。

---

## 18. 工程师交付模板

每个模块 PR 描述应包含：

```markdown
## Scope
- Task IDs:
- Files changed:

## Contracts
- Inputs:
- Outputs:
- Backward compatibility:

## Validation
- Unit tests:
- Integration tests:
- Golden cases:

## Risks
- Security:
- Cost:
- Migration:

## Follow-ups
- Deferred task IDs:
```

---

## 19. 代码位置建议

```text
udify/
  models/
    source.py                 # SourceSpan, Provenance, Evidence
    content_graph.py          # ContentGraph v3 compatible extension
    cdl_patch.py              # CDLPatch v3 compatible extension
  core/
    adapters/
      base.py                 # EngineAdapter, ToolAdapter
      miu2d.py
      rpg_maker.py
      unity.py
    tool_gateway/
      gateway.py
      policy.py
      lockfile.py
      audit.py
    perception/
      semantic_lifter.py
      ontology.py
    planning/
      action_schema.py
      plan_ranker.py
      risk.py
    validation/
      runtime_probe.py
      benchmark.py
    orchestration/
      mod_job.py
      local_runner.py
```

迁移注意：

- 不要一次大搬家。先新增目录和协议，再逐步把现有实现迁入。
- 旧模块保留兼容 facade，避免一次性破坏测试。
- 新 v3 类型可以先作为 optional metadata 挂到现有 dataclass。

---

## 20. 成功判据

v3 第一阶段成功，不看代码行数，看以下事实：

1. 对同一个 miu2d 样例，连续运行同一意图得到稳定 Patch。
2. 每个 PatchOperation 都能回溯到 SourceSpan 和 planning reason。
3. 修改只先进 VFS，原文件不受影响。
4. 静态验证能抓出无效引用和危险脚本。
5. Playwright probe 能证明游戏启动并读取关键状态。
6. Patch 能回滚，回滚后 checksum 一致。
7. 至少 10 个 UdifyBench case 在 CI 中运行。
8. 工程师能根据本文任务 ID 拆 PR，而不需要重新解释架构。
