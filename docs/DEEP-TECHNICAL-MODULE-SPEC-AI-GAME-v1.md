<!--
status: aspirational
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 愿景/未验证蓝图。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# AI 原生游戏工业深层技术模块规格 v1

> 继续下沉到可实施的技术模块。本文件不是宏观蓝图，而是把硬件、运行时、语义 IR、Patch 编译、验证、云调度和供应链拆成内部组件、数据流、失败模式、指标和测试夹具。

---

## 0. 分层模块总线

所有模块通过五类总线协作：

| 总线 | 传输内容 | 示例 |
|---|---|---|
| `CapabilityBus` | 硬件、运行时、云资源能力 | GPU VRAM、NPU backend、DirectStorage 支持 |
| `SemanticBus` | 内容图谱、机制图、资产 provenance | Boss 节点、任务边、资产授权 |
| `PatchBus` | 计划、Patch、反向 Patch、风险 | NumericPatch、RuntimeHookPatch |
| `ValidationBus` | 静态/运行时/仿真/兼容性结果 | ProbeResult、ValidationCertificate |
| `SupplyBus` | 发布物、签名、SBOM、市场元数据 | ModPackage、CompatibilityCertificate |

每条消息必须携带：

```yaml
trace:
  trace_id: string
  session_id: string
  job_id: string
  module_id: string
  schema_version: string
  created_at: datetime
  producer: string
```

---

## 1. HWCAP 深层规格

### 1.1 Capability Profiler

职责：将设备和云节点能力转成统一 `CapabilityProfile`。

内部子组件：

| 子组件 | 职责 | 数据来源 |
|---|---|---|
| `CpuProbe` | 核心数、线程数、SIMD、频率估计 | OS API |
| `GpuProbe` | API、VRAM、RT、compute、video encode | DX/Vulkan/Metal/NVML |
| `NpuProbe` | CoreML/DirectML/ONNX EP 可用性 | runtime backend |
| `StorageProbe` | SSD/HDD、吞吐、随机读 | micro benchmark |
| `NetworkProbe` | edge/cloud latency、jitter | ping/http probe |
| `ThermalProbe` | 掌机/移动热状态 | OS telemetry |
| `PolicyProbe` | 设备是否允许本地扫描/推理 | user consent |

输出 schema：

```yaml
CapabilityProfile:
  profile_id: string
  device_class: pc | console | handheld | mobile | cloud_node | edge_node
  cpu:
    logical_cores: int
    physical_cores: int | null
    simd: [string]
    estimated_score: float
  gpu:
    vendor: string | null
    api: [directx12, vulkan, metal, webgpu, opengl]
    vram_mb: int | null
    ray_tracing: unsupported | supported | unknown
    compute: unsupported | supported | unknown
    video_encode: [h264, hevc, av1]
    neural_features: [tensor, matrix, wave_mma]
  npu:
    available: bool
    backends: [coreml, directml, nnapi, onnxruntime]
    estimated_tops: float | null
  storage:
    type: hdd | sata_ssd | nvme | unknown
    sequential_read_mb_s: float
    random_read_iops: float
    direct_storage_capable: bool | null
  network:
    region: string | null
    latency_ms_by_region: map[string, float]
  privacy:
    local_only: bool
    upload_allowed: bool
```

失败模式：

| 失败 | 降级 |
|---|---|
| GPU 识别失败 | 标记 unknown，不调度 GPU-only probe |
| NPU backend 缺失 | 回退 CPU/GPU 推理 |
| 存储测试被权限阻止 | 使用保守默认值 |
| 网络不可用 | 本地模式 |

指标：

- `capability_probe_duration_ms`
- `capability_unknown_ratio`
- `profile_cache_hit_rate`
- `profile_staleness_seconds`

测试夹具：

- PC 高端 GPU。
- 低端集显。
- Steam Deck/掌机。
- 云 GPU 节点。
- 无网络本地模式。

### 1.2 Workload Mapper

职责：将 Udify 任务映射为资源需求。

输入：

- `PatchPlan`
- `ValidationPlan`
- `AssetJob`
- `InferenceJob`
- `CapabilityProfile`

输出：

