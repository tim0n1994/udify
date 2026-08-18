# Udify iter6 PRD — 闸门编排 + 端到端验证 + 主路径接入

日期: 2026-08-06 | 基线: iter5（759 passed, 2 skipped）
研究依据: docs/research-2026-08-iter6/DEEP-RESEARCH-REPORT-iter6.md（6×Sol × 2 轮，413k 字符）
验收标准: 构建完整的可上线产品能力——五道闸门编排成 fail-closed 状态机、端到端 fixture 验证闭环、主路径全部接入

## 0. iter6 的产品目标

iter5 把五道信任闸门的数据结构与逻辑落地了，但它们各自独立、未接入主路径。iter6 的目标：
1. 把五道闸门编排成一个 fail-closed 状态机（V1 研究）。
2. 用真实 RPGMV fixture 端到端验证「接地→Patch→验证」闭环（V3 研究）。
3. 把 iter5 的五道闸门全部接入 JobRunner 主路径（wiring）。
4. 用真实 sandbox-exec 执行守住安全承诺（V6 研究）。

## 模块切分（6 模块，每模块 PR1 数据结构/逻辑 + PR2 接入）

---

## M1 — 闸门编排器 GateOrchestrator（ORCHESTRATION）

**缺口**：JobRunner 是线性 glue，五道闸门各自独立，没有统一降级策略。
**目标**：V1 研究的四道阻断闸门 + 一道横切控制闸门的状态机。

### M1 数据结构（udify/core/orchestration/gate_orchestrator.py，新增）
```python
class GateName(Enum):
    INTENT_GROUNDING = "intent_grounding"   # 阻断型
    DEPENDENCY = "dependency"               # 阻断型
    SANDBOX = "sandbox"                     # 阻断型
    RUNTIME_VALIDATION = "runtime_validation"  # 阻断型
    LATENCY = "latency"                     # 横切控制型

class GateLifecycle(Enum):
    PENDING = "pending"; RUNNING = "running"; DECIDED = "decided"

class GateVerdict(Enum):
    PASS = "pass"; FAIL = "fail"; NEEDS_CLARIFICATION = "needs_clarification"

class DeliveryTier(Enum):
    INSTALLED_VERIFIED = "installed_verified"  # 可安装可称已验证
    UNVERIFIED_ARTIFACT = "unverified_artifact"  # 构件可供检查，验证未通过
    STATIC_ONLY = "static_only"  # 只完成静态分析
    NONE = "none"  # Job 被阻断

@dataclass(frozen=True)
class GateResult:
    name: GateName
    lifecycle: GateLifecycle
    verdict: GateVerdict
    evidence: str              # 判定证据（接地结果/验证报告/沙箱状态）
    delivery_tier: DeliveryTier  # 此闸门裁决对应的产物等级
    clarification: ClarificationRequest | None = None  # NEEDS_CLARIFICATION 时填充

@dataclass(frozen=True)
class JobVerdict:
    job_id: str
    gates: tuple[GateResult, ...]
    final_tier: DeliveryTier      # 取所有阻断闸门中最低的 tier
    final_tier_reason: str        # 为什么是这个 tier
```

### M1 GateOrchestrator（udify/core/orchestration/gate_orchestrator.py，新增）
- `run_gates(graph, intent, patch, manifests) -> JobVerdict`：按依赖序运行五道闸门。
- 降级铁律：final_tier = min(所有阻断闸门的 delivery_tier)。LATENCY 闸门不阻断，只标注 degraded。
- 串行强依赖：INTENT_GROUNDING → SANDBOX → RUNTIME_VALIDATION → DEPENDENCY（安装前）。
- 每道闸门产 GateResult，NEEDS_CLARIFICATION 立即暂停 Job（不继续后续闸门）。

### M1 PR1：GateOrchestrator + 状态机 + 降级矩阵 + 测试
- 验收：五道闸门按序运行，final_tier 取最低。NEEDS_CLARIFICATION 暂停。降级铁律：沙箱失败不可降级到裸执行。
- owned: `udify/core/orchestration/gate_orchestrator.py`, `tests/core/orchestration/test_gate_orchestrator.py`

