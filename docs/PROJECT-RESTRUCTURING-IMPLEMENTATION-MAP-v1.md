<!--
status: aspirational
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 愿景/未验证蓝图。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 项目重拆实施映射 v1

> 把 `SYSTEM-FUNCTIONAL-DESIGN-GUIDE-v1.md` 落到工程目录、模块迁移、功能迭代和 PR 切分。本文不是要求立即大搬家，而是给出从当前代码到新功能域架构的安全迁移路径。

---

## 0. 重拆原则

1. **先建契约，后搬目录**：先新增协议、schema、facade，再迁移实现。
2. **旧模块保留兼容 facade**：避免一次性破坏现有测试。
3. **每次迁移只改一个边界**：数据模型、调用方、实现目录不要同时大改。
4. **以端到端路径验收**：目录整齐不算成功，Path A/B/C 跑通才算。
5. **文档任务 ID 绑定 PR**：每个 PR 标注功能域和 Feature ID。

---

## 1. 目标目录结构

```text
udify/
  foundation/
    trace.py
    errors.py
    result.py
    versioning.py
    ids.py
    serialization.py

  capability/
    profile.py
    probes/
      cpu.py
      gpu.py
      npu.py
      storage.py
      network.py
    workload.py

  session/
    session.py
    job.py
    checkpoint.py
    approval.py
    events.py

  perception/
    inventory.py
    engine_detector.py
    source_index.py
    incremental.py
    parsers/
    adapters/

  semantic/
    graph.py
    entity.py
    relation.py
    source.py
    evidence.py
    confidence.py
    ontology.py
    lifter.py
    mechanism.py
    query.py
    overlay.py

  intent/
    ast.py
    compiler.py
    classifier.py
    constraints.py
    references.py
    ambiguity.py
    acceptance.py

  planning/
    target.py
    action_schema.py
    action_space.py
    constraints.py
    impact.py
    risk.py
    cost.py
    search.py
    ranker.py
    explainer.py

  patch/
    model.py
    target.py
    emitter.py
    emitters/
      numeric.py
      script.py
      json.py
      asset.py
      runtime_hook.py
    reverse.py
    idempotency.py
    renderer.py

  execution/
    vfs.py
    applicator.py
    scheduler.py
    transaction.py
    rollback.py
    dry_run.py

  tools/
    manifest.py
    registry.py
    gateway.py
    policy.py
    sandbox.py
    quota.py
    audit.py
    mcp_bridge.py
    adapters/

  validation/
    report.py
    static/
    runtime/
      probe_spec.py
      probe_runner.py
      evidence.py
    intent_alignment.py
    compatibility.py
    certificate.py
    bench/

  mod/
    manifest.py
    package.py
    installer.py
    stack.py
    conflicts.py
    compatibility.py
    migration.py

  memory/
    preferences.py
    patterns.py
    failures.py
    feedback.py
    embeddings.py
    learning.py

  supply/
    artifact.py
    registry.py
    sbom.py
    signature.py
    license.py
    gates.py

  ecosystem/
    listing.py
    search.py
    recommendation.py
    reviews.py
    moderation.py
    attribution.py
    templates.py

  governance/
    policy.py
    risk.py
    audit.py
    rbac.py
    secrets.py
    copyright.py
    privacy.py

  infrastructure/
    event_bus.py
    cache.py
    config.py
    persistence.py
    object_store.py
    graph_store.py
    vector_store.py
    observability.py
    cloud/

  presentation/
    cli.py
    api/
    web/
```

---

## 2. 当前代码到目标域映射

