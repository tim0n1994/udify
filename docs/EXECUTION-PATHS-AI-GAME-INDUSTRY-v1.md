<!--
status: aspirational
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 愿景/未验证蓝图。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# AI 原生游戏工业端到端执行路径 v1

> 用具体执行路径把深层模块串起来。每条路径都说明模块调用顺序、关键数据、确认点、失败分支、测试夹具和成功指标。

---

## 0. 路径总览

| 路径 | 目标 | 对应 Udify 阶段 |
|---|---|---|
| Path A | 本地 miu2d 配置 Mod | 当前 MVP |
| Path B | 脚本 Patch + 安全验证 | v3 核心 |
| Path C | 云端运行时验证 | GameAI Fabric |
| Path D | Unity Runtime Hook Mod | 多引擎扩展 |
| Path E | 公开发布和兼容性证书 | Udiface |
| Path F | LiveOps 平衡性候选 | 专业开发平台 |

---

## 1. Path A：本地 miu2d 配置 Mod

目标：用户输入“让第一个 Boss 更难，但不要单纯翻倍血量”，系统生成 VFS 预览和可回滚 Patch。

### 1.1 调用链

```text
CapabilityService.profile_device
  -> InventoryService.scan
  -> EngineDetector.detect(miu2d)
  -> SemanticGraphService.build
  -> IntentCompiler.compile
  -> PatchCompiler.plan
  -> PolicyService.evaluate_plan
  -> PatchCompiler.emit
  -> PatchExecutor.apply_to_vfs
  -> ValidationService.validate_patch(preview)
  -> PreviewFormatter.render
```

### 1.2 关键数据

输入：

```yaml
raw_intent: "让第一个 Boss 更难，但不要单纯翻倍血量"
game_root: /path/to/game
mode: preview
```

中间数据：

- `CapabilityProfile`
- `RawInventory`
- `GameSemanticGraph`
- `StructuredIntent`
- `PatchPlan`
- `CDLPatch`
- `VFSOverlay`
- `ValidationReport`

输出：

```yaml
PreviewResult:
  status: ready
  plan_summary: string
  diff_refs: [ArtifactRef]
  risk: R1 | R2
  validation:
    static: passed
    runtime: skipped
  next_actions:
    - run_runtime_probe
    - export_draft_package
```

### 1.3 确认点

默认不需要人工确认，因为：

- 只写 VFS。
- 不执行外部高风险工具。
- 可回滚。

需要确认的情况：

- 目标 Boss 置信度低。
- Patch 触碰主线任务。
- 计划只通过 HP 放大实现，违反用户约束。

### 1.4 失败分支

| 失败 | 处理 |
|---|---|
| 未检测到 miu2d | 进入 generic mode，只生成分析报告 |
| Boss 目标模糊 | 返回候选目标，请用户选择 |
| 无 SourceSpan | 只生成 graph patch，不生成 file patch |
| 静态验证失败 | 自动回滚 VFS |

### 1.5 测试夹具

- fixture：包含 2 个 Boss 的 miu2d 样例。
- golden：第一个 Boss 被正确选中。
- forbidden：HP factor 不超过 1.35。
- assertion：VFS diff 中不包含主线剧情文件。

---

## 2. Path B：脚本 Patch + 安全验证

目标：用户输入“让新手村导师对话后给火球术”，系统修改脚本，但必须阻止危险 API。

### 2.1 调用链

```text
IntentCompiler.compile
  -> SemanticGraphService.query(NPC mentor)
  -> PatchCompiler.plan(script_insert)
  -> ToolGateway.call(Tree-sitter Lua parse)
  -> ValidationService.static_safety
  -> PolicyService.evaluate_plan
  -> PatchExecutor.apply_to_vfs
  -> ValidationService.reparse
```

### 2.2 ScriptPatch 契约

```yaml
ScriptPatch:
  target:
    entity_id: npc_mentor
    source_span: talk/mentor.lua:function:on_dialog_end
  insertion:
    strategy: after_statement
    guard: "if not player.has_skill('fireball')"
    body_ast: ...
  safety:
    forbidden_calls: [os.execute, io.open, require_network]
```

