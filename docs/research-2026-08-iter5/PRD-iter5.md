# Udify iter5 PRD — 信任链补齐

日期: 2026-08-06 | 基线: iter4（637 passed, 2 skipped）
依据: DEEP-RESEARCH-REPORT-iter5.md（5×Sol ×4轮循环研究，9h46m 深度）
目标: 补齐 iter4 留下的三道信任闸门 + 安全/多 Mod 产品边界，全部可独立验收。

## 0. 设计原则（继承 iter2-4，强化）

- **诚实优先**：不臆造引擎契约/延迟数值/沙箱强度。U4 用 version 1 真实模板（不声称 version 3）；U3 不填入未测量的 LLM 延迟。
- **fail-closed**：安全（U4）、验证（U2）、预算（U3）宁可拒绝也不静默降级。
- **frozen dataclass + mypy strict + Google docstring + ruff SIM**。
- **无 key 全降级不触网**；CI 无 key 必须全绿。
- **接口不变**：新增消解层不破坏 resolve_targets 签名；新沙箱层不破坏 ToolGateway 协议。

## 五个模块（M1-M5），每个 2-3 个 PR

---

## M1 — 意图接地：ReferenceSpec 消解层 + ClarificationRequest（INTENT-GROUNDING）

**缺口**：iter4 的"第一个 Boss 改错 Hero"——缺少顺序域（order domain）。
**目标**：target_resolver 能正确消解序数/形容词/空间指代，消歧失败产 ClarificationRequest 而非静默猜错。

### M1 数据结构（udify/core/cognition/reference_spec.py，新增）
```python
@dataclass(frozen=True)
class ReferenceSpec:
    entity_type: str              # "boss" | "enemy" | "actor" | "item"
    operator: ReferenceOperator   # ORDINAL | SUPERLATIVE | SPATIAL | ID
    ordinal: int | None           # operator=ORDINAL 时：1=第一个
    superlative_field: str | None # operator=SUPERLATIVE 时："attack"|"hp"|"defense"
    superlative_direction: str | None  # "max" | "min"
    order_domain: OrderDomain     # DB_INDEX | TROOP_MEMBER | FIRST_ENCOUNTER | SPATIAL
    constraint_fields: dict[str, object]  # 额外硬约束

@dataclass(frozen=True)
class ClarificationRequest:
    spec: ReferenceSpec
    candidates: list[str]         # 候选节点 ID + 语义摘要
    reason: ClarificationReason   # AMBIGUOUS_ORDINAL | MISSING_ORDER_DOMAIN | MULTI_SUPERLATIVE_TIE
    suggested_clarifications: list[str]  # 建议用户回答的选项

class ReferenceOperator(Enum): ORDINAL; SUPERLATIVE; SPATIAL; ID
class OrderDomain(Enum): DB_INDEX; TROOP_MEMBER; FIRST_ENCOUNTER; SPATIAL
class ClarificationReason(Enum): AMBIGUOUS_ORDINAL; MISSING_ORDER_DOMAIN; MULTI_SUPERLATIVE_TIE; NO_CANDIDATES
```

### M1 消解器（udify/core/cognition/reference_resolver.py，新增）
- `resolve_reference(graph, spec) -> ResolveResult`：ResolveResult = Success(reference) | NeedsClarification(ClarificationRequest) | Failed(reason)。
- 三层：候选过滤（SemanticView 硬过滤）→ 排序（按 order_domain）→ 唯一性检查（CSP）。
- 无 LLM 依赖（纯确定性，A+C 路径）。B 路径（LLM）留接口但默认不启用。

### M1 PR1：数据结构 + 消解器 + 测试
- 验收：`resolve_reference(graph, ReferenceSpec(boss, ORDINAL, 1, DB_INDEX))` 返回唯一第一个 Boss。
- 消歧失败产 ClarificationRequest（不静默猜）。20+ 测试（序数/形容词/tie/no_candidates）。
- owned: `udify/core/cognition/reference_spec.py`, `udify/core/cognition/reference_resolver.py`, `tests/cognition/test_reference_resolver.py`