```yaml
WorkloadDescriptor:
  workload_id: string
  workload_type: graph_build | patch_apply | runtime_probe | playtest | asset_compile | llm_infer | package_publish
  priority: low | normal | high | interactive
  resources:
    cpu_cores: float
    memory_mb: int
    gpu:
      required: bool
      min_vram_mb: int | null
      features: [vulkan, directx12, metal, nvenc, av1_encode, cuda, rocm]
      partition: none | mig | time_slicing | vgpu
    storage:
      temp_mb: int
      sequential_read_mb_s: float | null
    network:
      egress: bool
      region_affinity: string | null
  sandbox:
    isolation: none | process | container | gvisor | firecracker
    writable_paths: [string]
    network_allowed: bool
  determinism:
    seed_required: bool
    record_inputs: bool
    capture_video: bool
  timeout_seconds: int
```

映射规则：

| 任务 | 资源策略 |
|---|---|
| 静态解析 | CPU + RAM，本地优先 |
| miu2d Playwright probe | CPU + browser，GPU optional |
| Unity/Unreal runtime probe | GPU required，video encode optional |
| LLM planning | InferCloud or API，本地小模型可降级 |
| asset upscaling | GPU required，batch queue |
| compatibility matrix | 云端批量并行 |

关键约束：

- DirectStorage/GPU decompression 类能力不能假设可用，必须检测并记录 fallback。
- GPU 既可能用于渲染，也可能用于推理，同一 workload 不得隐式抢占。
- MIG 适合推理和部分 compute，不适合所有图形渲染 workload。

参考：Microsoft DirectStorage 文档说明游戏需要处理压缩和解压路径；NVIDIA MIG 文档说明 MIG 可将支持的 GPU 切分为隔离实例；Kubernetes DRA 提供更灵活的设备资源分配模型。

---

## 2. Game Semantic IR 深层规格

### 2.1 Semantic Object Model

核心对象：

```yaml
SemanticEntity:
  entity_id: string
  canonical_type: Actor | Enemy | Boss | NPC | Item | Skill | Buff | Quest | Dialog | Map | Region | Trigger | Asset | Script | RuntimeHook
  names:
    display: string | null
    internal: string | null
    aliases: [string]
  properties: map[string, SemanticProperty]
  tags: [SemanticTag]
  provenance: [ProvenanceRef]
  evidence: [EvidenceRef]
  confidence: ConfidenceScore
  runtime_observations: [RuntimeObservationRef]
```

```yaml
SemanticRelation:
  relation_id: string
  relation_type: contains | references | triggers | rewards | requires | modifies | spawns | loads | overrides | conflicts_with
  source_entity_id: string
  target_entity_id: string
  properties: map
  provenance: [ProvenanceRef]
  confidence: ConfidenceScore
```

```yaml
SemanticProperty:
  key: string
  value: scalar | list | map
  unit: hp | percent | seconds | frames | tiles | currency | enum | unknown
  source_span: SourceSpan
  confidence: ConfidenceScore
  mutability: immutable | editable | generated | runtime_only
  constraints:
    min: number | null
    max: number | null
    enum_values: [string] | null
```

### 2.2 SourceSpan and Evidence

```yaml
SourceSpan:
  source_id: string
  source_kind: file | archive_member | asset_bundle | script_ast | runtime_trace | generated
  path: string
  archive_path: string | null
  byte_start: int | null
  byte_end: int | null
  line_start: int | null
  line_end: int | null
  column_start: int | null
  column_end: int | null
  ast_path: string | null
  content_hash: string
```

```yaml
EvidenceRef:
  evidence_id: string
  evidence_type: schema_rule | filename_pattern | ast_reference | runtime_observation | llm_label | user_confirmed | community_pattern
  summary: string
  source_spans: [SourceSpan]
  confidence_contribution: float
```

证据等级：

| 等级 | 含义 | 示例 |
|---|---|---|
| E0 | 弱猜测 | 文件名相似 |
| E1 | 结构证据 | schema 字段 `MaxLife` |
| E2 | 引用证据 | 脚本引用 NPC id |
| E3 | 运行证据 | probe 读取到 Boss HP |
| E4 | 人类确认 | 用户/工程师确认 |

写入规则：

