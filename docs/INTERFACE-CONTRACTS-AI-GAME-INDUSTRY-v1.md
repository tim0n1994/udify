<!--
status: aspirational
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 愿景/未验证蓝图。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# AI 原生游戏工业接口契约矩阵 v1

> 本文把深层模块之间的边界契约写清楚：谁调用谁、传什么、谁拥有数据、失败谁处理、什么情况下必须人工确认。目标是让工程师按接口并行施工。

---

## 0. 契约原则

1. **所有跨模块数据必须有 schema version**。
2. **所有副作用必须有 trace、audit 和 rollback plan**。
3. **所有低置信语义不得直接驱动文件写入**。
4. **所有工具调用必须经过 Tool Gateway**。
5. **所有可发布 Mod 必须有 Validation Certificate**。

---

## 1. 顶层接口流

```text
UserIntent
  -> IntentCompiler.compile()
  -> SemanticGraphService.resolve_context()
  -> PatchCompiler.plan()
  -> PolicyService.review_plan()
  -> PatchExecutor.apply_to_vfs()
  -> ValidationService.validate()
  -> PackageService.package()
  -> PublishingService.publish()
  -> FeedbackService.learn()
```

---

## 2. 服务契约总表

| 服务 | 输入 | 输出 | 数据所有者 | 失败处理 |
|---|---|---|---|---|
| `CapabilityService` | device/cloud node | `CapabilityProfile` | Device/Cloud | fallback unknown |
| `InventoryService` | game root | `RawInventory` | Perception | partial inventory |
| `SemanticGraphService` | inventory + adapters | `GameSemanticGraph` | Perception | low confidence graph |
| `IntentCompiler` | raw text + user prefs | `StructuredIntent` | Cognition | clarification |
| `PatchCompiler` | intent + graph | `PatchPlan`/`CDLPatch` | Planning | no viable plan |
| `PolicyService` | plan/tool/package | `PolicyDecision` | Governance | deny/approval |
| `ToolGateway` | tool request | `ToolResult` | Tool layer | quarantine |
| `PatchExecutor` | patch + VFS | `PatchApplyResult` | Execution | rollback |
| `ValidationService` | patch/package | `ValidationReport` | Validation | failure taxonomy |
| `PackageService` | patch + evidence | `ModPackage` | Supply | package rejected |
| `PublishingService` | package + cert | publish result | Eco | moderation queue |
| `FeedbackService` | usage + rating | memory update | Memory | quarantine signal |

---

## 3. Capability Contracts

### 3.1 `CapabilityService.profile_device`

Request：

```yaml
ProfileDeviceRequest:
  request_id: string
  scope: local | cloud_node | edge_node
  probes:
    cpu: bool
    gpu: bool
    npu: bool
    storage: bool
    network: bool
  consent_token: string | null
```

Response：

```yaml
ProfileDeviceResponse:
  profile: CapabilityProfile
  warnings: [Finding]
  expires_at: datetime
```

契约：

- 不允许采集用户文件内容。
- 网络 probe 必须可关闭。
- profile 过期后不能用于 publish certificate，只能用于本地提示。

### 3.2 `WorkloadPlanner.create_descriptor`

Request：

```yaml
CreateWorkloadDescriptorRequest:
  job_id: string
  workload_kind: string
  patch_plan_ref: string | null
  validation_plan_ref: string | null
  artifact_refs: [string]
  desired_mode: local | edge | cloud | auto
```

Response：

```yaml
CreateWorkloadDescriptorResponse:
  descriptor: WorkloadDescriptor
  placement_hints: [string]
  fallback_descriptors: [WorkloadDescriptor]
```

契约：

- 必须有 fallback，除非任务本身明确不可降级。
- GPU 图形任务和 GPU 推理任务要标明互斥或可共享。

---

## 4. Semantic Graph Contracts

### 4.1 `InventoryService.scan`

Request：

```yaml
InventoryScanRequest:
  game_root: string
  include_patterns: [string]
  exclude_patterns: [string]
  hash_mode: fast | strong
  previous_snapshot: string | null
```

Response：

```yaml
RawInventory:
  inventory_id: string
  game_root_hash: string
  files:
    - path: string
      size: int
      mtime: datetime
      hash: string
      media_guess: string
  changed_since_previous: [string]
```

失败模式：

- `permission_denied`
- `path_too_large`
- `hash_failed`

处理：

- 权限失败文件进入 warning，不阻塞全图构建。
- 如果核心文件不可读，阻塞。

### 4.2 `SemanticGraphService.build`

Request：

