<!--
status: aspirational
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 愿景/未验证蓝图。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 系统功能设计指南 v1

> 从架构到功能、从整体到局部细节，对 Udify 进行重新拆分和功能化设计。本指南面向工程师、测试、产品、架构和未来 AI 编码助手，目标是把“意图驱动的内容魔改系统”落成可执行、可验证、可迭代的功能体系。

---

## 0. 设计总纲

Udify 的本质不是一个普通 Mod 工具，也不是一个聊天机器人。它是：

> **面向游戏内容的意图编译、语义 Patch、自动验证和生态分发系统。**

系统必须始终围绕最初使命：

```text
非技术用户表达自然语言愿望
  -> 系统理解原始内容
  -> 系统规划修改
  -> 系统执行修改
  -> 系统验证可玩和意图对齐
  -> 用户预览、安装、分享、反馈
  -> 成功模式进入生态记忆
```

### 0.1 产品功能总流

```text
导入游戏
  -> 扫描和识别引擎
  -> 构建游戏语义图
  -> 输入自然语言意图
  -> 生成结构化意图
  -> 生成候选修改方案
  -> 展示风险和预览
  -> 应用到 VFS
  -> 静态验证
  -> 运行时验证
  -> 导出 ModPackage
  -> 安装或发布
  -> 收集反馈
  -> 更新模板和偏好
```

### 0.2 系统分层

| 层 | 功能定位 | 用户可感知结果 |
|---|---|---|
| Presentation | CLI/API/Web/编辑器 | 用户输入意图、看计划、确认、预览、导出 |
| Session & Job | 会话、任务、状态机 | 可暂停、恢复、回滚、查看进度 |
| Intent OS | 自然语言理解和约束编译 | 模糊愿望变成清晰目标 |
| Perception & Semantic IR | 游戏文件和机制理解 | 系统知道什么是 Boss、任务、物品、脚本 |
| Planning & Patch Compiler | 生成修改计划和 Patch | 多个可选方案、风险、影响范围 |
| Execution | VFS、文件 Patch、工具调用 | 安全预览和可回滚安装 |
| Validation | 静态、运行时、意图对齐 | 证明 Mod 能跑、符合意图 |
| Mod Management | ModPackage、兼容性、加载顺序 | 可安装、卸载、组合、迁移 |
| Knowledge & Memory | 用户偏好、成功模板、失败签名 | 越用越懂用户和游戏 |
| Supply & Ecosystem | 签名、发布、市场、反馈 | Udiface 生态 |
| Governance | 安全、版权、隐私、审计 | 可控、可信、合规 |
| Infrastructure | 缓存、云调度、工具网关、观测 | 稳定、高效、可扩展 |

---

## 1. 用户角色和核心场景

### 1.1 用户角色

| 角色 | 核心诉求 | 权限 |
|---|---|---|
| Player | 想快速改游戏体验 | 导入、预览、安装、反馈 |
| Mod Creator | 想制作可分享 Mod | 创建、导出、发布、维护 |
| Tester | 想验证 Mod 可玩性 | 运行探针、提交报告 |
| Game Developer | 想用于开发和 LiveOps | 批量生成、验证、A/B、回滚 |
| Community Moderator | 想审核内容和版权 | 审核、下架、标记风险 |
| Platform Operator | 想管理基础设施和生态 | 配置策略、监控、成本 |
| Tool Maintainer | 想接入新工具或引擎 | 提供 Adapter、Contract Test |

### 1.2 一级用户旅程

#### Journey A：玩家本地魔改

1. 用户选择游戏目录。
2. 系统识别引擎并扫描文件。
3. 用户输入：“让第一个 Boss 更难，但不要单纯翻倍血量。”
4. 系统解释意图，展示目标和约束。
5. 系统生成 2 到 3 个方案。
6. 用户选择方案。
7. 系统应用到 VFS 预览。
8. 系统验证配置、引用和脚本。
9. 用户安装或回滚。

成功标准：

- 不破坏原始游戏。
- 用户看得懂改了什么。
- Patch 可回滚。
- 验证报告可读。

#### Journey B：创作者发布 Mod

1. 创作者生成或手工编辑 Patch。
2. 系统构建 ModPackage。
3. 系统运行静态和运行时验证。
4. 系统生成 Validation Certificate。
5. 系统检查 license、安全和兼容性。
6. 创作者提交发布。
7. 平台审核或自动通过。
8. 用户安装、评分、反馈。