- E0/E1 只能创建候选标签。
- E2 可写入图谱但标记中置信。
- E3/E4 可提升为高置信。
- LLM 标签必须至少绑定 E1 或 E2，不能裸写。

### 2.3 Semantic Lifter Pipeline

```text
RawInventory
  -> FormatParser
  -> SyntaxGraph
  -> ReferenceGraph
  -> CandidateEntityExtractor
  -> OntologyMapper
  -> EvidenceScorer
  -> RuntimeObservationMerger
  -> GameSemanticGraph
```

内部模块：

| 模块 | 输入 | 输出 | 失败模式 |
|---|---|---|---|
| `FormatParser` | 文件 | AST/records | parse_error |
| `ReferenceGraphBuilder` | records/AST | references | unresolved_ref |
| `EntityExtractor` | syntax graph | candidate entities | duplicate_entity |
| `OntologyMapper` | candidate | canonical type | unknown_type |
| `EvidenceScorer` | evidence | confidence | low_confidence |
| `ObservationMerger` | runtime probe | updated confidence | stale_observation |

### 2.4 MechanismGraph

`MechanismGraph` 是玩法层，不是文件层。

核心节点：

```text
DamageFormula, DefenseFormula, DropTable, ShopInventory,
QuestStep, QuestGate, DialogBranch, SpawnRule, EncounterRule,
ProgressionGate, SavePoint, DeathPenalty, HealingLoop,
ResourceSink, ResourceSource, DifficultySpike
```

机制边：

| 边 | 语义 |
|---|---|
| `feeds` | 资源产出进入另一个系统 |
| `gates` | 条件阻塞进度 |
| `amplifies` | 增强难度或收益 |
| `mitigates` | 缓解惩罚 |
| `balances` | 与另一机制平衡 |
| `breaks_if_removed` | 删除会破坏 |

机制不变量：

```yaml
GameplayInvariant:
  invariant_id: string
  scope: graph_query
  expression: string
  severity: blocking | warning | info
  examples:
    - "main_quest must have path from start to ending"
    - "starter_area enemies average_damage_per_second < player_hp * 0.35"
```

---

## 3. Intent OS 深层规格

### 3.1 Intent AST

自然语言不是直接变 Patch，而是先变 Intent AST：

```yaml
IntentAST:
  intent_id: string
  raw_text: string
  language: zh | en | ja | mixed | unknown
  clauses:
    - clause_id: string
      clause_type: goal | constraint | reference | exclusion | preference | scope | acceptance
      text: string
      normalized: string
      confidence: float
  global_scope:
    game_area: string | null
    systems: [combat, economy, narrative, map, ui, audio, visual]
  risk_hints: [string]
```

例：

```text
"让第一个 Boss 更像魂系，但不要单纯翻倍血量，也别改主线剧情"
```

拆成：

- goal：第一个 Boss 更难、更需要学习模式。
- reference：魂系。
- exclusion：不要单纯翻倍血量。
- constraint：不改主线剧情。
- scope：Boss/战斗系统。

### 3.2 Intent Lowering

`IntentAST` 降级为 `StructuredIntent`：

```yaml
StructuredIntent:
  primary_goal:
    type: difficulty_adjustment
    target_selector:
      semantic_type: Boss
      ordinal: first
  feature_targets:
    - feature: pattern_learning
      desired_direction: increase
    - feature: punishment
      desired_direction: increase
    - feature: raw_hp_inflation
      desired_direction: avoid
  constraints:
    - id: no_main_story_change
      type: scope_exclusion
      query: "type in [Quest, MainDialog]"
    - id: no_hp_double
      type: numeric_bound
      target_property: hp
      max_factor: 1.35
  acceptance:
    - probe: boss_hp_factor_under_1_35
    - probe: boss_has_new_attack_or_timing_pressure
```

### 3.3 Reference Feature Library

参考风格不能只存文本，要存机制向量。

```yaml
ReferenceFeature:
  reference_id: dark_souls_like
  features:
    - name: punishment
      mechanisms: [death_penalty, enemy_damage, checkpoint_distance]
    - name: pattern_learning
      mechanisms: [boss_phase, telegraph, dodge_window]
    - name: resource_pressure
      mechanisms: [healing_limit, stamina, item_scarcity]
  forbidden_shortcuts:
    - hp_only_scaling
```