| 当前路径 | 目标域 | 迁移策略 |
|---|---|---|
| `udify/models/content_graph.py` | `semantic/graph.py`, `semantic/entity.py` | 先拆类型，保留旧 import facade |
| `udify/models/cdl_patch.py` | `patch/model.py`, `patch/reverse.py`, `patch/emitter.py` | 先复制 v3 optional 字段，再分文件 |
| `core/perception/*` | `perception/*`, `semantic/lifter.py` | parser 留 perception，语义提升迁 semantic |
| `core/cognition/*` | `intent/*` | 改名为 Intent OS，保留 cognition facade |
| `core/planning/*` | `planning/*` | 拆 target/action/risk/search/ranker |
| `core/execution/vfs.py` | `execution/vfs.py` | 可直接迁移 |
| `core/execution/tool_registry.py` | `tools/registry.py` | 加 gateway 后迁移 |
| `core/execution/mcp_server.py` | `tools/mcp_bridge.py` | 不再直接执行工具 |
| `core/validation/enhanced_validator.py` | `validation/static/*`, `validation/report.py` | 拆静态验证器 |
| `core/evaluation/intent_alignment.py` | `validation/intent_alignment.py` | 归入 validation |
| `core/mod_manager/*` | `mod/*` | 拆 package/stack/conflicts |
| `core/feedback/*` | `memory/feedback.py`, `memory/learning.py` | 反馈和学习拆开 |
| `core/knowledge/*` | `memory/*`, `semantic/ontology.py` | 游戏规则进 semantic，历史知识进 memory |
| `core/infrastructure/*` | `infrastructure/*`, `governance/audit.py` | audit 迁 governance |
| `core/security/sanitizer.py` | `governance/*`, `intent/input_sanitizer.py` | 输入消毒进 intent，策略进 governance |
| `core/session/*` | `session/*` | 扩展 ModJob |
| `core/pipeline_v2.py` | `presentation/cli` + `session/job_runner` | 拆 orchestration，不做巨型 pipeline |
| `core/toolchain/*` | `tools/adapters/*` | 每个工具独立 adapter |
| `cli.py` | `presentation/cli.py` | 保持入口兼容 |

---

## 3. 迁移 Wave 计划

### Wave 0：建立基础契约

目标：不改变行为，只新增基础类型。

新增：

- `foundation/trace.py`
- `foundation/errors.py`
- `foundation/result.py`
- `semantic/source.py`
- `semantic/evidence.py`
- `semantic/confidence.py`
- `capability/profile.py`

验收：

- 旧测试全过。
- 新类型 round-trip。
- 旧 ContentGraph 可以附加 optional provenance。

PR 切分：

| PR | 内容 |
|---|---|
| W0-PR1 | foundation 基础类型 |
| W0-PR2 | SourceSpan/Evidence/Confidence |
| W0-PR3 | CapabilityProfile/WorkloadDescriptor |

### Wave 1：Intent 和 Semantic 解耦

目标：把 cognition 改造成 intent 域，把 perception 中的语义逻辑抽出。

迁移：

- `core/cognition/intent.py` -> `intent/ast.py`
- `intent_classifier.py` -> `intent/classifier.py`
- `reference_resolver.py` -> `intent/references.py`
- 新增 `intent/compiler.py`
- 新增 `semantic/lifter.py`

验收：

- 输入意图可输出 IntentAST + StructuredIntent。
- SemanticGraph 每个 tag 有 evidence。

### Wave 2：Patch v3 和 Planning 拆分

目标：让 Patch 成为独立域。

迁移：

- `models/cdl_patch.py` 拆 `patch/model.py`
- 新增 `patch/target.py`
- 新增 `patch/reverse.py`
- 新增 `planning/target.py`
- 新增 `planning/impact.py`
- 新增 `planning/risk.py`

验收：

- PatchOperation 支持 execution_mode。
- file_patch 必须有 SourceSpan。
- reverse coverage 100% for installable patches。

### Wave 3：ToolGateway 强制边界

目标：外部工具调用不再散落。

迁移：

- `tool_registry.py` -> `tools/registry.py`
- `mcp_server.py` -> `tools/mcp_bridge.py`
- `toolchain/__init__.py` -> `tools/adapters/*`
- 新增 `tools/gateway.py`
- 新增 `tools/policy.py`
- 新增 `tools/audit.py`

验收：

- 所有工具调用走 ToolGateway。
- path escape 被拒绝。
- 大输出落 artifact。

### Wave 4：Validation Fabric

目标：验证域拆清楚。

迁移：

- `enhanced_validator.py` -> `validation/static/*`
- `intent_alignment.py` -> `validation/intent_alignment.py`
- 新增 `validation/runtime/probe_spec.py`
- 新增 `validation/runtime/probe_runner.py`
- 新增 `validation/certificate.py`
- 新增 `validation/bench/*`