成功标准：

- 包含 manifest、patch、reverse、evidence、signature。
- 公开发布必须有验证证书。
- 兼容性风险可见。

#### Journey C：开发团队批量 QA 和平衡性

1. 团队上传候选平衡性目标。
2. 系统生成多个 Patch 方案。
3. SimCloud 批量验证。
4. 设计师看指标和录像。
5. 选择方案进入 A/B。
6. 监控异常并可自动回滚。

成功标准：

- 不自动上线高风险变更。
- 所有实验有回滚条件。
- 所有结果可复现。

---

## 2. 项目功能域重新拆分

### 2.1 Domain Map

```text
udify/
  foundation/       基础类型、错误、trace、配置
  capability/       硬件和运行时能力画像
  session/          用户会话和 ModJob 状态机
  perception/       游戏扫描、引擎检测、解析
  semantic/         Game Semantic IR、ontology、graph query
  intent/           意图解析、参考映射、约束编译
  planning/         ActionSchema、计划搜索、风险评分
  patch/            CDLPatch、PatchEmitter、ReversePatch
  execution/        VFS、调度、工具执行
  tools/            ToolGateway、ToolAdapter、MCP
  validation/       静态验证、运行时探针、UdifyBench
  mod/              ModPackage、ModStack、兼容性
  memory/           用户偏好、模板、反馈学习
  supply/           SBOM、签名、发布门
  ecosystem/        Udiface API、搜索、评分、市场
  governance/       安全、版权、隐私、审计、策略
  infrastructure/   缓存、事件、持久化、云调度、观测
  presentation/     CLI、API、Web、ReactFlow
```

### 2.2 Domain Responsibility Matrix

| Domain | 拥有的数据 | 提供能力 | 不负责 |
|---|---|---|---|
| foundation | Trace、Error、Result、Version | 全局基础协议 | 业务决策 |
| capability | CapabilityProfile | 设备/节点能力检测 | Patch 规划 |
| session | Session、ModJob、Checkpoint | 生命周期、暂停恢复 | 语义理解 |
| perception | RawInventory、ParseOutput | 文件扫描、引擎检测、解析 | 意图解释 |
| semantic | GameSemanticGraph | 语义实体、关系、证据 | 文件写入 |
| intent | IntentAST、StructuredIntent | 意图和约束 | 直接生成 Patch |
| planning | PatchPlan、ImpactReport | 方案搜索和排序 | 具体文件写入 |
| patch | CDLPatch、ReversePatch | Patch 表达和合成 | 执行工具 |
| execution | VFSOverlay、ApplyResult | 应用、回滚、调度 | 判断内容好坏 |
| tools | ToolManifest、ToolRun | 外部能力安全执行 | 业务编排 |
| validation | ValidationReport、ProbeResult | 证明正确性 | 发布市场 |
| mod | ModManifest、ModStack | 安装、卸载、组合 | 版权裁决 |
| memory | Pattern、Preference、Feedback | 复用和学习 | 强制发布策略 |
| supply | Artifact、Signature、Certificate | 包和供应链 | 生成玩法 |
| ecosystem | Listing、Review、SearchIndex | 发布、搜索、社区 | 本地执行 |
| governance | Policy、Audit、LicenseRisk | 策略、审计、合规 | 游戏解析 |
| infrastructure | Cache、Event、Storage、Scheduler | 横向基础设施 | 领域语义 |
| presentation | Command、ViewModel | 用户交互 | 核心状态所有权 |

---

## 3. Foundation 基础层

### 3.1 功能目标

统一所有模块的基本协议，避免每个模块自定义错误、trace、版本、结果对象。

### 3.2 子模块

| 子模块 | 功能 |
|---|---|
| `trace_context` | trace_id、session_id、job_id、op_id |
| `result` | Result/Success/Failure 标准返回 |
| `errors` | ErrorRecord、错误码规范 |
| `versioning` | schema version、兼容策略 |
| `time` | clock abstraction，便于测试 |
| `ids` | 稳定 ID 生成 |
| `serialization` | JSON/YAML/protobuf 预留 |

### 3.3 核心数据

```yaml
TraceContext:
  trace_id: string
  session_id: string | null
  job_id: string | null
  intent_id: string | null
  graph_id: string | null
  patch_id: string | null
  op_id: string | null
```

