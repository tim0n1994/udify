# Udify iter4 PRD —— 产品级健壮性迭代

日期: 2026-08-06 | 基于: DEEP-RESEARCH-REPORT-iter4.md（5×Sol × 3 轮，~2.5M 字符研究）
基线: iter3（452 passed, 2 skipped）| 目标: iter4 把五条主线推进到可上线产品能力

## 0. 北极星与验收总纲

把 Udify 从「合成样例能跑」推进到「真实用户五分钟闭环 + 能力不退化」。五个模块（M1-M5）各自可独立验收，合起来构成产品闭环的健壮性补全。

**不可谈判验收项**：每个模块新增代码全部带测试与类型注解；无 key 全降级不触网；安全 fail-closed；不 commit/push/部署/迁移（未授权）；现有 452 测试不退化。

---

## M1 — 真实游戏目录 ingestion 与引擎自适应（基于 T1）

### 职责
给定一个真实解压后的游戏目录，安全地识别引擎、定位可改资源、生成 ContentGraph，并产出显式不完整性诊断。

### 接口契约（Python，基于 T1 交付）
- `udify/models/detection.py`（新）：
  - `EngineId(StrEnum)`: rpg_maker_mv / rpg_maker_mz / godot / unity / miu2d / unknown
  - `DetectionResult(frozen)`: engine_id, confidence, evidence: list[DetectionEvidence], diagnostics, budget_usage
  - `DetectionEvidence(frozen)`: kind, source_path, field, expected, actual, strength(EvidenceStrength)
  - `DetectionBudget(frozen)`: max_files, max_bytes —— 防 OOM
- `udify/core/ingestion/security.py`（新）：`IngestionGuard.validate(game_root) -> GuardReport`（路径穿越/symlink loop/超大文件/二进制检测）
- `udify/core/ingestion/root_discovery.py`（新）：`discover_project_root(path) -> CandidateRoot`（候选根发现，不靠单一文件）
- `udify/core/ingestion/fs_view.py`（新）：`SafeFsView` —— 受限文件系统视图
- `udify/core/perception/engine_detector.py`（改）：`detect(game_root, budget) -> DetectionResult`（字段级指纹，非单文件）