验收：

- Path A 静态验证。
- Path B 危险脚本拒绝。
- ProbeSpec schema round-trip。

### Wave 5：ModPackage 和 Supply

目标：可导出 draft package。

迁移：

- `mod_exporter.py` -> `mod/package.py`
- `mod_manager.py` -> `mod/stack.py`, `mod/conflicts.py`
- 新增 `supply/artifact.py`
- 新增 `supply/gates.py`
- 新增 `supply/signature.py`

验收：

- ModPackage 包含 manifest、patch、reverse、validation。
- 缺 validation certificate 只能 draft export。

### Wave 6：Cloud 和 Ecosystem 预备

目标：不一定立即实现云，但 schema 和接口固定。

新增：

- `infrastructure/cloud/workload.py`
- `infrastructure/cloud/scheduler.py`
- `infrastructure/cloud/node_agent.py`
- `ecosystem/listing.py`
- `ecosystem/search.py`
- `ecosystem/moderation.py`

验收：

- WorkloadDescriptor 可被 scheduler mock placement。
- Publish gates 可以返回 queued/rejected/draft。

---

## 4. 功能到模块映射

### 4.1 扫描游戏

| 步骤 | 模块 |
|---|---|
| 读取目录 | perception.inventory |
| 计算 hash | perception.inventory |
| 检测引擎 | perception.engine_detector |
| 缓存结果 | infrastructure.cache |
| 记录事件 | infrastructure.event_bus |

### 4.2 构建语义图

| 步骤 | 模块 |
|---|---|
| parser 分发 | perception.format_router |
| 解析文件 | perception.parsers |
| 建 SourceSpan | perception.source_index |
| 抽实体 | semantic.entity_extractor |
| 建关系 | semantic.relation_builder |
| 打证据 | semantic.evidence_scorer |
| 写图 | semantic.graph |

### 4.3 编译意图

| 步骤 | 模块 |
|---|---|
| 输入消毒 | intent.input_sanitizer |
| clause 解析 | intent.parser |
| 分类 | intent.classifier |
| 参考映射 | intent.references |
| 约束抽取 | intent.constraints |
| 模糊检测 | intent.ambiguity |
| 验收规划 | intent.acceptance |

### 4.4 生成 Patch

| 步骤 | 模块 |
|---|---|
| 目标解析 | planning.target |
| action 扩展 | planning.action_schema |
| 约束求解 | planning.constraints |
| 影响分析 | planning.impact |
| 风险评分 | planning.risk |
| 计划排序 | planning.ranker |
| Patch emit | patch.emitter |
| reverse build | patch.reverse |

### 4.5 应用和验证

| 步骤 | 模块 |
|---|---|
| 写入 VFS | execution.vfs |
| 调度 op | execution.scheduler |
| 应用 patch | execution.applicator |
| 静态验证 | validation.static |
| 运行探针 | validation.runtime |
| 证据保存 | validation.runtime.evidence |
| 证书生成 | validation.certificate |

### 4.6 打包发布

| 步骤 | 模块 |
|---|---|
| 生成 manifest | mod.manifest |
| 构建包 | mod.package |
| 供应链检查 | supply.gates |
| 签名 | supply.signature |
| 发布 | ecosystem.listing |
| 审核 | ecosystem.moderation |

---

## 5. PR 颗粒度规则

每个 PR 应满足：

- 不超过 1 个功能域主改。
- 不超过 1 个跨域接口新增。
- 包含测试。
- 更新文档中的任务状态或映射。

不推荐的 PR：

- “重构 core 目录”一次性搬所有文件。
- 同时改数据模型、planner、executor、validator。
- 无测试的 schema 改动。
- 直接删除旧 import path。

推荐的 PR：

- “新增 SourceSpan 类型并在 ContentNode metadata 中兼容挂载”。
- “新增 IntentAST 和 compiler facade，旧 classifier 保持可用”。
- “ToolGateway 拦截一个现有 toolchain 调用”。

---

## 6. Facade 兼容策略

迁移期间保留：

```python
udify.models.content_graph
udify.models.cdl_patch
udify.core.cognition
udify.core.execution
udify.core.validation
```