### 2.3 安全门

必须检查：

- AST 可解析。
- 无文件系统危险 API。
- 无网络 API。
- 无无限循环明显模式。
- 插入点函数存在。
- reward item/skill id 存在。

### 2.4 失败分支

| 失败 | 归因 |
|---|---|
| `script_parse_failed` | parser/patch emitter |
| `dangerous_api_detected` | validation/security |
| `skill_not_found` | semantic graph |
| `insert_anchor_missing` | source span stale |

测试：

- good script insert。
- malicious generated body 包含 `os.execute`。
- missing skill id。
- stale source span。

---

## 3. Path C：云端运行时验证

目标：本地生成 Patch 后，把 VFS overlay 上传云端，在 GPU/浏览器节点执行 runtime probe，返回证据。

### 3.1 调用链

```text
ValidationService.create_runtime_plan
  -> WorkloadPlanner.create_descriptor
  -> Scheduler.place
  -> ArtifactManager.upload(game_snapshot, vfs_overlay)
  -> NodeAgent.execute(ProbeRunner)
  -> ProbeRunner.run
  -> EvidenceBundle.store
  -> ValidationService.aggregate
```

### 3.2 WorkloadDescriptor

```yaml
workload_type: runtime_probe
resources:
  cpu_cores: 4
  memory_mb: 8192
  gpu:
    required: true
    min_vram_mb: 4096
    features: [vulkan, video_encode]
sandbox:
  isolation: container
  network_allowed: false
determinism:
  seed_required: true
  record_inputs: true
  capture_video: true
```

### 3.3 云端节点要求

节点必须报告：

- GPU API。
- VRAM。
- video encode。
- browser/runtime 版本。
- cached engine/game artifacts。

### 3.4 失败分支

| 失败 | 处理 |
|---|---|
| insufficient_vram | 调度 fallback node |
| browser_launch_failed | infrastructure_failed，不归因 Patch |
| assertion_failed | patch validation failed |
| video_capture_failed | warning，除非 publish 要求视频 |
| node_preempted | retry if idempotent |

指标：

- queue latency。
- probe duration。
- infrastructure failure rate。
- flaky probe rate。

---

## 4. Path D：Unity Runtime Hook Mod

目标：对 Unity 游戏生成 BepInEx/Harmony 风格 runtime hook，而不是直接改原包。

### 4.1 调用链

```text
EngineDetector.detect(Unity)
  -> ToolGateway.call(AssetRipper manifest)
  -> SemanticGraphService.build(Unity partial graph)
  -> IntentCompiler.compile
  -> PatchCompiler.plan(runtime_hook)
  -> PolicyService.evaluate_plan(R4)
  -> HumanApproval.wait
  -> PatchCompiler.emit(RuntimeHookPatch)
  -> PackageService.build(BepInEx plugin package)
  -> ValidationService.runtime_probe
```

### 4.2 RuntimeHookPatch

```yaml
RuntimeHookPatch:
  hook_target:
    assembly: Assembly-CSharp.dll
    type_name: EnemyStats
    method_name: CalculateDamage
  hook_type: prefix | postfix | transpiler
  codegen:
    language: csharp
    framework: harmony
  disable_plan:
    remove_plugin: true
  risk: R4
```

### 4.3 必须确认

Runtime Hook 永远需要确认，因为：

- 执行代码。
- 可能触发反作弊。
- 可能影响多人公平。
- 可能与其他 Hook 冲突。

### 4.4 失败分支

| 失败 | 处理 |
|---|---|
| symbol_not_found | 尝试 Roslyn/反射候选，否则人工 |
| anti_cheat_detected | 拒绝 |
| multiplayer_mode | 默认拒绝自动生成 |
| hook_conflict | 加入 compatibility matrix |

---

## 5. Path E：公开发布和兼容性证书

目标：将 ModPackage 发布到 Udiface，必须经过供应链和验证门。

### 5.1 调用链

```text
PackageService.build
  -> SupplyGate.schema
  -> SupplyGate.license
  -> SupplyGate.security
  -> SupplyGate.validation
  -> CompatibilityService.sample_matrix
  -> SignatureService.sign
  -> PublishingService.publish
  -> EcoIndex.index
```