### 3.4 Clarification Policy

触发澄清：

- target_selector 命中多个高风险目标。
- hard constraint 与 goal 冲突。
- Patch 需要 R4 权限。
- acceptance probe 无法生成。
- 用户意图涉及在线多人或反作弊。

不触发澄清：

- 低风险、可回滚、VFS 预览。
- 有明确默认策略。
- 只生成计划不应用。

---

## 4. Patch Compiler 深层规格

### 4.1 编译阶段

```text
StructuredIntent
  -> TargetResolution
  -> ActionExpansion
  -> CandidatePatchSet
  -> ConstraintSolving
  -> ImpactAnalysis
  -> RiskScoring
  -> PlanRanking
  -> PatchEmission
  -> ReverseEmission
  -> ValidationPlanEmission
```

### 4.2 TargetResolution

输入：

- `StructuredIntent.target_selector`
- `GameSemanticGraph`

输出：

```yaml
TargetResolution:
  targets:
    - entity_id: boss_001
      confidence: 0.91
      evidence: [schema, ordinal, runtime_seen]
  alternatives:
    - entity_id: boss_tutorial
      confidence: 0.62
  ambiguity: low | medium | high
```

失败模式：

- `target_not_found`
- `target_ambiguous`
- `target_low_confidence`
- `target_protected_by_policy`

### 4.3 ActionExpansion

ActionSchema：

```yaml
ActionSchema:
  action_id: string
  action_type: numeric_scale | property_set | script_insert | event_modify | asset_replace | runtime_hook
  applicable_to: graph_query
  parameters:
    - name: factor
      type: float
      range: [0.1, 3.0]
  preconditions: [Condition]
  effects: [EffectDescriptor]
  cost_model: CostModel
  risk_model: RiskModel
  validators: [ValidatorRef]
```

`EffectDescriptor`：

```yaml
EffectDescriptor:
  system: combat | economy | narrative | map | rendering
  direction: increase | decrease | replace | add | remove
  magnitude_estimate: float
  confidence: float
```

### 4.4 ConstraintSolving

约束类型：

| 类型 | 示例 | 求解方式 |
|---|---|---|
| hard scope | 不改主线 | graph query filter |
| numeric bound | HP 不超过 1.35x | interval constraints |
| resource budget | cost < $1 | budget filter |
| risk limit | 不允许 R4 | policy filter |
| compatibility | 不冲突高频 Mod | compatibility graph |
| style | 魂系 | feature score |

输出：

```yaml
ConstraintReport:
  passed: bool
  rejected_actions:
    - action_id: scale_hp_2x
      reason: violates no_hp_double
  softened_constraints:
    - constraint_id: "not_too_hard"
      interpretation: "starter_area death_rate < 0.25"
```

### 4.5 ImpactAnalysis

影响半径：

```yaml
ImpactReport:
  direct_entities: [boss_001]
  indirect_entities: [drop_table_03, quest_gate_02, battle_scene_01]
  files_touched: [npc/boss_001.ini, script/boss_001.lua]
  systems_touched: [combat, reward]
  risk_flags:
    - touches_script
    - affects_progression_gate
  blast_radius_score: 0.42
```

图遍历规则：

- `references` 深度 1 默认。
- `triggers/requires/rewards` 深度 2。
- `main_quest` 保护边默认不穿透修改，只做影响报告。

### 4.6 RiskScoring

```text
risk =
  file_write_risk
  + script_execution_risk
  + runtime_hook_risk
  + blast_radius_risk
  + low_confidence_risk
  + copyright_risk
  + multiplayer_risk
  - reversibility_credit
  - validation_coverage_credit
```

等级：

| 等级 | 条件 | 处置 |
|---|---|---|
| R0 | 只读/分析 | 自动 |
| R1 | VFS 图级 patch | 自动 |
| R2 | 文件 patch，可回滚 | 验证后自动或确认 |
| R3 | 执行脚本/外部工具 | 沙箱 |
| R4 | runtime hook/联网/发布 | 人工确认 |

### 4.7 PatchEmission

Patch operation：