这些旧路径只做 re-export 或薄包装，禁止继续堆新功能。

废弃标记：

| 阶段 | 行为 |
|---|---|
| T0 | 新旧并存 |
| T1 | 新代码只能 import 新路径 |
| T2 | 旧路径 warning |
| T3 | 删除旧路径 |

---

## 7. 文档和代码同步点

| 代码动作 | 必须更新 |
|---|---|
| 新增 domain | `SYSTEM-FUNCTIONAL-DESIGN-GUIDE-v1.md` |
| 新增目录 | 本文目标目录结构 |
| 新增跨模块接口 | `INTERFACE-CONTRACTS-AI-GAME-INDUSTRY-v1.md` |
| 新增端到端路径 | `EXECUTION-PATHS-AI-GAME-INDUSTRY-v1.md` |
| 新增底层 schema | `DEEP-TECHNICAL-MODULE-SPEC-AI-GAME-v1.md` |
| 新增 benchmark | `MODULE-ATTACK-MAP-v3.md` 和 UdifyBench 清单 |

---

## 8. 最小可执行切片

### Slice 1：Intent to VFS Diff

目标：

```text
game_root + intent -> VFS diff
```

必须包含：

- inventory。
- engine detection。
- semantic graph minimal。
- intent compiler。
- deterministic planner。
- patch emitter。
- VFS apply。

不包含：

- runtime probe。
- package。
- marketplace。

### Slice 2：VFS Diff to Validation Report

目标：

```text
VFS diff -> static validation report
```

必须包含：

- schema validation。
- reference validation。
- script safety。
- reparse。

### Slice 3：Validation Report to Draft ModPackage

目标：

```text
patch + reverse + validation -> draft package
```

必须包含：

- manifest。
- package layout。
- reverse。
- validation artifact。

### Slice 4：Draft ModPackage to Runtime Certificate

目标：

```text
draft package -> runtime validation certificate
```

必须包含：

- ProbeSpec。
- local Playwright runner。
- evidence bundle。
- certificate。

---

## 9. 工程看板建议

看板列：

1. Spec Ready。
2. Schema Ready。
3. Unit Implementing。
4. Contract Testing。
5. Integration Testing。
6. Golden Case。
7. Docs Updated。
8. Done。

每张卡必须有：

- Domain。
- Feature ID。
- Input/Output。
- Test。
- Failure mode。

---

## 10. 风险和规避

| 风险 | 规避 |
|---|---|
| 目录重构过大 | facade + wave 迁移 |
| schema 膨胀 | optional fields + version |
| planner 过早复杂 | deterministic first |
| cloud 过早引入 | local runner first |
| LLM 幻觉 | evidence-first + validation |
| 工具安全漏洞 | ToolGateway 强制 |
| 测试缺口 | Path A/B golden 先行 |
| 文档和代码漂移 | PR 模板强制更新文档 |

---

## 11. 第一阶段任务清单

最先开的 20 张卡：

1. `FOUND-TRACE-01`：TraceContext。
2. `FOUND-ERROR-01`：ErrorRecord。
3. `SEM-SOURCE-01`：SourceSpan。
4. `SEM-EVID-01`：EvidenceRef。
5. `SEM-CONF-01`：ConfidenceScore。
6. `CAP-PROFILE-01`：CapabilityProfile schema。
7. `CAP-WORKLOAD-01`：WorkloadDescriptor schema。
8. `SESSION-JOB-01`：ModJob state enum。
9. `PER-INV-01`：RawInventory schema。
10. `INT-AST-01`：IntentAST。
11. `INT-STRUCT-01`：StructuredIntent。
12. `PLAN-IMPACT-01`：ImpactReport。
13. `PLAN-RISK-01`：RiskScore。
14. `PATCH-OP-01`：PatchOperation v3。
15. `PATCH-REV-01`：ReverseOperation。
16. `VAL-PROBE-01`：ProbeSpec。
17. `VAL-REPORT-01`：ValidationReport。
18. `MOD-MANIFEST-01`：ModManifest。
19. `TOOL-MANIFEST-01`：ToolManifest。
20. `SUP-ARTIFACT-01`：ArtifactRef。

完成这 20 张卡后，后续工程就不会再悬空。