### M1 PR2：接入 target_resolver（改造，接口不变）
- resolve_targets 内部：StructuredIntent → 提取 ReferenceSpec → resolve_reference → 候选。
- 向后兼容：无 ReferenceSpec 的旧 Intent 走原确定性路径。
- 验收：「让第一个 Boss 更难」正确选第一个 Boss（DB_INDEX）；「最强的 Boss」max(attack) 且 tie 时产 ClarificationRequest。
- owned: `udify/core/cognition/target_resolver.py`, `tests/cognition/test_target_resolver_grounding.py`

---

## M2 — 可验证执行：ValidationReport + Godot headless 适配器（VERIFIED-EXECUTION）

**缺口**：HeadlessRuntimeProbe 骨架从未跑通真实闭环。
**目标**：Godot native headless 完整闭环（应用 patch → 启动 → 读状态 → 捕获报错 → 报告），诚实分级其他引擎。

### M2 数据结构（udify/core/validation/validation_report.py，新增）
```python
@dataclass(frozen=True)
class ValidationReport:
    job_id: str
    status: ValidationStatus       # PASSED | FAILED_RUNTIME | FAILED_ASSERTION | FAILED_CRASH | SKIPPED
    engine_coverage: EngineCoverage # NATIVE_HEADLESS | AUTOMATED_NON_HEADLESS | INSTRUMENTED_ONLY | UNVERIFIABLE
    assertions: list[AssertionResult]  # 每个语义断言的可信观测值
    errors: list[ValidationError]  # crash/runtime/silent 分类
    duration_ms: int

@dataclass(frozen=True)
class AssertionResult:
    name: str; expected: str; observed: str | None; passed: bool; evidence: str

class ValidationStatus(Enum): PASSED; FAILED_RUNTIME; FAILED_ASSERTION; FAILED_CRASH; SKIPPED
class EngineCoverage(Enum): NATIVE_HEADLESS; AUTOMATED_NON_HEADLESS; INSTRUMENTED_ONLY; UNVERIFIABLE
```

### M2 Godot 适配器（udify/core/validation/godot_probe.py，新增）
- `run_godot_headless(staging_dir, probe_script) -> ValidationReport`。
- 真实 CLI：`godot --headless --path /staging --script probe.gd --quit-after N --log-file out.log`。
- GDScript 探针读节点/资源，输出 JSON。三层判定：exit code（crash）/ stderr（runtime）/ 断言（silent）。

### M2 PR1：ValidationReport + Godot 适配器骨架 + 测试
- 验收：PASSED 需进程正常+无异常+所有断言通过。"成功启动"≠"已验证"。15+ 测试。
- owned: `udify/core/validation/validation_report.py`, `udify/core/validation/godot_probe.py`, `tests/core/validation/test_godot_probe.py`

### M2 PR2：接入 HeadlessRuntimeProbe（改造，引擎分派）
- HeadlessRuntimeProbe 按 EngineId 分派到 Godot/RPGMV/Unity/SKIP。
- 诚实声明 EngineCoverage：Godot=NATIVE_HEADLESS，RPGMV=AUTOMATED_NON_HEADLESS，商业未植入=UNVERIFIABLE。
- owned: `udify/core/validation/runtime_probe.py`, `tests/core/validation/test_runtime_probe_dispatch.py`

---

## M3 — 延迟可观测：Instrumentation 统一计时层（LATENCY-PROFILE）

**缺口**：从未测量端到端延迟分布，无法承诺"五分钟闭环"。
**目标**：统一计时 + 分阶段记录，让延迟可测量、可分解、可承诺。