### M1 PR2：接入 JobRunner（改造，process_job 调用 run_gates）
- JobRunner.process_job 在规划后调用 GateOrchestrator.run_gates，根据 JobVerdict.final_tier 决定安装/标注/拒绝。
- owned: `udify/core/orchestration/job_runner.py`, `tests/core/orchestration/test_job_runner_gates.py`

---

## M2 — 主路径 wiring：接地+验证+计时+依赖接入（WIRING）

**缺口**：iter5 的五道闸门逻辑全部未接入主路径（resolve_targets_grounded/process_intent_timed/run_by_engine/graph_from_manifests 都是死代码）。
**目标**：把 iter5 的五道闸门逻辑全部接入 JobRunner/Pipeline/MultiModManager 主路径。

### M2 PR1：接地接入 pipeline（改造）
- UdifyPipeline.process_intent 第 4 步（ReferenceResolver）改为调用 resolve_targets_grounded。
- 向后兼容：无 ReferenceSpec 的旧 Intent 走原确定性路径。
- 验收：「让第一个 Boss 更难」正确选第一个 Boss（修复 iter4 改错 Hero 的根因）。+ 集成测试。
- owned: `udify/core/pipeline.py`, `tests/core/test_pipeline_grounding.py`

### M2 PR2：验证引擎分派接入 job_runner（改造）
- JobRunner 调用 HeadlessRuntimeProbe.run_by_engine(graph, engine_id) 而非 run(graph)。
- 诚实分级：Godot=NATIVE_HEADLESS，RPGMV=AUTOMATED_NON_HEADLESS，商业未植入=UNVERIFIABLE。
- 验收：job_runner 产出的 ValidationReport 带 engine_coverage 字段。+ 测试。
- owned: `udify/core/orchestration/job_runner.py`, `udify/core/validation/runtime_probe.py`

### M2 PR3：依赖检查接入 install（改造）
- MultiModManager.install 调用 graph_from_manifests + detect_conflicts。
- CYCLE/MISSING 冲突 → 拒绝安装并返回冲突报告；VERSION 冲突 → 返回冲突供用户决策。
- 验收：循环依赖 Mod 被拒绝安装。+ 测试。
- owned: `udify/core/mod_manager/mod_manager.py`, `tests/core/mod_manager/test_install_dependency_check.py`

---

## M3 — 端到端 fixture 与验证（E2E-CORRECTNESS）

**缺口**：UdifyBench 只测 Patch 合成，没测接地+验证闭环。
**目标**：V3 研究的真实 RPGMV fixture 跑通完整闭环。

### M3 fixture（tests/fixtures/rpgmv/minimal/，新增）
- 真实 RPGMV 1.6.2 最小项目：Actors.json（2 actor）、Enemies.json（3 enemy: Slime/BossA/BossC）、Troops.json（含 BossA 在 troops[0]）、System.json、Map001.json。
-Enemies 结构：Enemies.json[0]=Slime(params[2]=10), Enemies.json[1]=BossA(params[2]=50), Enemies.json[2]=BossC(params[2]=120)。

### M3 端到端断言（tests/e2e/test_e2e_grounding.py，新增）
- 接地断言：「让第一个 Boss 攻击力翻倍」→ resolve_targets_grounded 选 BossA（Enemies.json[1]，不是 Hero）。
- Patch 断言：CDLPatch 应用后 BossA.params[2] == 100（原 50 * 2）。
- 数据完整性断言：应用后 Enemies.json 仍是合法 JSON，结构未损坏。
- owned: `tests/fixtures/rpgmv/minimal/`, `tests/e2e/test_e2e_grounding.py`

### M3 PR1：fixture + 端到端断言链 + 测试
- 验收：「第一个 Boss 攻击力翻倍」完整闭环：接地正确(BossA) + Patch 合法 + 应用后数值正确 + JSON 完整。
- owned: `tests/fixtures/rpgmv/minimal/Enemies.json`, `tests/fixtures/rpgmv/minimal/Actors.json`, `tests/fixtures/rpgmv/minimal/Troops.json`, `tests/e2e/test_e2e_grounding.py`

---

## M4 — 真实沙箱执行（SANDBOX-EXECUTION-REAL）

**缺口**：SandboxExecutor.execute 不实际 sandbox-exec 包裹——沙箱是声明而非执行。
**目标**：V6 研究的真实 sandbox-exec 执行。

