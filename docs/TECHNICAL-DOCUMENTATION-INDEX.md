# Udify 技术文档索引

> 面向工程团队的阅读入口。
>
> **文档纪律（沿袭 ITERATION-PLAN-2026-07.md §9.3）**：文档只减不增，活跃集恒 ≤4 份；其余文档标注 `frozen` / `aspirational`，不再扩写。
>
> **2026-07 北极星已达成**（2026-07-27 批次 0-3 落库推送，337 测试全绿）。欠条台账见 MODULE-ATTACK-MAP-v3 §21。当前迭代：**产品化**（ITERATION-PLAN-2026-08.md）。

---

## 1. 唯一活跃文档集（≤4）

这四份是当前唯一允许编辑、作为工程依据的文档：

| # | 文档 | 角色 |
|---|---|---|
| 1 | `ITERATION-PLAN-2026-08.md` | **本轮北极星与成功判据**——产品闭环（ModJob/薄API/前端切片/LLM 可选增强）、批次划分、红线 15 条 |
| 2 | `MODULE-ATTACK-MAP-v3.md` | **任务台账**——按任务 ID 拆 PR、验收标准、代码位置建议、§21 产品化扩展 |
| 3 | `ARCHITECTURE-OSS-OPTIMIZED-v3.md` | **架构边界**——v3 原语定义、模块边界、ADR-v3-001..010 |
| 4 | `TECHNICAL-DOCUMENTATION-INDEX.md` | **本文档**——索引与冻结状态 |

> 规则：代码为准，文档滞后必须补，但**不允许再用新文档扩张未验证的架构承诺**。

---

## 2. 冻结 / 愿景文档（只读，不再扩写）

下列文档保留作为历史背景与初心参考，但**不再主动维护**，标注状态：

### 2.1 `aspirational`（愿景/未验证蓝图，0 行代码支撑）

| 文档 | 说明 |
|---|---|
| `BLUEPRINT-AI-NATIVE-GAME-INDUSTRY-v1.md` | AI 原生游戏工业端边云蓝图——**aspirational** |
| `RESEARCH-AI-NATIVE-GAME-INDUSTRY-STACK-2026.md` | 芯片/硬件/云栈调研——**aspirational** |
| `MODULE-ATTACK-MAP-AI-GAME-INDUSTRY.md` | 蓝图模块拆解——**aspirational** |
| `DEEP-TECHNICAL-MODULE-SPEC-AI-GAME-v1.md` | 模块规格——**aspirational** |
| `INTERFACE-CONTRACTS-AI-GAME-INDUSTRY-v1.md` | 接口契约——**aspirational** |
| `EXECUTION-PATHS-AI-GAME-INDUSTRY-v1.md` | 执行路径——**aspirational** |
| `SYSTEM-FUNCTIONAL-DESIGN-GUIDE-v1.md` | 功能设计指南——**aspirational** |
| `PROJECT-RESTRUCTURING-IMPLEMENTATION-MAP-v1.md` | 重拆迁移地图——**aspirational**（facade+wave 策略仍被引用） |

### 2.2 `frozen`（v2/v1 架构分册，被 v3 取代但保留为历史）

| 文档 | 说明 |
|---|---|
| `ARCHITECTURE-v2.md` | v2 通用核心架构——**frozen**（被 v3 取代） |
| `ARCHITECTURE-v2.1-Community.md` | v2.1 社区版——**frozen** |
| `ARCHITECTURE.md` | 最早架构——**frozen** |
| `ARCHITECTURE-GAME-MOD-v1.md` | 游戏魔改特化 v1——**frozen** |
| `ARCHITECTURE-GAME-MOD-v1.1-REVIEW.md` | v1.1 盲点审查——**frozen** |
| `ARCHITECTURE-DATA.md` / `SECURITY.md` / `DEVOPS.md` / `EVENT-DRIVEN.md` / `API.md` / `PERFORMANCE.md` / `OBSERVABILITY.md` / `TESTING.md` / `FRONTEND.md` / `MCP-ECOSYSTEM.md` | v2 分册（各 1,400–1,900 行）——**frozen** |
| `VISION.md` | 项目初心——**frozen**（仍作为价值观参考） |
| `PLAN.md` | 四阶段路线图——**frozen**（被 ITERATION-PLAN 取代） |
| `RESEARCH.md` / `RESEARCH-v3-GitHub-UGC-Agent.md` | 早期调研——**frozen** |
| `RESEARCH-OSS-INTEGRATION-2026.md` | OSS 集成调研——**frozen**（结论已并入 v3） |
| `COMMUNITY_RESEARCH.md` / `COMMUNITY-RESEARCH-v2.md` | 社区调研——**frozen** |
| `TECHNICAL_COMPETITIVE_ANALYSIS.md` | 竞品分析——**frozen** |
| `PROGRESS-SESSION-{2,3,4}.md` | 历史进展报告——**frozen** |
| `ITERATION-PLAN-2026-07.md` | 2026-07 迭代方案（北极星已达成）——**frozen**（被 2026-08 取代） |