```yaml
ErrorRecord:
  code: string
  message: string
  severity: info | warning | error | blocking
  retryable: bool
  owner_domain: string
  suggested_action: string
  evidence_refs: [string]
```

### 3.4 验收

- 所有跨模块 Response 都能携带 `TraceContext`。
- 所有 blocking error 都有 `owner_domain`。
- enum 新增值时消费者默认处理 unknown。

---

## 4. Capability 能力画像域

### 4.1 功能目标

识别本地设备、云节点、边缘节点能力，为验证、调度、推理和安装提供资源约束。

### 4.2 子模块

| 子模块 | 细节 |
|---|---|
| `cpu_probe` | 核心数、SIMD、频率估算 |
| `gpu_probe` | API、VRAM、RT、compute、video encode |
| `npu_probe` | CoreML/DirectML/ONNX backend |
| `storage_probe` | SSD/HDD、吞吐、随机读 |
| `network_probe` | latency、jitter、region |
| `profile_cache` | profile 缓存和过期 |
| `workload_mapper` | 任务到资源需求 |

### 4.3 核心功能

| 功能 ID | 名称 | 输入 | 输出 | 验收 |
|---|---|---|---|---|
| CAP-01 | 构建设备画像 | local node | CapabilityProfile | 可在无 GPU 下返回 |
| CAP-02 | 构建云节点画像 | node agent | CapabilityProfile | 包含 GPU 分区 |
| CAP-03 | 创建 workload descriptor | job + validation plan | WorkloadDescriptor | 有 fallback |
| CAP-04 | 判断本地可执行 | profile + workload | ExecutionFeasibility | 给出原因 |
| CAP-05 | 生成降级策略 | workload | fallback list | 不可降级时说明 |

### 4.4 失败模式

- `CAP_GPU_UNKNOWN`
- `CAP_NPU_BACKEND_MISSING`
- `CAP_STORAGE_PROBE_DENIED`
- `CAP_NETWORK_OFFLINE`
- `CAP_PROFILE_STALE`

---

## 5. Session and Job 会话域

### 5.1 功能目标

把一次魔改从“函数调用”变成可追踪、可暂停、可恢复、可回滚的工作流。

### 5.2 状态对象

```yaml
ModSession:
  session_id: string
  user_id: string
  game_id: string
  active_job_ids: [string]
  intent_history: [IntentRef]
  graph_refs: [GraphRef]
  patch_refs: [PatchRef]
  feedback_refs: [FeedbackRef]
```

```yaml
ModJob:
  job_id: string
  session_id: string
  state: created | sanitized | perceived | intent_compiled | planned | approval_required | approved | applied_to_vfs | validated | packaged | published | completed | failed | rolled_back
  checkpoints: [Checkpoint]
  approvals: [ApprovalRecord]
  audit_head: string
```

### 5.3 子模块

| 子模块 | 功能 |
|---|---|
| `session_manager` | 创建、查询、关闭 session |
| `job_manager` | job 状态机 |
| `checkpoint_manager` | graph/patch/vfs 快照 |
| `approval_manager` | 人工确认 |
| `resume_manager` | 恢复中断任务 |
| `job_events` | 状态变更事件 |

### 5.4 状态转移规则

- `planned -> approval_required`：风险高或策略要求。
- `approval_required -> approved`：用户确认。
- `applied_to_vfs -> validated`：验证完成。
- 任意状态可进入 `failed`。
- `failed` 必须能进入 `rolled_back` 或 `manual_recovery_required`。

### 5.5 验收

- 每个状态转移有事件。
- 非法转移被拒绝。
- checkpoint 可恢复。
- approval 记录不可变。

---

## 6. Perception 感知域

### 6.1 功能目标

从游戏目录和文件中提取结构化信息，但不做高层语义判断。感知域回答“文件里有什么”。

### 6.2 子模块

| 子模块 | 功能 |
|---|---|
| `inventory_scanner` | 文件列表、hash、mtime |
| `engine_detector` | miu2d/RPG Maker/Unity/Godot/Unreal |
| `format_router` | 根据文件类型分发 parser |
| `parser_miu2d` | INI/OBJ/NPC/Lua/DSL |
| `parser_rpg_maker` | JSON database/map/event |
| `parser_unity_manifest` | AssetRipper 输出 |
| `parser_godot` | scene/resource |
| `parser_unreal_manifest` | FModel/CUE4Parse 输出 |
| `incremental_perception` | 变更文件重解析 |
| `source_index` | SourceSpan 索引 |