```yaml
PatchOperation:
  op_id: string
  op_kind: NumericPatch | ScriptPatch | EventPatch | AssetPatch | RuntimeHookPatch
  execution_mode: graph_only | file_patch | runtime_hook | package_overlay
  target:
    entity_id: string
    property_path: string | null
    source_span: SourceSpan
  payload:
    before: any
    after: any
    transform: any
  preconditions: [Condition]
  postconditions: [Condition]
  reverse: ReverseOperation
  probes: [ProbeSpec]
  risk: RiskScore
```

强制规则：

- 没有 source anchor，不允许 file_patch。
- 没有 reverse，不允许 R2 自动应用。
- 没有 probe，不允许发布证书。

---

## 5. Validation Fabric 深层规格

### 5.1 Validation Plan

```yaml
ValidationPlan:
  plan_id: string
  patch_id: string
  stages:
    - static_schema
    - static_reference
    - static_safety
    - runtime_smoke
    - runtime_target_probe
    - intent_alignment
    - compatibility_sample
  required_for:
    preview: [static_schema]
    install: [static_schema, static_reference, static_safety]
    publish: [all]
```

### 5.2 ProbeSpec

```yaml
ProbeSpec:
  probe_id: string
  engine: miu2d | rpg_maker | unity | godot | unreal | generic
  goal: string
  setup:
    save_state: string | null
    launch_args: [string]
    mod_stack: [string]
  actions:
    - type: wait_for_scene | click | keypress | call_debug_api | read_state | screenshot | assert
      args: map
  assertions:
    - expression: "boss_001.hp <= original.hp * 1.35"
      severity: blocking
  capture:
    logs: true
    screenshots: true
    video_seconds: 15
    performance: true
  determinism:
    seed: int | null
    input_recording: string | null
  timeout_seconds: 60
```

### 5.3 Runtime Observation

```yaml
RuntimeObservation:
  observation_id: string
  probe_id: string
  entity_id: string | null
  metric:
    name: string
    value: any
    unit: string
  evidence:
    screenshot: string | null
    video: string | null
    log_span: string | null
  confidence: float
```

### 5.4 Failure Taxonomy

| 失败类型 | 示例 | 归因模块 |
|---|---|---|
| `parse_after_patch_failed` | INI/Lua 修改后无法解析 | PatchEmitter |
| `reference_missing` | 奖励物品不存在 | SemanticGraph/Patch |
| `runtime_launch_failed` | 游戏无法启动 | RuntimeProbe |
| `state_assertion_failed` | Boss HP 未变化 | Patch/Probe |
| `performance_regression` | frame time 恶化 | Runtime/Asset |
| `probe_flaky` | 重试结果不一致 | Probe |
| `intent_mismatch` | 只加 HP，违背约束 | Planner |
| `policy_violation` | 尝试联网或越权路径 | ToolGateway |

### 5.5 Validation Certificate

```yaml
ValidationCertificate:
  certificate_id: string
  patch_id: string
  mod_package_id: string | null
  game_id: string
  game_version: string
  engine: string
  hardware_profiles: [CapabilityProfileRef]
  stages:
    static:
      status: passed | failed | skipped
      findings: [Finding]
    runtime:
      status: passed | failed | skipped
      probe_results: [ProbeResult]
    intent:
      score: float
      explanation: string
    compatibility:
      status: passed | warning | failed | skipped
  evidence_bundle: string
  signature: string | null
```

---

## 6. Tool Mesh 深层规格

### 6.1 Tool Adapter Lifecycle

状态机：

```text
registered
  -> resolved
  -> verified
  -> available
  -> quarantined
  -> deprecated
```

阶段：

| 阶段 | 检查 |
|---|---|
| registered | manifest schema |
| resolved | binary/library path |
| verified | hash/signature |
| available | health check |
| quarantined | 安全或 contract test 失败 |
| deprecated | 版本淘汰 |

### 6.2 Tool Manifest

```yaml
ToolManifest:
  tool_id: string
  name: string
  version: string
  kind: cli | library | mcp_server | web_service
  license: string | unknown
  binary:
    path: string | null
    sha256: string | null
    signature: string | null
  capabilities:
    - id: extract_assets
      input_schema: schema_ref
      output_schema: schema_ref
      risk_level: R3
  sandbox_defaults:
    network: false
    writable_paths: [workspace_cache]
    timeout_seconds: 300
  contract_tests:
    - test_asset_manifest_sample
```