```yaml
BuildSemanticGraphRequest:
  inventory_id: string
  engine_hint: string | null
  adapter_ids: [string]
  confidence_threshold: float
  mode: full | incremental
```

Response：

```yaml
BuildSemanticGraphResponse:
  graph_id: string
  graph_version: string
  confidence_summary:
    high: int
    medium: int
    low: int
  unresolved_references: [Finding]
  protected_scopes: [GraphScope]
```

契约：

- 图可以在低置信下返回，但 PatchCompiler 只能对高置信 target 自动写入。
- 每个 editable property 必须有 SourceSpan。
- 每个 semantic tag 必须有 EvidenceRef。

### 4.3 `SemanticGraphService.query`

Request：

```yaml
GraphQueryRequest:
  graph_id: string
  query:
    type: semantic | structural | source | hybrid
    expression: string
  include_evidence: bool
  max_nodes: int
```

Response：

```yaml
GraphQueryResponse:
  nodes: [SemanticEntity]
  relations: [SemanticRelation]
  evidence: [EvidenceRef]
  truncation: bool
```

契约：

- LLM prompt 使用 graph query 时必须设置 `max_nodes`。
- 被截断的结果不能用于高风险自动决策。

---

## 5. Intent Contracts

### 5.1 `IntentCompiler.compile`

Request：

```yaml
CompileIntentRequest:
  raw_text: string
  user_id: string | null
  game_context:
    graph_id: string | null
    engine: string | null
  preference_profile_ref: string | null
```

Response：

```yaml
CompileIntentResponse:
  intent_ast: IntentAST
  structured_intent: StructuredIntent
  ambiguity:
    level: low | medium | high
    questions: [ClarificationQuestion]
  risk_hints: [RiskHint]
```

契约：

- high ambiguity 不允许自动进入 PatchCompiler，除非用户选择“给我候选方案，不应用”。
- 所有 exclusion clause 必须转成 hard constraint 或 warning。

### 5.2 `ReferenceMapper.resolve`

Request：

```yaml
ResolveReferenceRequest:
  reference_text: string
  game_genre: string | null
  target_systems: [string]
```

Response：

```yaml
ReferenceResolution:
  reference_id: string
  features: [ReferenceFeature]
  forbidden_shortcuts: [string]
  confidence: float
  evidence: [string]
```

契约：

- 风格参考只能贡献 feature targets，不能直接指定文件修改。

---

## 6. Patch Contracts

### 6.1 `PatchCompiler.plan`

Request：

```yaml
CreatePatchPlanRequest:
  structured_intent: StructuredIntent
  graph_id: string
  constraints:
    max_cost_usd: float
    max_risk: R0 | R1 | R2 | R3 | R4
    execution_modes_allowed: [graph_only, file_patch, runtime_hook, package_overlay]
  planning_mode: deterministic | search | propose_only
```

Response：

```yaml
PatchPlanResponse:
  plans:
    - plan_id: string
      summary: string
      score: float
      risk: RiskScore
      impact: ImpactReport
      patch_preview: CDLPatch
      validation_plan: ValidationPlan
  rejected_candidates: [RejectedCandidate]
```

契约：

- 至少返回一个 `propose_only` 计划，除非 target 无法解析。
- plan 必须包含 impact report。
- risk R3/R4 plan 默认需要 approval。

### 6.2 `PatchCompiler.emit`

Request：

```yaml
EmitPatchRequest:
  plan_id: string
  selected_options: map
  graph_version: string
```

Response：

```yaml
EmitPatchResponse:
  patch: CDLPatch
  reverse_patch: CDLPatch
  validation_plan: ValidationPlan
```

契约：

- graph_version 不匹配必须拒绝。
- file_patch 必须有 reverse_patch。
- runtime_hook 必须有 disable plan。

### 6.3 `PatchExecutor.apply_to_vfs`

Request：

```yaml
ApplyPatchToVfsRequest:
  patch_id: string
  vfs_id: string
  mode: preview | install
  idempotency_key: string
```

Response：

```yaml
PatchApplyResult:
  status: applied | already_applied | failed | rolled_back
  touched_files: [string]
  graph_delta_ref: string
  file_diff_refs: [string]
  rollback_ref: string
```

契约：

- 重复 idempotency key 返回 `already_applied`。
- apply 失败必须自动 rollback。
- touched files 为空但 patch 非空时为异常。

---

## 7. Policy and Governance Contracts

### 7.1 `PolicyService.evaluate_plan`

Request：

```yaml
EvaluatePlanPolicyRequest:
  plan_id: string
  user_context:
    role: owner | editor | viewer | tester
  risk: RiskScore
  impact: ImpactReport
```

Response：