### 6.3 功能列表

| 功能 ID | 名称 | 验收 |
|---|---|---|
| PER-01 | 扫描游戏目录 | 输出 RawInventory |
| PER-02 | 检测引擎 | 输出 DetectionResult + evidence |
| PER-03 | 增量扫描 | 只返回 changed files |
| PER-04 | 解析配置 | 输出 typed records + SourceSpan |
| PER-05 | 解析脚本 AST | 输出函数、调用、危险 API |
| PER-06 | 构建引用图 | 输出 ReferenceGraph |
| PER-07 | 记录 parser provenance | 每条 record 有 tool/version/hash |
| PER-08 | parser contract test | 每个 adapter 有 golden fixture |

### 6.4 非职责

感知域不判断：

- “这个是不是好设计”。
- “应该怎么改”。
- “这个 Mod 能不能发布”。

---

## 7. Semantic 语义域

### 7.1 功能目标

把感知结果提升成游戏语义。语义域回答“这些结构在游戏里意味着什么”。

### 7.2 子模块

| 子模块 | 功能 |
|---|---|
| `ontology_registry` | 核心游戏 ontology |
| `entity_extractor` | 从 records 抽取 Actor/Item/Quest |
| `relation_builder` | contains/requires/rewards/triggers |
| `semantic_lifter` | 结构到语义 |
| `evidence_scorer` | 证据评分 |
| `confidence_model` | 置信度合成 |
| `mechanism_graph_builder` | 战斗、经济、任务、地图机制 |
| `runtime_observation_merger` | 合并运行时观测 |
| `graph_query` | semantic/structural/source/hybrid 查询 |
| `overlay_merger` | base graph + Mod overlays |

### 7.3 核心功能

| 功能 ID | 名称 | 输入 | 输出 |
|---|---|---|---|
| SEM-01 | 抽取语义实体 | ParseOutput | SemanticEntity |
| SEM-02 | 构建语义关系 | ReferenceGraph | SemanticRelation |
| SEM-03 | 标注证据 | entity/relation | EvidenceRef |
| SEM-04 | 计算置信度 | evidence | ConfidenceScore |
| SEM-05 | 构建机制图 | semantic graph | MechanismGraph |
| SEM-06 | 查询目标 | semantic query | nodes + evidence |
| SEM-07 | 合并 runtime observation | probe result | updated graph |
| SEM-08 | 生成 protected scope | main quest/core files | GraphScope |

### 7.4 语义写入规则

- 没有 EvidenceRef 的 semantic tag 不可写入正式图。
- 低置信实体不能自动进入 file patch。
- Runtime observation 可以提升置信度。
- 用户确认可以成为 E4 evidence。

---

## 8. Intent 意图域

### 8.1 功能目标

把用户自然语言转换成结构化目标、约束、参考、禁止路径和验收条件。

### 8.2 子模块

| 子模块 | 功能 |
|---|---|
| `input_sanitizer` | 长度、注入、危险请求过滤 |
| `language_detector` | 语言识别 |
| `intent_parser` | IntentAST |
| `intent_classifier` | 意图类型 |
| `constraint_extractor` | hard/soft constraints |
| `reference_mapper` | 风格参考到机制特征 |
| `scope_resolver` | 目标范围 |
| `ambiguity_detector` | 模糊和冲突 |
| `clarification_engine` | 澄清问题 |
| `acceptance_planner` | 验收探针 |

### 8.3 功能列表

| 功能 ID | 名称 | 验收 |
|---|---|---|
| INT-01 | 生成 IntentAST | 每个 clause 分类 |
| INT-02 | 生成 StructuredIntent | goal/constraints/reference |
| INT-03 | 提取禁止路径 | “不要数值膨胀”转 hard constraint |
| INT-04 | 参考映射 | “魂系”转机制特征 |
| INT-05 | 模糊检测 | high ambiguity 阻止自动应用 |
| INT-06 | 生成验收探针 | 每个主目标至少一个 probe idea |
| INT-07 | 合并用户偏好 | 与历史偏好冲突时报 warning |

---

## 9. Planning 规划域

### 9.1 功能目标

根据结构化意图和语义图生成候选方案，并对质量、成本、风险、影响范围排序。

### 9.2 子模块