### 5.2 发布门

| Gate | 必需数据 |
|---|---|
| schema | manifest、patch、reverse |
| license | license hint、asset provenance |
| security | risk report、tool audit |
| validation | validation certificate |
| compatibility | ModStack sample |
| provenance | tool lock、asset history |

### 5.3 兼容性证书

```yaml
CompatibilityCertificate:
  mod_id: string
  tested_against:
    - mod_id: popular_mod_a
      result: compatible
    - mod_id: popular_mod_b
      result: conflict
      conflict_type: same_property
  load_order_rules:
    - load_after: popular_mod_a
```

### 5.4 失败分支

| 失败 | 用户可见结果 |
|---|---|
| license unknown | draft only |
| validation failed | cannot publish |
| compatibility warning | publish with warning |
| security R4 unapproved | require approval |
| provenance incomplete | reject public publish |

---

## 6. Path F：LiveOps 平衡性候选

目标：专业团队根据玩家反馈生成平衡性 Patch 候选，不直接上线。

### 6.1 调用链

```text
TelemetryCloud.aggregate
  -> ExperienceAnalyzer.detect_issue
  -> IntentCompiler.from_metric_anomaly
  -> PatchCompiler.plan
  -> SimCloud.batch_validate
  -> DesignerReview
  -> ABExperimentPlanner
  -> RolloutController
```

### 6.2 输入信号

- 某 Boss 通过率过低。
- 某装备使用率过高。
- 某任务放弃率高。
- 某 ModStack 崩溃率高。
- 某地图区域死亡热力图异常。

### 6.3 输出

```yaml
LiveOpsPatchCandidate:
  candidate_id: string
  issue: string
  patch_plan: PatchPlan
  simulation_results: [ProbeResult]
  expected_impact:
    retention: float
    difficulty: float
    economy: float
  rollout:
    ab_groups: [string]
    rollback_condition: string
```

### 6.4 硬规则

- 不自动上线。
- 设计师必须确认。
- 必须有回滚条件。
- 必须隔离实验数据和训练数据。

---

## 7. 综合测试矩阵

### 7.1 Path 覆盖

| 测试 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| intent compile | yes | yes | no | yes | no | yes |
| semantic graph | yes | yes | no | yes | no | no |
| patch compile | yes | yes | no | yes | no | yes |
| tool gateway | optional | yes | yes | yes | no | no |
| policy | yes | yes | yes | yes | yes | yes |
| runtime probe | optional | optional | yes | yes | no | batch |
| package | draft | draft | no | yes | yes | no |
| publish | no | no | no | no | yes | no |

### 7.2 最小 CI

每次合并至少跑：

1. Path A golden case。
2. Path B dangerous script rejection。
3. Patch reverse round-trip。
4. ToolGateway path escape denial。
5. Validation report schema round-trip。

### 7.3 Nightly

每晚跑：

1. 云端 runtime probe。
2. 兼容性 sample matrix。
3. 多硬件 profile mock。
4. 大文件扫描。
5. benchmark 趋势报告。

---

## 8. 失败复盘格式

```markdown
## Failure
- Path:
- Error code:
- Owner module:

## Evidence
- Logs:
- Screenshot/video:
- Graph/Patch refs:

## Root Cause
- Schema:
- Tool:
- Planner:
- Runtime:
- Infra:

## Fix
- Code/task ID:
- New benchmark:
- Prevention:
```

原则：每个生产级失败都应沉淀成 benchmark 或 policy rule。

---

## 9. 近期最小执行建议

下一步不要再扩宏观蓝图，应开始按文档切任务。最小顺序：

1. 实现 schema 包，但仍不写业务逻辑。
2. 为 Path A 写完整 fixture 和 golden spec。
3. 为 Path B 写安全拒绝 spec。
4. 定义 ValidationCertificate 和 ModManifest schema。
5. 将 ToolGateway 作为所有外部工具的唯一入口。

这 5 步完成后，Udify 才真正从“模块集合”变成“可验证工业流程”。