```yaml
PolicyDecision:
  decision: allow | deny | require_approval
  reasons: [string]
  required_approvals: [ApprovalRequirement]
  constraints_added: [Condition]
```

契约：

- deny 必须可解释。
- require_approval 必须指定 approval scope。

### 7.2 `PolicyService.evaluate_tool_call`

Request：

```yaml
EvaluateToolCallPolicyRequest:
  tool_id: string
  capability_id: string
  args_summary: map
  requested_paths: [string]
  network: bool
  risk_level: string
```

Response：同 `PolicyDecision`。

契约：

- ToolGateway 不得绕过该接口。
- 任何 path escape 直接 deny。

---

## 8. Tool Gateway Contracts

### 8.1 `ToolGateway.call`

Request：

```yaml
ToolCallRequest:
  tool_id: string
  capability_id: string
  args: map
  input_artifacts: [ArtifactRef]
  requested_paths: [string]
  timeout_seconds: int
  trace: TraceContext
```

Response：

```yaml
ToolCallResult:
  status: success | failed | denied | timeout | quarantined
  stdout_ref: string | null
  stderr_ref: string | null
  output_artifacts: [ArtifactRef]
  findings: [Finding]
  audit_ref: string
```

契约：

- stdout/stderr 超过限制必须落 artifact，不直接进内存。
- timeout 必须终止子进程/容器。
- failed 不等于 quarantined；contract test 失败才 quarantine。

---

## 9. Validation Contracts

### 9.1 `ValidationService.validate_patch`

Request：

```yaml
ValidatePatchRequest:
  patch_id: string
  graph_id: string
  vfs_id: string
  validation_plan: ValidationPlan
  required_level: preview | install | publish
```

Response：

```yaml
ValidationReport:
  status: passed | failed | warning | skipped
  blocking_findings: [Finding]
  warnings: [Finding]
  probe_results: [ProbeResult]
  intent_alignment: IntentAlignmentReport
  recommended_action: approve | revise | reject | human_review
```

契约：

- `required_level=publish` 不允许 skipped blocking stage。
- failed report 必须有 failure taxonomy。

### 9.2 `ProbeRunner.run`

Request：

```yaml
RunProbeRequest:
  probe_spec: ProbeSpec
  workload_descriptor: WorkloadDescriptor
  artifact_refs:
    game_snapshot: string
    vfs_overlay: string
```

Response：

```yaml
ProbeResult:
  status: passed | failed | flaky | infrastructure_failed
  observations: [RuntimeObservation]
  evidence_bundle: ArtifactRef
  performance:
    avg_frame_ms: float | null
    peak_memory_mb: int | null
    vram_mb: int | null
  failure: FailureRecord | null
```

契约：

- infrastructure_failed 不得当作 patch failed。
- flaky 必须记录每次尝试。

---

## 10. Cloud Contracts

### 10.1 `Scheduler.place`

Request：

```yaml
PlaceWorkloadRequest:
  descriptor: WorkloadDescriptor
  candidate_scope:
    local_allowed: bool
    edge_regions: [string]
    cloud_regions: [string]
```

Response：

```yaml
PlaceWorkloadResponse:
  decision: SchedulingDecision
  reservation_id: string | null
  fallback: [SchedulingDecision]
```

契约：

- 每个 rejected node 必须有 reason。
- 如果 budget exceeded，返回降级 workload 建议。

### 10.2 `NodeAgent.execute`

Request：

```yaml
ExecuteOnNodeRequest:
  reservation_id: string
  workload_descriptor: WorkloadDescriptor
  artifacts: [ArtifactRef]
```

Response：

```yaml
NodeExecutionResult:
  status: success | failed | preempted | infrastructure_failed
  output_artifacts: [ArtifactRef]
  metrics: map
  logs_ref: string
```

契约：

- preempted workload 必须可重试或声明不可重试原因。
- node agent 不做业务解释，只返回原始结果和指标。

---

## 11. Supply Contracts

### 11.1 `PackageService.build`

Request：

```yaml
BuildPackageRequest:
  patch_id: string
  reverse_patch_id: string
  validation_report_id: string
  artifact_refs: [ArtifactRef]
  manifest_overrides: map
```

Response：

```yaml
BuildPackageResponse:
  package_id: string
  manifest: ModManifest
  package_artifact: ArtifactRef
  supply_findings: [Finding]
```

契约：

- package 必须包含 reverse patch。
- validation report 缺失则只能 export draft，不可 publish。

### 11.2 `PublishingService.publish`

Request：

```yaml
PublishRequest:
  package_id: string
  target: local_export | private_share | public_marketplace
  user_context: UserContext
```

Response：