| 子模块 | 功能 |
|---|---|
| `target_resolver` | 意图目标到实体 |
| `action_schema_registry` | 可执行动作 schema |
| `action_expander` | 生成候选动作 |
| `constraint_solver` | 过滤违规动作 |
| `impact_analyzer` | 影响范围 |
| `risk_scorer` | R0-R4 |
| `cost_estimator` | LLM/tool/runtime 成本 |
| `plan_search` | deterministic/beam/MCTS |
| `plan_ranker` | 打分和解释 |
| `plan_explainer` | 用户可读方案 |

### 9.3 规划模式

| 模式 | 用途 |
|---|---|
| deterministic | 单目标简单数值修改 |
| beam_search | 多候选低成本方案 |
| mcts | 多目标复杂影响 |
| propose_only | 高风险或低置信时只提方案 |
| template_reuse | 从成功模板生成 |

### 9.4 Plan 输出

```yaml
PatchPlan:
  plan_id: string
  summary: string
  target_resolution: TargetResolution
  actions: [PlannedAction]
  impact: ImpactReport
  risk: RiskScore
  cost: CostEstimate
  validation_plan: ValidationPlan
  explanation: string
```

### 9.5 验收

- 每个 plan 有 impact report。
- 每个 rejected candidate 有原因。
- simple task 不强制走 MCTS。
- high risk plan 触发 confirmation。

---

## 10. Patch 变换域

### 10.1 功能目标

把计划转换成可执行、可回滚、可验证的 CDLPatch。

### 10.2 子模块

| 子模块 | 功能 |
|---|---|
| `patch_model` | CDLPatch / PatchOperation |
| `anchor_resolver` | entity/property 到 SourceSpan |
| `numeric_emitter` | 数值 Patch |
| `script_emitter` | Lua/DSL/C# patch |
| `json_emitter` | RPG Maker JSON patch |
| `asset_emitter` | 资产替换 |
| `runtime_hook_emitter` | Hook patch |
| `reverse_builder` | 反向 Patch |
| `idempotency_builder` | 重复应用检测 |
| `patch_diff_renderer` | 人类可读 diff |

### 10.3 Patch 强制字段

- `op_id`
- `op_kind`
- `execution_mode`
- `target`
- `payload`
- `preconditions`
- `postconditions`
- `reverse`
- `probes`
- `risk`
- `provenance`

### 10.4 验收

- installable patch 必须有 reverse。
- file patch 必须有 SourceSpan。
- runtime hook 必须有 disable plan。
- patch 可序列化。
- patch 重复应用幂等。

---

## 11. Execution 执行域

### 11.1 功能目标

安全应用 Patch 到 VFS、文件或运行时 Hook，不直接信任 LLM 输出。

### 11.2 子模块

| 子模块 | 功能 |
|---|---|
| `vfs_overlay` | 预览层 |
| `patch_applicator` | 应用 Patch |
| `rollback_manager` | 回滚 |
| `execution_scheduler` | op 依赖排序 |
| `file_transaction` | 文件级原子性 |
| `apply_audit` | 应用日志 |
| `runtime_hook_installer` | Hook 安装/禁用 |
| `dry_run_executor` | 只模拟 |

### 11.3 执行策略

| execution_mode | 行为 |
|---|---|
| graph_only | 只改图，不写文件 |
| file_patch | 写 VFS 或文件 |
| package_overlay | 输出 overlay |
| runtime_hook | 生成/安装 hook，必须确认 |

### 11.4 验收

- 默认只写 VFS。
- 真实文件写入必须显式确认。
- 失败自动回滚。
- apply result 包含 touched files。

---

## 12. Tool 工具域

### 12.1 功能目标

所有外部工具、MCP server、CLI、库调用统一走安全网关。

### 12.2 子模块

| 子模块 | 功能 |
|---|---|
| `tool_registry` | 注册工具 |
| `tool_manifest` | 工具能力 schema |
| `tool_resolver` | 查找二进制/库 |
| `policy_adapter` | 调用策略 |
| `sandbox_runner` | 隔离执行 |
| `quota_manager` | CPU/GPU/内存/时间 |
| `output_sanitizer` | 输出净化 |
| `tool_audit` | 调用审计 |
| `contract_tests` | 工具契约测试 |
| `mcp_bridge` | MCP/FastMCP 接入 |

### 12.3 工具分类