### 验收标准
1. 给定 RPG Maker MV 真实目录（package.json + www/data/*.json），detect 返回 engine_id=rpg_maker_mv，confidence>=0.9，evidence 非空。
2. IngestionGuard 拒绝路径穿越（../etc/passwd）、symlink loop、>10MB 单文件、二进制误解析——每个有测试。
3. ContentGraph 从真实目录物化，24 类失败模式至少 8 类有测试覆盖（带回退）。
4. 未知引擎目录返回 engine_id=unknown + diagnostics，不 crash 不臆测。
5. 全部 frozen dataclass + 完整 type hints。

### PR 切分
- PR1: models/detection.py + engine_detector.py 增强（纯接口 + 单引擎识别测试）
- PR2: ingestion/security.py + fs_view.py + root_discovery.py（安全层）
- PR3: graph_build.py 物化失败模式矩阵（含回退）

---

## M2 — LLM 意图路径成本护栏与可观测性（基于 T2）

### 职责
让 LLM 意图解析的每次调用可计量（token/成本/延迟）、降级可解释、预算可护栏，并与现有 audit chain 收敛。

### 接口契约（Python，基于 T2 交付）
- `udify/core/cognition/intent_trace.py`（新）：
  - `IntentDecisionTrace(frozen)`: decision_path(DecisionPath), confidence, degradation_reason(DegradationReasonCode), usage(TokenUsageTrace), cost(CostTrace), to_dict()
  - `DegradationReasonCode(StrEnum)`: NO_KEY / BUDGET_EXHAUSTED / TIMEOUT / VALIDATION_FAILED / MALFORMED_RESPONSE / NETWORK_ERROR / RATE_LIMIT
  - `ReasonDescriptor`: 每个 reason 的 retryable + suggested_action
- `udify/core/cognition/llm_pricing.py`（新）：`estimate_cost(usage, model) -> Decimal`（真实定价表，标注来源日期）
- `udify/core/cognition/llm_budget.py`（新）：`LLMBudgetPolicy(frozen)`, `reserve(req) -> ReservationResult`, `settle(result)` —— 三级预算（全局/日/job），sqlite 事务原子检查
- `udify/core/cognition/llm_intent.py`（改）：LLMIntentProposer 注入 trace 产出，JobLLMBudget 替换为 LLMBudgetPolicy
- `udify/core/tool_gateway/audit.py`（改）：LLM 调用审计字段映射，收敛为一套

### 验收标准
1. 无 ANTHROPIC_API_KEY 时，IntentDecisionTrace.decision_path=heuristic，reason=NO_KEY，不触网。
2. 有 key 时，trace 记录真实 token usage（input/output）+ 成本估算（非零）。
3. 预算耗尽时 reason=BUDGET_EXHAUSTED，硬停不再调用。
4. IntentDecisionTrace 可序列化进 sqlite job_events + audit chain（链式哈希不断）。
5. 三级预算并发安全（模拟多 job 同时 reserve，不超预算）。
6. 全部 frozen + 完整 type hints；现有 6 个 llm_intent 测试不退化。

### PR 切分
- PR1: intent_trace.py + llm_pricing.py（纯计量 + 成本）
- PR2: llm_budget.py + llm_intent.py 改造（预算护栏接入）
- PR3: audit.py 收敛 + job_events 序列化

---

## M3 — 多 Mod 叠加真实冲突解决（基于 T3）

### 职责
对叠加的多个 Mod 做三路合并（按格式分派），分类冲突（auto/manual/semantic），产出前端可渲染的 ConflictReport，支持 ModStack 中间层移除重算。

### 接口契约（Python，基于 T3 交付）
- `udify/core/mod_manager/real_merge/__init__.py`（新）：`merge(base, ours, theirs, fmt) -> MergeResult`
- `real_merge/text_merge.py`：ini 行级 diff3（difflib.SequenceMatcher）
- `real_merge/json_merge.py`：字段级递归 structured merge（保留键序/缩进）
- `real_merge/lua_merge.py`：受限 AST 合并
- `real_merge/semantic_merge.py`：数值语义规则集（白名单 auto / 黑名单 manual）
- `real_merge/conflict_report.py`（新）：`ConflictReport(frozen)`: files: list[FileConflict], state(ReportState), diagnostics
  - `FileConflict`: path, hunks: list[ThreeWayHunk], strategy(ResolutionStrategy), risk(ResolutionRisk)
  - `ThreeWayHunk`: base/ours/theirs: ConflictSide, semantic: SemanticContext
  - `ResolutionOption`: side, rationale, auto_resolvable: bool

### 验收标准
1. 两个 Mod 改同一 ini 不同字段 → auto merge 成功，无冲突。
2. 两个 Mod 改同一 ini 同一字段不同值 → ConflictReport 标 manual，含三路内容。
3. 两个 Mod 都把 Boss 血量 +50% → semantic merge 白名单自动合并（叠加 or 取大，按规则）。
4. 类型冲突（数值 vs 字符串）→ 黑名单，必须 manual。
5. ModStack [base,A,B,C] 移除 B → C 基于 A' 重算（suffix replay），有测试。
6. ConflictReport 可序列化为 JSON，前端 TS 类型一一对应。
7. 恶意 Mod（危险 patch）被检测拒绝。
8. 全部 frozen + 完整 type hints。

### PR 切分
- PR1: real_merge/__init__ + text_merge + json_merge（基础合并）
- PR2: lua_merge + semantic_merge（语义规则集）
- PR3: conflict_report.py + ModStack suffix replay 接入

---

## M4 — 流式任务进度与前端实时性（基于 T4）

### 职责
把 1s 轮询状态串升级为 per-stage 流式进度（SSE），支持取消（端到端状态机），前端实时渲染进度与阶段时间线。

### 接口契约（前后端，基于 T4 交付）
**后端 Python**：
- `udify/core/orchestration/progress.py`（新）：`ProgressEvent(frozen)`, `emit_progress(stage, detail, pct)`，从 JobRunner 步进产生
- `udify/core/orchestration/progress_store.py`（新）：SQLite 持久化进度账本（崩溃可恢复）
- `udify/core/orchestration/cancellation.py`（新）：`CancellationToken`（threading.Event），状态机迁移 + VFS 补偿
- `udify/api/job_events.py`（新）：`GET /api/v0/jobs/{id}/events` —— SSE（StreamingResponse + 心跳 + 断线检测）
- `udify/api/app.py`（改）：注册 SSE 路由，回退轮询

**前端 TypeScript**：
- `web/lib/api/job-progress.ts`（新）：ProgressEvent TS 类型（与 Python 一一对应）
- `web/hooks/use-job-progress.ts`（新）：`useJobProgress(jobId)` —— EventSource + TanStack Query 5，SSE 主/轮询兜底
- `web/components/jobs/job-progress-panel.tsx`（新）：阶段时间线 + 进度条 + ETA

### 验收标准
1. `GET /jobs/{id}/events` 返回 SSE 流，每秒心跳，阶段变更推 ProgressEvent。
2. ProgressEvent 含 stage（perceive/plan/validate）、detail、pct（0-100）。
3. 取消：POST 触发 CancellationToken，JobRunner 停在安全点，VFS 回滚，状态迁移到 cancelled。
4. SSE 断线 → 前端自动回退轮询，不丢状态。
5. progress_store 持久化，kill -9 后重启恢复进度。
6. 前端 job-progress-panel 渲染阶段时间线 + 进度条。
7. 现有 web 测试不退化；新增 SSE 端点测试。

### PR 切分
- PR1: orchestration/{progress,progress_store}.py + 测试
- PR2: cancellation.py + SSE 端点 job_events.py
- PR3: 前端 hooks + 组件 + 集成

---

## M5 — 评测驱动 CI 与回归闭环（基于 T5）

### 职责
把 30 case bench 进 CI 做 gating，固化确定性 mock LLM fixture，建立基线冻结 + 退化检测 + PRD 反馈闭环。

### 接口契约
- `tests/bench/conftest.py`（改/新）：确定性 mock LLM fixture（cassette replay 或手写），环境变量隔离在线/离线
- `tests/bench/baseline.json`（新，git-tracked）：基线快照（case_id/metric/value/timestamp/commit）
- `.github/workflows/ci.yml`（改）：bench job（marker 分层 default/bench-gate/bench-info），退化 block
- `tests/bench/report.py`（新/改）：JSON 报告 schema（case 级 + 聚合 + PRD 反馈映射）

### 验收标准
1. `pytest -m bench-gate` 在 CI 运行，target_precision 低于基线则 exit 非 0（block）。
2. `pytest -m bench-info` 运行但不 block（informational）。
3. mock LLM fixture 确定性（同一 case 连跑 3 次结果一致，无 flaky）。
4. 在线 LLM 评测与离线 mock 用 ANTHROPIC_API_KEY 环境变量隔离。
5. 退化报告含 case 级 delta + 阈值 + 是否 block。
6. 覆盖率门禁 70% 与 bench 门禁并存于同一 workflow。
7. 现有 30 case bench 不退化。

### PR 切分
- PR1: conftest 确定性 fixture + baseline.json 冻结
- PR2: ci.yml bench-gate job + 退化检测
- PR3: report.py PRD 反馈映射

---

## 落地顺序（依赖序）

1. **M5（评测 CI）先落**：建立回归门禁，保护后续模块不退化。
2. **M1（ingestion）**：真实目录入口，是产品闭环起点。
3. **M2（LLM 可观测）**：意图信任地基，独立可落。
4. **M3（多 Mod 合并）**：依赖 M1 的 ContentGraph，是产品护城河。
5. **M4（流式进度）**：前后端全栈，独立可落，最后接前端整合。

## 红线（继承）
- 不 commit/push/部署/迁移（未授权）。
- 无 key 全降级不触网。
- 安全 fail-closed（沙箱/ingestion/合并）。
- 不臆造未确认契约（引擎字段、合并语义）。
- 全部新增代码带测试 + 类型注解。