```yaml
PublishResponse:
  status: published | queued_for_review | rejected | draft_exported
  url: string | null
  moderation_findings: [Finding]
```

契约：

- public_marketplace 必须经过 license/security/validation/provenance gates。
- rejected 必须可申诉或可修复。

---

## 12. Feedback Contracts

### 12.1 `FeedbackService.record`

Request：

```yaml
RecordFeedbackRequest:
  subject_type: patch | mod_package | template | probe | plan
  subject_id: string
  feedback_type: rating | rollback | crash | comment | playtime | install | uninstall
  value: any
  privacy:
    anonymized: bool
    user_consented: bool
```

Response：

```yaml
RecordFeedbackResponse:
  accepted: bool
  memory_updates: [MemoryUpdateRef]
```

契约：

- 未授权用户数据不得进入训练集。
- crash/rollback 是强负反馈。

---

## 13. 数据所有权矩阵

| 数据 | 所有者 | 可写模块 | 可读模块 |
|---|---|---|---|
| `CapabilityProfile` | CapabilityService | HWCAP/NodeAgent | Scheduler, ProbeRunner |
| `RawInventory` | InventoryService | InventoryService | SemanticGraph |
| `GameSemanticGraph` | SemanticGraphService | SemanticGraphService | Intent, Patch, Validation |
| `StructuredIntent` | IntentCompiler | IntentCompiler | PatchCompiler, Evaluation |
| `CDLPatch` | PatchCompiler | PatchCompiler | Executor, Validation, Package |
| `VFSOverlay` | PatchExecutor | PatchExecutor | Validation, Package |
| `ValidationReport` | ValidationService | ValidationService | Package, Publish, Feedback |
| `ModPackage` | PackageService | PackageService | Publish, Eco |
| `FeedbackSignal` | FeedbackService | FeedbackService | Memory, Planner |
| `AuditRecord` | AuditService | append-only | all read by permission |

---

## 14. 人工确认矩阵

| 场景 | 自动 | 需要确认 |
|---|---|---|
| 图级预览 | 是 | 否 |
| VFS 中修改配置 | 是 | 风险高时 |
| 写入真实游戏目录 | 否 | 是 |
| 运行外部 CLI | 低风险可自动 | R3 需要策略 |
| runtime hook | 否 | 是 |
| 联网工具 | 否 | 是 |
| 发布到公开市场 | 否 | 是 |
| 版权未知资产 | 否 | 是 |
| 多人/反作弊游戏 | 否 | 是 |

---

## 15. 接口版本策略

版本规则：

- `v1alpha`：实验，只在内部。
- `v1beta`：可被其他模块依赖，但允许兼容变更。
- `v1`：稳定，破坏性变更必须新增版本。

破坏性变更：

- 删除字段。
- 字段语义改变。
- enum 删除。
- 必填字段新增。
- 错误码改变。

非破坏性变更：

- 新增 optional 字段。
- enum 新增值，但消费者必须默认 unknown。
- warning 新增。

---

## 16. 错误码规范

```text
DOMAIN_CATEGORY_DETAIL
```

示例：

- `SEMANTIC_TARGET_LOW_CONFIDENCE`
- `PATCH_GRAPH_VERSION_MISMATCH`
- `TOOL_POLICY_PATH_ESCAPE`
- `VALIDATION_RUNTIME_LAUNCH_FAILED`
- `CLOUD_GPU_INSUFFICIENT_VRAM`
- `SUPPLY_LICENSE_BLOCKED`

错误对象：

```yaml
ErrorRecord:
  code: string
  message: string
  severity: info | warning | error | blocking
  retryable: bool
  owner_module: string
  suggested_action: string
  evidence: [EvidenceRef]
```

---

## 17. 并行开发切分

可以并行开工的包：

1. **Schema 包**：所有 Request/Response/Entity schema。
2. **HWCAP 包**：CapabilityProfile 和 WorkloadDescriptor。
3. **SEMIR 包**：SemanticEntity、SourceSpan、Evidence。
4. **PATCH 包**：PatchOperation、RiskScore、ImpactReport。
5. **VALID 包**：ProbeSpec、ProbeResult、ValidationCertificate。
6. **TOOL 包**：ToolManifest、ToolCallRequest、ToolCallResult。
7. **SUPPLY 包**：ModManifest、Artifact、Package layout。

依赖顺序：

```text
Schema -> HWCAP/SEMIR/PATCH/VALID/TOOL/SUPPLY
SEMIR -> PATCH
PATCH -> VALID
VALID -> SUPPLY
TOOL -> SEMIR/PATCH/VALID
HWCAP -> VALID/CLOUD
```