| 类别 | 示例 | 风险 |
|---|---|---|
| parser | Tree-sitter | R1 |
| extractor | AssetRipper/QuickBMS | R3 |
| browser | Playwright | R2/R3 |
| generator | ComfyUI | R3 |
| packager | converter | R3 |
| remote service | LLM/Cloud API | R2-R4 |

### 12.4 验收

- 无工具可绕过 ToolGateway。
- 越权路径拒绝。
- stdout/stderr 大输出落 artifact。
- contract test 失败工具进入 quarantine。

---

## 13. Validation 验证域

### 13.1 功能目标

证明 Patch 正确、可运行、符合意图、可发布。

### 13.2 子模块

| 子模块 | 功能 |
|---|---|
| `schema_validator` | Patch/file schema |
| `reference_validator` | 引用完整性 |
| `numeric_validator` | 数值范围 |
| `script_safety_validator` | 危险 API |
| `semantic_invariant_validator` | 机制不变量 |
| `probe_spec` | 运行探针描述 |
| `probe_runner` | 本地/云运行 |
| `evidence_capture` | 日志、截图、视频 |
| `intent_alignment` | 意图对齐评分 |
| `compatibility_validator` | Mod 兼容 |
| `certificate_builder` | 验证证书 |
| `udify_bench` | benchmark |

### 13.3 验证等级

| 等级 | 必需验证 |
|---|---|
| preview | schema |
| install | schema + reference + safety |
| export | install + reverse check |
| publish | export + runtime + intent + provenance |
| marketplace featured | publish + compatibility matrix + human review |

### 13.4 验收

- publish 不允许跳过 blocking stage。
- infrastructure_failed 不归因 patch。
- flaky probe 记录重试。
- 每个失败进入 taxonomy。

---

## 14. Mod 管理域

### 14.1 功能目标

管理 ModPackage、安装、卸载、组合、加载顺序、兼容性和迁移。

### 14.2 子模块

| 子模块 | 功能 |
|---|---|
| `mod_manifest` | 包元数据 |
| `mod_package_reader` | 读取包 |
| `mod_installer` | 安装到 VFS |
| `mod_uninstaller` | 卸载和回滚 |
| `mod_stack` | 多 Mod 组合 |
| `load_order_resolver` | 加载顺序 |
| `conflict_detector` | 文件/语义冲突 |
| `compatibility_matrix` | 兼容性 |
| `migration_planner` | 游戏版本迁移 |

### 14.3 冲突类型

- same file overwrite。
- same property conflict。
- semantic conflict。
- runtime hook conflict。
- load order conflict。
- license conflict。
- multiplayer policy conflict。

---

## 15. Memory and Knowledge 记忆知识域

### 15.1 功能目标

把用户偏好、成功模式、失败签名、社区反馈变成可复用知识。

### 15.2 子模块

| 子模块 | 功能 |
|---|---|
| `preference_store` | 用户偏好 |
| `pattern_store` | 成功 Patch 模板 |
| `failure_store` | 失败签名 |
| `embedding_index` | 语义检索 |
| `knowledge_graph` | 游戏知识 |
| `feedback_collector` | 显式/隐式反馈 |
| `learning_engine` | 更新权重 |
| `template_extractor` | 成功 Mod 到模板 |

### 15.3 反馈信号

| 信号 | 含义 |
|---|---|
| rating | 显式质量 |
| rollback | 强负反馈 |
| crash | 强负反馈 |
| playtime | 间接正/负 |
| reinstall | 正反馈 |
| uninstall | 负反馈 |
| comment | 需 sentiment/主题分析 |

### 15.4 隐私规则

- 用户偏好本地优先。
- 未授权数据不进入训练集。
- 可删除。
- 社区统计匿名化。

---

## 16. Supply and Ecosystem 供应链生态域

### 16.1 Supply 子模块

| 子模块 | 功能 |
|---|---|
| `artifact_registry` | artifact 存储 |
| `package_builder` | ModPackage |
| `sbom_generator` | 物料清单 |
| `signature_service` | 签名 |
| `license_reporter` | 授权报告 |
| `provenance_checker` | 完整性 |
| `publish_gates` | 发布门 |

### 16.2 Ecosystem 子模块

| 子模块 | 功能 |
|---|---|
| `listing_service` | Mod 页面 |
| `semantic_search` | 意图搜索 |
| `recommendation` | 推荐 |
| `review_service` | 评论和评分 |
| `moderation_queue` | 审核 |
| `creator_attribution` | 归因 |
| `template_market` | 模板库 |
| `bounty_system` | 悬赏 |