### M3 数据结构（udify/core/infrastructure/timing.py，新增）
```python
@dataclass(frozen=True)
class PhaseTiming:
    phase: str            # "perception" | "planning" | "llm" | "validation" | "apply"
    category: PhaseCategory  # MANDATORY | OPTIONAL
    duration_ms: int
    detail: dict[str, object]  # 文件数/rollout数/token数等

@dataclass(frozen=True)
class JobTimingReport:
    job_id: str
    total_ms: int
    mandatory_ms: int
    optional_ms: int
    phases: list[PhaseTiming]
    degraded: bool        # 是否因预算降级

class PhaseCategory(Enum): MANDATORY; OPTIONAL
```

### M3 计时器（udify/core/infrastructure/timer.py，新增）
- `PhaseTimer`：context manager，`with timer.phase("perception", MANDATORY, {files: N}):`。
- `TimingCollector`：累积 PhaseTiming，产 JobTimingReport。与 IntentDecisionTrace 协同（trace 记决策，timing 记耗时）。
- 预算护栏：optional 阶段超 time_budget 时标记 degraded（不静默继续）。

### M3 PR1：数据结构 + PhaseTimer + 测试
- 验收：PhaseTimer 正确记录各阶段耗时；mandatory/optional 分类正确；degraded 标记准确。15+ 测试。
- owned: `udify/core/infrastructure/timing.py`, `udify/core/infrastructure/timer.py`, `tests/infrastructure/test_timer.py`

### M3 PR2：接入 UdifyPipeline（改造，各阶段插计时）
- pipeline 各阶段用 PhaseTimer 包裹；产 JobTimingReport 入 JobStore 事件流。
- 验收：跑一次 job 能产完整 JobTimingReport（各阶段耗时 > 0，total = Σ）。前端可读（已有 SSE）。
- owned: `udify/core/pipeline.py`, `tests/core/test_pipeline_timing.py`

---

## M4 — 安全沙箱：version 1 seatbelt + AST 静态分析（SANDBOX-REAL）

**缺口**：SandboxExecutor 的 seatbelt 是预留，从未验证真实隔离强度。
**目标**：两层防御——AST 静态拒绝已知危险 API + version 1 真实 seatbelt profile 兜底。

### M4 静态分析增强（udify/core/security/script_analyzer.py，新增）
- `analyze_script(language, code) -> ScriptAnalysis`：AST 解析 Lua/JS，检测危险 API 调用。
- 危险清单（真实）：Lua {os.execute, os.exit, os.getenv, io.popen, io.open, loadstring, load, require, ffi.C, debug.*}；
  JS {require('child_process'), require('fs'), eval, Function, child_process.*, fs.*}。
- `ScriptAnalysis`：blocked_apis list + severity + 建议改写。

### M4 seatbelt profile（udify/core/execution/seatbelt_profile.py，新增）
- `build_seatbelt_profile(writable_dirs: list[Path]) -> str`：生成 version 1 (deny default) profile。
- 仅允许临时目录可写 + 进程执行受限 + 网络 deny。close_fds=True 执行。
- **诚实**：version 1（不声称 version 3），声明 sandbox-exec 已弃用但仍可用。

### M4 PR1：ScriptAnalyzer + seatbelt profile + 测试
- 验收：危险 API 全检测（Lua+JS 各 10+ case）；profile 生成正确语法（version 1 deny default）。20+ 测试。
- owned: `udify/core/security/script_analyzer.py`, `udify/core/execution/seatbelt_profile.py`, `tests/security/test_script_analyzer.py`, `tests/core/execution/test_seatbelt_profile.py`

### M4 PR2：接入 validate_script_safety / ToolGateway（改造，两层防御）
- validate_script_safety 调 ScriptAnalyzer（静态层）；ToolGateway 在执行前要求 seatbelt/gVisor（运行时层）。
- 任一层失败 → 拒绝执行（fail-closed）。
- owned: `udify/core/execution/sandbox.py`, `tests/core/execution/test_sandbox_two_layer.py`

---