### M4 SandboxExecutor 改造（udify/core/execution/sandbox.py，改造）
- execute(cmd, workdir, game_dir) 改为：
  ```python
  def execute(self, cmd, *, workdir, game_dir, timeout_s=30):
      profile = build_seatbelt_profile(work_dir=workdir, game_dir=game_dir)
      if not shutil.which("sandbox-exec"):
          return ExecutionResult(status="unsandboxed", reason="sandbox-exec not found")
      with tempfile.NamedTemporaryFile("w", suffix=".sb", delete=False) as f:
          f.write(profile); profile_path = f.name
      try:
          proc = subprocess.run(
              ["sandbox-exec", "-f", profile_path, *cmd],
              cwd=workdir, capture_output=True, timeout=timeout_s,
              resource_limits={"cpu": timeout_s, "fsize": 100*1024*1024},
          )
          return ExecutionResult(status="sandboxed", exit_code=proc.returncode, ...)
      finally:
          os.unlink(profile_path)
  ```
- `-f` 接收文件路径（V6 纠正：`-p` 接收 profile 内容字符串，不是路径）。
- 无 sandbox-exec → status="unsandboxed"（诚实，不伪造 sandboxed）。

### M4 PR1：sandbox-exec 真实包裹 + 资源限制 + 诚实降级 + 测试
- 验收：有 sandbox-exec 时 status="sandboxed"；无时 status="unsandboxed"。危险脚本被 seatbelt 拒绝。
- owned: `udify/core/execution/sandbox.py`, `tests/core/execution/test_sandbox_execution.py`

---

## M5 — 语义提升能力矩阵（SEMANTIC-LIFT-LITE）

**缺口**：SemanticLifter 的 LLM 降级路径未真正测试，能力边界未声明。
**目标**：V4 研究的能力矩阵 + 降级诚实。

### M5 能力声明（udify/core/perception/semantic_lifter.py，改造）
- SemanticLifter.lift(node) 返回 LiftResult 增加 `source: LiftSource`（RULE | LLM | MISSING）。
- 纯规则层标签（npc/actor/item/weapon）source=RULE。
- 无 Key 时 LLM 标签 source=MISSING（不假装 source=LLM）。

### M5 PR1：能力矩阵 + 降级诚实 + 测试
- 验收：无 Key 时规则标签 source=RULE，语义标签 source=MISSING。有 Key 时语义标签 source=LLM。
- owned: `udify/core/perception/semantic_lifter.py`, `tests/perception/test_semantic_lifter_source.py`

---

## 模块验收矩阵

| 模块 | PR | 内容 | owned 文件 |
|------|-----|------|-----------|
| M1 | PR1 | GateOrchestrator 状态机 + 降级矩阵 | orchestration/gate_orchestrator.py |
| M1 | PR2 | JobRunner 接入 run_gates | orchestration/job_runner.py |
| M2 | PR1 | 接地接入 pipeline（修复改错 Hero） | core/pipeline.py |
| M2 | PR2 | 验证引擎分派接入 job_runner | orchestration/job_runner.py, validation/runtime_probe.py |
| M2 | PR3 | 依赖检查接入 install | mod_manager/mod_manager.py |
| M3 | PR1 | RPGMV fixture + 端到端断言链 | tests/fixtures/rpgmv/, tests/e2e/ |
| M4 | PR1 | sandbox-exec 真实包裹 + 资源限制 | execution/sandbox.py |
| M5 | PR1 | 语义提升能力矩阵 + 降级诚实 | perception/semantic_lifter.py |

## 整体验收标准（可上线产品能力）

1. **五道闸门编排**：「让第一个 Boss 攻击力翻倍」跑通完整 Job 闭环，五道闸门按序运行，final_tier=INSTALLED_VERIFIED。
2. **接地正确**：第一个 Boss 选 BossA（Enemies.json[1]），不碰 Hero（修复 iter4 致命 bug）。
3. **端到端 fixture**：真实 RPGMV fixture 跑通接地→Patch→数值验证→JSON 完整性。
4. **沙箱真实**：sandbox-exec 真实包裹；无 sandbox-exec 诚实 status="unsandboxed"。
5. **依赖检查**：循环依赖 Mod 被拒绝安装。
6. **诚实降级**：所有闸门失败时降级只降交付级别不降安全级别。
7. **测试全绿**：759 基线 + 新增测试，0 退化，ruff/mypy 过。