### 16.3 发布状态

```text
draft
  -> private_export
  -> submitted
  -> automated_review
  -> human_review_required
  -> published
  -> flagged
  -> deprecated
  -> archived
```

---

## 17. Governance 治理域

### 17.1 功能目标

保证安全、版权、隐私、审计和社区规则。

### 17.2 子模块

| 子模块 | 功能 |
|---|---|
| `policy_engine` | allow/deny/approval |
| `risk_taxonomy` | R0-R4 |
| `audit_log` | 链式审计 |
| `rbac` | 权限 |
| `secret_scanner` | secret 检测 |
| `copyright_risk` | 版权风险 |
| `content_policy` | 内容政策 |
| `privacy_manager` | consent/delete/anonymize |
| `appeal_workflow` | 申诉 |

### 17.3 强制人工确认

- runtime hook。
- 发布公开市场。
- 版权未知资产。
- 联网工具。
- 真实游戏目录写入。
- 多人/反作弊游戏。
- 高 blast radius patch。

---

## 18. Infrastructure 基础设施域

### 18.1 子模块

| 子模块 | 功能 |
|---|---|
| `event_bus` | 状态事件 |
| `cache_manager` | L1/L2/L3 |
| `config_center` | 配置 |
| `state_persistence` | session/job/graph |
| `object_store` | artifact |
| `graph_store` | graph backend |
| `vector_store` | embedding |
| `cloud_scheduler` | workload 调度 |
| `node_agent` | 云/边缘执行节点 |
| `observability` | logs/metrics/traces |
| `cost_controller` | 成本 |

### 18.2 本地到云升级

| 能力 | 本地 MVP | 云生产 |
|---|---|---|
| event | in-memory | Redis Streams |
| persistence | JSON/SQLite | PostgreSQL |
| graph | in-memory/NetworkX | Neo4j |
| vector | local embeddings | Qdrant |
| workflow | local runner | Temporal |
| artifact | filesystem | S3/MinIO |
| sandbox | process/container | gVisor/Firecracker |
| observability | structured logs | OpenTelemetry |

---

## 19. Presentation 表现层

### 19.1 CLI

核心命令：

```text
udify scan <game_root>
udify inspect <game_root>
udify plan <game_root> "<intent>"
udify preview <plan_id>
udify validate <patch_id>
udify package <patch_id>
udify install <mod_package>
udify rollback <session_id>
udify status <job_id>
```

### 19.2 API

核心资源：

- `/sessions`
- `/jobs`
- `/games`
- `/graphs`
- `/intents`
- `/plans`
- `/patches`
- `/validations`
- `/packages`
- `/mods`
- `/feedback`

### 19.3 Web/Editor

核心视图：

| 视图 | 功能 |
|---|---|
| Game Import | 导入和扫描 |
| Intent Console | 输入意图 |
| Plan Review | 候选方案、风险、影响 |
| Graph Explorer | 语义图查看 |
| Diff Preview | 文件/图差异 |
| Validation Report | 验证证据 |
| Mod Manager | 安装和组合 |
| Publish Flow | 发布门 |

---

## 20. 端到端功能 Epics

### Epic 1：本地安全预览

目标：用户能对 miu2d 游戏做 VFS 预览。

功能：

- 扫描游戏。
- 构建语义图。
- 编译意图。
- 生成计划。
- 应用 VFS。
- 静态验证。
- 展示 diff。

验收：

- 不写原文件。
- 可回滚。
- 10 个 golden case。

### Epic 2：脚本安全修改

目标：支持 Lua/DSL 脚本插入，并阻止危险 API。

功能：

- Tree-sitter Lua。
- DSL schema。
- ScriptPatch。
- script safety validator。
- reparse validation。

验收：

- 恶意 API 必拒。
- 插入点 stale 必拒。

### Epic 3：运行时验证

目标：Playwright 启动样例游戏并读取状态。

功能：

- ProbeSpec。
- ProbeRunner。
- evidence capture。
- failure taxonomy。

验收：

- 游戏启动验证。
- 状态断言。
- 截图/日志保存。

### Epic 4：ModPackage 和发布准备

目标：生成可回滚、可验证的包。

功能：