### 6.3 Secure Execution Envelope

```yaml
ToolExecutionEnvelope:
  request: ToolCallRequest
  policy_decision: allow | deny | require_approval
  sandbox_profile: SandboxProfile
  resource_limits: ResourceLimits
  input_artifacts: [ArtifactRef]
  output_artifacts: [ArtifactRef]
  audit_record: AuditRecord
```

高风险工具规则：

- QuickBMS 脚本必须 allowlist。
- 资源提取工具默认无网络。
- LLM 生成脚本不得直接作为工具参数执行。
- GUI 工具自动化必须先有 headless 替代评估。

---

## 7. Cloud Fabric 深层规格

### 7.1 Control Plane

组件：

| 组件 | 内部队列 | 状态 |
|---|---|---|
| `WorkloadIngress` | incoming | accepted/rejected |
| `PolicyController` | policy_eval | allow/deny/approval |
| `CapabilityScheduler` | scheduling | pending/placed |
| `ArtifactManager` | artifact_ops | uploaded/verified |
| `CostController` | budget | reserved/exceeded |
| `TraceController` | trace_events | open/closed |

### 7.2 Scheduling Decision

```yaml
SchedulingDecision:
  workload_id: string
  selected_node: string
  reason:
    capability_match: float
    latency_score: float
    cache_score: float
    cost_score: float
    queue_score: float
  rejected_nodes:
    - node_id: gpu-node-1
      reason: insufficient_vram
```

调度拒绝原因：

- `missing_gpu_feature`
- `insufficient_vram`
- `no_video_encoder`
- `region_latency_too_high`
- `policy_denied`
- `budget_exceeded`
- `cache_miss_too_expensive`

### 7.3 Node Agent

每个云/边缘节点运行：

- Capability reporter。
- Artifact cache manager。
- Sandbox runtime。
- Probe executor。
- Metrics collector。
- Heartbeat。

Node heartbeat：

```yaml
NodeHeartbeat:
  node_id: string
  region: string
  capabilities: CapabilityProfile
  current_load:
    cpu: float
    memory: float
    gpu: float
    queue_depth: int
  cache:
    artifacts: [ArtifactRef]
  health: healthy | degraded | draining
```

### 7.4 GPU Partitioning Strategy

| workload | MIG | time slicing | full GPU | 说明 |
|---|---|---|---|---|
| embedding | 适合 | 适合 | 不必要 | 小推理 |
| LLM small | 适合 | 视模型 | 可能 | 看显存 |
| asset upscale | 视情况 | 不稳定 | 常用 | 批处理 |
| Unreal runtime probe | 通常不适合 | 风险 | 首选 | 需要图形栈 |
| video encode | 取决于 encoder | 取决于驱动 | 常用 | 需实际探测 |
| cloud streaming | 不适合 | 风险 | 首选 | 低延迟 |

---

## 8. Supply Chain 深层规格

### 8.1 Artifact Types

```yaml
Artifact:
  artifact_id: string
  type: raw_game_snapshot | graph_snapshot | patch | reverse_patch | vfs_overlay | mod_package | validation_evidence | tool_binary | model | asset
  content_hash: string
  size_bytes: int
  storage_uri: string
  provenance: [ProvenanceRef]
  retention_policy: string
```

### 8.2 ModPackage Layout

```text
mod_package/
  manifest.yaml
  patches/
    patch.cdl.yaml
    reverse.cdl.yaml
  overlays/
  assets/
  validation/
    certificate.yaml
    findings.json
    screenshots/
    videos/
    logs/
  provenance/
    asset_provenance.yaml
    tool_runs.yaml
    sbom.spdx.json
  signatures/
    package.sig
```

### 8.3 Manifest

```yaml
ModManifest:
  mod_id: string
  name: string
  version: semver
  game:
    engine: string
    game_id: string
    version_range: string
  intent:
    summary: string
    structured_intent_ref: string
  dependencies:
    requires: [mod_id]
    conflicts: [mod_id]
    load_after: [mod_id]
  capabilities_required:
    gpu: false
    runtime_hook: false
  validation_certificate: string
  license:
    mod_license: string
    asset_licenses: [LicenseHint]
```