## M5 — 依赖图：DependencyGraph + DecisionRecord（MODSTACK-DEPENDENCY）

**缺口**：ModStack 无依赖建模，冲突解决无前端可视化数据契约。
**目标**：DependencyGraph（DAG）管合法共存 + 安装/卸载序；DecisionRecord 持久化用户决策。

### M5 数据结构（udify/core/mod_manager/dependency_graph.py，新增）
```python
@dataclass(frozen=True)
class DependencyEdge:
    mod_id: str; depends_on: str; version_constraint: str  # ">=1.0"

@dataclass(frozen=True)
class DependencyGraph:
    edges: list[DependencyEdge]
    def install_order(active: set[str]) -> list[str]  # 拓扑序
    def detect_conflicts(active: set[str]) -> list[DependencyConflict]  # 环/缺失/版本

@dataclass(frozen=True)
class DecisionRecord:
    conflict_fingerprint: str  # 精确 hash，复用必须完全一致
    decision: str; decided_at: str; mod_ids: list[str]
```

### M5 PR1：DependencyGraph + 冲突检测 + 测试
- 验收：拓扑序正确；循环依赖检测；缺失依赖检测；版本冲突检测。20+ 测试。
- owned: `udify/core/mod_manager/dependency_graph.py`, `tests/core/mod_manager/test_dependency_graph.py`

### M5 PR2：接入 ModManifest + DecisionRecord 持久化
- ModManifest 加 `depends_on: list[DependencyEdge]`（默认空，向后兼容）。
- DecisionRecord 精确指纹复用（不做模糊匹配）。
- owned: `udify/core/mod_manager/mod_exporter.py`, `udify/core/mod_manager/mod_manager.py`, `tests/core/mod_manager/test_decision_record.py`

---

## 全局验收标准

1. **Python**: 637 → ~720+ passed, 0 退化。ruff 全过。新模块 mypy strict。
2. **Web**: 现有门禁不退化。
3. **诚实约束**:
   - U1: 「第一个 Boss」正确消解（不静默猜错）；ClarificationRequest 产出口径清晰。
   - U2: Godot NATIVE_HEADLESS 闭环；RPGMV 诚实标 AUTOMATED_NON_HEADLESS；商业未植入 UNVERIFIABLE。
   - U3: JobTimingReport 各阶段耗时可测；不填入未测量的 LLM 数值。
   - U4: version 1 seatbelt（不声称 version 3）；危险 API 全检测；fail-closed。
   - U5: 依赖环检测；DecisionRecord 精确指纹复用。
4. **无 key 全降级不触网**（U1 纯确定性、U3 计时本地、U2 无网络、U4 本地沙箱、U5 本地图）。
5. **未授权**: 不 commit/push/部署/迁移。

## PR 切分总览

| 模块 | PR | 内容 | owned 目录 |
|------|----|------|-----------|
| M1 | PR1 | ReferenceSpec + resolver | cognition/{reference_spec,reference_resolver}.py |
| M1 | PR2 | 接入 target_resolver | cognition/target_resolver.py |
| M2 | PR1 | ValidationReport + Godot 适配器 | validation/{validation_report,godot_probe}.py |
| M2 | PR2 | 接入 runtime_probe 引擎分派 | validation/runtime_probe.py |
| M3 | PR1 | PhaseTiming + PhaseTimer | infrastructure/{timing,timer}.py |
| M3 | PR2 | 接入 pipeline 计时 | core/pipeline.py |
| M4 | PR1 | ScriptAnalyzer + seatbelt profile | security/script_analyzer.py, execution/seatbelt_profile.py |
| M4 | PR2 | 接入 sandbox 两层防御 | execution/sandbox.py |
| M5 | PR1 | DependencyGraph + 冲突检测 | mod_manager/dependency_graph.py |
| M5 | PR2 | 接入 ModManifest + DecisionRecord | mod_manager/{mod_exporter,mod_manager}.py |