---

## 3. v3 的核心变更（对照）

| 领域 | v2/v1.1 | v3 |
|---|---|---|
| 架构定位 | Diff-first, Tool-centric, Human-in-the-loop | 开源工具编排之上的语义 Patch 编译器 |
| 工具策略 | MCP + Tool Registry | Secure Tool Gateway + Policy + Sandbox + Audit |
| 工作流 | Prefect 倾向 | Temporal 管副作用，LangGraph 管 Agent 推理（**P2，本轮不上**） |
| 图谱 | ContentGraph 基础结构 | ContentGraph v3 增加 evidence、confidence、provenance |
| Patch | 图级操作为主 | file_patch、runtime_hook、package_overlay 都是一等执行形态 |
| 验证 | 静态验证为主 | 静态验证 + runtime probe + intent eval + UdifyBench |

---

## 4. 后续维护规则

1. **活跃集只改 4 份**：新增内容只能进 `ITERATION-PLAN-2026-07.md` / `MODULE-ATTACK-MAP-v3.md` / `ARCHITECTURE-OSS-OPTIMIZED-v3.md` / 本索引。
2. 修改实际代码模块结构时，同步更新 `MODULE-ATTACK-MAP-v3.md` 的"代码位置建议"。
3. 改变架构边界或 ADR 时，同步更新 `ARCHITECTURE-OSS-OPTIMIZED-v3.md`。
4. 新增 benchmark case 时，同步更新 `MODULE-ATTACK-MAP-v3.md` 的 UdifyBench 清单。
5. 如果文档和代码冲突，短期以代码为准，中期必须补文档，长期应通过测试和 ADR 消除冲突。
6. **冻结文档如确需解冻，必须先在 ITERATION-PLAN 中说明理由并获得明确同意。**

---

## 5. 下一批工程切入

参考 `ITERATION-PLAN-2026-08.md` §6 的批次划分。历史进度（2026-07，全部 ✅ 并已落库推送）：

- **批次 0（止血）**：CI 骨架、Session 4 测试债清偿、双 pipeline 合并、文档冻结
- **批次 1（数据地基）**：`DATA-CG-01..05` + `DATA-PATCH-01..06` + `ADAPT-ENGINE-01..04` + `TOOL-GW-01..06`
- **批次 2（miu2d 闭环）**：`ADAPT-MIU2D-01..09` + `PER-LIFT-01..04` + `PLAN-ACTION-01..04` + `PATCH-SYN-01..06`
- **批次 3（验证与基准）**：`VAL-STATIC-01..05` + `VAL-RUNTIME-01..05` + `EVAL-INTENT-01..04` + `BENCH-01..03` = **7 月北极星达成**

当前迭代（2026-08 产品化）：

- **批次 4A（Job 基座）**：`ORCH-JOB-01..05` + `OBS-01..02` ⬜
- **批次 4B（薄 API）**：`API-01..05` + `API-07/08` + `SRV-01` + `MOD-STACK-01..03` ⬜
- **批次 5（前端切片）**：`UI-00` + `UI-01..04` + `UI-07` ⬜
- **批次 6（意图真化与欠条）**：`COG-LLM-01..03` + `REAL-GAME-01..02` + `VAL-RUNTIME-06` + 覆盖率 62→70 ⬜