- ModManifest。
- reverse patch。
- validation certificate。
- package builder。
- draft export。

验收：

- 包 round-trip。
- manifest schema。
- reverse 存在。

### Epic 5：多引擎扩展

目标：RPG Maker 作为第二引擎。

功能：

- detector。
- JSON database parser。
- event graph。
- JSON patch emitter。
- static validator。

验收：

- actors/enemies/items/maps 解析。
- event reference 检查。

---

## 21. 测试策略

### 21.1 测试层级

| 层级 | 内容 |
|---|---|
| Unit | dataclass、parser、validator、risk scorer |
| Contract | adapter、tool、service request/response |
| Integration | intent -> graph -> patch -> validation |
| E2E | game root -> ModPackage |
| Benchmark | UdifyBench golden cases |
| Regression | 每个生产失败沉淀 |

### 21.2 必需测试集

- `test_foundation_contracts`
- `test_capability_profiles`
- `test_inventory_scanner`
- `test_semantic_lifter`
- `test_intent_compiler`
- `test_patch_compiler`
- `test_patch_reverse`
- `test_tool_gateway_policy`
- `test_validation_static`
- `test_runtime_probe`
- `test_mod_package`
- `test_execution_paths`

### 21.3 Golden Case 最小集

1. 修改初始 HP。
2. Boss 难度提升但 HP 不超过 1.35x。
3. NPC 给技能。
4. 危险脚本拒绝。
5. 悬空引用拒绝。
6. VFS 回滚 checksum 一致。
7. ModPackage 包含 reverse。
8. 发布缺证书被拒。
9. 目标低置信需要澄清。
10. 两个 Mod 同属性冲突。

---

## 22. 工程实施顺序

### Wave 0：冻结契约

- Foundation schemas。
- SourceSpan/Evidence/Confidence。
- CapabilityProfile。
- IntentAST/StructuredIntent。
- PatchOperation。
- ProbeSpec。
- ModManifest。

### Wave 1：本地闭环

- inventory scanner。
- miu2d adapter。
- semantic graph。
- intent compiler。
- deterministic planner。
- VFS patch。
- static validation。

### Wave 2：安全和验证

- ToolGateway。
- script safety。
- runtime probe。
- ValidationCertificate。
- UdifyBench。

### Wave 3：包和生态

- ModPackage。
- ModStack。
- compatibility。
- draft publish flow。
- feedback loop。

### Wave 4：多引擎和云

- RPG Maker。
- Unity runtime hook。
- cloud workload。
- scheduler。
- remote probe。

### Wave 5：Udiface 和产业化

- semantic search。
- marketplace。
- creator attribution。
- moderation。
- LiveOps。

---

## 23. 模块交付模板

每个模块交付必须写：

```markdown
## Scope
- Domain:
- Feature IDs:
- Non-goals:

## Contract
- Inputs:
- Outputs:
- Errors:
- Events:

## Data Ownership
- Owns:
- Reads:
- Writes:

## Validation
- Unit tests:
- Contract tests:
- Integration tests:
- Golden cases:

## Risk
- Security:
- Privacy:
- Cost:
- Rollback:
```

---

## 24. 成功标准

系统设计成功不看文档厚度，而看能否做到：

1. 任意模块都有清晰 owner 和 non-goal。
2. 任意跨模块调用都有 request/response。
3. 任意 Patch 都有 SourceSpan、reverse、risk、probe。
4. 任意发布物都有 manifest、provenance、validation certificate。
5. 任意失败能归因到模块并沉淀 benchmark。
6. 任意高风险操作必须经过确认。
7. 任意用户数据都有隐私策略。
8. 任意开源工具都有 manifest、lock、audit。

---

## 25. 与其他文档关系

- 宏观工业调研：`RESEARCH-AI-NATIVE-GAME-INDUSTRY-STACK-2026.md`
- AI 原生工业蓝图：`BLUEPRINT-AI-NATIVE-GAME-INDUSTRY-v1.md`
- 细粒度模块地图：`MODULE-ATTACK-MAP-AI-GAME-INDUSTRY.md`
- 深层模块规格：`DEEP-TECHNICAL-MODULE-SPEC-AI-GAME-v1.md`
- 接口契约：`INTERFACE-CONTRACTS-AI-GAME-INDUSTRY-v1.md`
- 执行路径：`EXECUTION-PATHS-AI-GAME-INDUSTRY-v1.md`