### 8.4 Publishing Gates

| Gate | 条件 |
|---|---|
| `schema_gate` | manifest、patch、package schema 通过 |
| `license_gate` | 无 blocking license risk |
| `security_gate` | 无 R4 未确认能力 |
| `validation_gate` | publish 必需验证通过 |
| `compatibility_gate` | 兼容性结果存在 |
| `provenance_gate` | tool/asset provenance 完整 |

---

## 9. 测试矩阵

### 9.1 单模块测试

| 模块 | 测试 |
|---|---|
| CapabilityProfiler | mock hardware profiles |
| SemanticLifter | golden files to graph |
| IntentCompiler | natural language to IntentAST |
| PatchCompiler | intent + graph to patch |
| ToolGateway | policy deny/allow |
| RuntimeProbe | fake engine runner |
| CloudScheduler | workload placement |
| SupplyChain | package round-trip |

### 9.2 集成测试

| 场景 | 链路 |
|---|---|
| miu2d numeric mod | INTENT -> SEMIR -> PATCH -> VALID |
| script safety reject | INTENT -> PATCH -> TOOL/GOV deny |
| runtime probe fail | PATCH -> VALID -> FailureTaxonomy |
| cloud placement | WorkloadDescriptor -> Scheduler -> Node |
| publish package | VALID -> SUPPLY -> ECO |

### 9.3 压力测试

| 压力 | 指标 |
|---|---|
| 10k 文件扫描 | graph build time |
| 1k Mod compatibility | matrix time |
| 100 runtime probes | queue latency |
| 1TB asset cache | cache hit and eviction |
| 10k tool runs | audit write throughput |

---

## 10. 指标总表

| 指标 | 目标 |
|---|---|
| `intent_parse_p95_ms` | < 1500 |
| `semantic_graph_build_p95_ms_small` | < 5000 |
| `target_resolution_confidence_avg` | > 0.85 |
| `patch_reverse_coverage` | 100% for installable patches |
| `static_validation_pass_rate` | > 98% for generated patches |
| `runtime_probe_flake_rate` | < 3% |
| `tool_policy_bypass_count` | 0 |
| `artifact_provenance_completeness` | > 99% |
| `cloud_scheduler_rejection_explained` | 100% |
| `mod_publish_gate_false_negative` | tracked, target near 0 |

---

## 11. 与开源/官方能力的映射

| 能力 | 参考 |
|---|---|
| DirectStorage/GPU decompression/I/O 风险 | Microsoft DirectStorage docs |
| Vulkan ray tracing/descriptor/resource 模型 | Khronos Vulkan docs |
| GPU partitioning | NVIDIA MIG docs |
| Kubernetes 设备调度 | Kubernetes DRA, NVIDIA device plugin |
| 引擎 profiling | Unreal Insights, Unity Profiler |
| 图形 capture | RenderDoc |
| 浏览器运行时验证 | Playwright |
| 云游戏和远程验证 | Unreal Pixel Streaming, WebRTC |

参考链接：

- Microsoft DirectStorage: <https://learn.microsoft.com/en-us/gaming/gdk/docs/features/console/storage/directstorage/directstorage-overview>
- DirectStorage 1.1 GPU decompression: <https://devblogs.microsoft.com/directx/directstorage-1-1-now-available/>
- Vulkan Ray Tracing: <https://github.khronos.org/Vulkan-Site/spec/latest/chapters/raytracing.html>
- Kubernetes Dynamic Resource Allocation: <https://kubernetes.io/docs/concepts/scheduling-eviction/dynamic-resource-allocation/>
- NVIDIA MIG User Guide: <https://docs.nvidia.com/datacenter/tesla/mig-user-guide/>
- NVIDIA GPU Operator MIG: <https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-operator-mig.html>
- Unity Frame Timing Manager: <https://docs.unity3d.com/Manual/frame-timing-manager.html>
- Tracy profiler: <https://github.com/wolfpld/tracy>
- Playwright: <https://playwright.dev/>
