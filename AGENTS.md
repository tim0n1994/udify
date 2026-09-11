# AGENTS.md — Udify

> 本文件为 AI 编码助手提供项目上下文。人类贡献者请优先阅读 README.md。

---

## 1. 项目概述

**Udify** 是一个意图驱动的自动化内容魔改（Intent-Driven Automated Content Transformation）平台。

核心使命：让非技术用户用自然语言描述愿望，系统自动分析原始内容、规划修改方案、执行修改、验证结果。

首攻方向：游戏 Mod 自动化（RPG Maker MV/Unity/Godot/Unreal）。

---

## 2. 门禁与契约（修改前必读）

### Python 门禁

```bash
ruff check udify/ tests/
bash scripts/typecheck.sh        # blocking mypy：15 文件 v3 子集（清单与 .github/workflows/ci.yml 一致）
python3 -m pytest tests/ -q
```

- `scripts/typecheck.sh` 是唯一 blocking 的 mypy 门禁，`--follow-imports=silent` 只查自包含 v3 模块；全包 `mypy udify/` 仍有历史类型债，仅作非阻塞报告，不得据此宣称 strict 通过。
- 文档中的测试数量仅为快照（2026-09-03 `.venv` 实跑 860 通过 / 2 跳过）；宣称“全绿”必须以当场实跑为准。注意：用 Homebrew `python3` 直跑时，Playwright 运行时探针 4 例因该解释器的浏览器环境超时失败，统一以 `.venv` 为准。

### Web 门禁

Web 门禁（install/audit/lint/typecheck/unit/build/E2E）、`sharp`/`postcss` 供应链 override 约束与 `NEXT_PUBLIC_*` 运行时配置契约，统一见 [web/AGENTS.md](web/AGENTS.md)。

### 编码规范

- **类型注解**: 所有函数必须有完整的 type hints（blocking 范围见 `scripts/typecheck.sh`；存量全包 strict 是历史债）
- **不可变性优先**: 使用 `frozen=True` dataclass 表示核心数据结构
- **纯函数优先**: 副作用显式标记，状态修改函数命名用动词（`apply_`, `update_`）
- **错误处理**: 明确异常路径，不使用裸 `except`
- **文档字符串**: 所有公共类/方法使用 Google-style docstring
- **TDD**: 新功能先写测试；fixture 共享测试数据；同场景用 `@pytest.mark.parametrize`
- **覆盖率**: 目标 80%+（CI 当前门槛 62%）

---

## 3. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.12+ | 核心后端 |
| 数据科学 | NumPy | 嵌入向量、数值计算 |
| 测试 | pytest, hypothesis | TDD，目标 80%+ 覆盖率 |
| 类型检查 | mypy | strict mode |
| 代码风格 | ruff | 替代 black + isort + flake8 |
| API / 本地持久化 | FastAPI + sqlite3 WAL | 单用户、127.0.0.1；Job 工件落盘 |
| 前端 | Next.js 15 + React 19 + TypeScript strict + Tailwind 4 | Zod runtime contract、TanStack Query、Radix primitives |
| Web 测试 | Vitest + Testing Library + MSW + Playwright | unit/component + mocked Chromium desktop/mobile |
| Web 供应链 | pnpm 10 + production audit | Node ≥20.9；high/critical 阻塞；Next 定向 sharp/postcss override |
| 图数据库 | Neo4j (预留) | ContentGraph 持久化 |
| 关系数据库 | PostgreSQL (预留) | 元数据、审计日志 |
| 向量数据库 | Pinecone (预留) | 语义搜索 |
| 容器 | Docker, gVisor (预留) | 沙箱执行 |
| DAG 编辑器 | ReactFlow (预留) | 当前工作台尚未引入 |
| 构建 | hatchling | pyproject.toml 标准 |

---

## 4. 目录结构（速览）

```
udify/
├── udify/models/        # ContentGraph / CDLPatch / v3 证据链（source.py）
├── udify/core/          # pipeline、perception/、planning/、tool_gateway/、validation/、
│                        #   orchestration/（mod_job / job_store / job_runner / gate_orchestrator / progress）、
│                        #   adapters/、evaluation/、execution/ 等核心引擎
├── udify/api/           # 薄 API（FastAPI app / schemas / job_events，`udify serve`）
├── web/                 # Next.js 15 审阅工作台（门禁见 web/AGENTS.md）
├── scripts/             # typecheck.sh（mypy 子集门禁）、check_reachability.py 等
├── tests/               # Python 测试
└── docs/                # 架构文档；活跃集见 docs/ITERATION-PLAN-2026-08.md
```

---

## 5. 当前状态快照

**截至 2026-09-03**（批次 0-5 完成；验收台账见 docs/ITERATION-PLAN-2026-08.md §11）：

| 模块 | 状态 | 测试 |
|------|------|------|
| 感知引擎 (Perception) | ✅ 完成 | 19/19 通过 |
| CDL Patch/Diff | ✅ 完成 | 32/32 通过 |
| 规划引擎 (Planning) | ✅ 完成 | 30/30 通过 |
| 基础设施 (Infrastructure) | ✅ 完成 | 40/40 通过 |
| 安全层 (Security) | ✅ 完成 | — |
| 会话管理 (Session) | ✅ 完成 | — |
| 知识图谱 (Knowledge) | ✅ 完成 | — |
| 虚拟文件系统 (VFS) | ✅ 完成 | — |
| 沙箱执行 (Sandbox) | ✅ 完成 | — |
| 反馈闭环 (Feedback) | ✅ 完成 | — |
| 多 Mod 管理 (ModManager) | ✅ 完成 | — |
| 增强验证 (Validation) | ✅ 完成 | — |
| 高级模块测试 | ✅ 完成 | 38/38 通过 |
| 解析器 (Parsers) | ✅ 完成 | 24/24 通过 |
| 端到端管道 (Pipeline) | ✅ 完成 | — |
| 持久化 (Persistence) | ✅ 完成 | — |
| 备份管理 (Backup) | ✅ 完成 | — |
| Mod 导出 (ModExporter) | ✅ 完成 | — |
| CLI | ✅ 完成 | — |
| 记忆系统 (Memory) | ✅ 完成 | — |
| LLM 客户端 (LLMClient) | ✅ 完成 | — |
| 执行调度器 (ExecutionScheduler) | ✅ 完成 | — |
| MCP 服务端 (MCPServer) | ✅ 基础版 | — |
| v3 证据链 (source.py) | ✅ 完成 | 批次 1 |
| 引擎适配器 (adapters/miu2d) | ✅ 完成 | 批次 1-2 |
| 安全工具网关 (tool_gateway) | ✅ 完成 | 批次 1 |
| 静态验证/运行时探针 v3 | ✅ 完成 | 批次 3 |
| UdifyBench (10 golden case) | ✅ 完成 | 批次 3 |
| ModJob 编排 (orchestration) | ✅ 完成 | 2026-08 批次 4A |
| 薄 API (udify/api + serve) | ✅ 完成 | 2026-08 批次 4B |
| 前端工作台 (web/, Next.js 15) | ✅ 可配置审阅切片 | 31 unit/component + 4 mocked E2E |
| JobStore 并发与关闭协议 | ✅ 完成 | API/编排 59；竞态循环 40/40 |

**当前门禁快照**: Python `.venv` 实跑 860 通过 / 2 跳过（2026-09-03 当场实跑；历史基线见 docs/ITERATION-PLAN-2026-08.md §11）；Web ESLint/tsc/Vitest/production build/Playwright desktop+mobile 全绿（同上基线）。全包 mypy 仍有历史债，只宣称迭代方案指定的 15 文件子集通过。

**产品入口**：`udify serve`（API，127.0.0.1:8765）+ `cd web && pnpm dev`（工作台，localhost:3000）。状态目录 `./.udify/`（jobs.db + 任务工件）。

**iter8 产品契约（2026-09-09）**：实际 API 仅支持 miu2d 静态 ModPackage；不运行或安装到原游戏。新增 `awaiting_clarification` 与 `POST /jobs/{id}/clarify`，目标候选和图版本持久化；SSE `event: job` 与轮询共用 `job_events.seq`，`JobStore.read_detail` 提供一致快照。批准绑定审阅及源文件摘要，下载校验包摘要；rollback 是可恢复的包撤销。状态数据库与工件目录必须位于游戏目录外。验收与仍未实现的能力见 `docs/ITERATION-PLAN-2026-08.md` §12。

---

## 6. 关键设计决策

### D1: CDL Patch 作为核心抽象

系统不直接生成修改后的文件，而是生成结构化的 `CDLPatch`。这带来了可验证性、可回滚性、可审计性和可合并性。

### D2: LLM 导演 + MCTS 制片人

规划不依赖纯 LLM 生成（不可靠、成本高），而是使用 MCTS 做系统性搜索，LLM 仅作为价值评估函数。当前默认使用启发式价值函数，LLM 为可插拔升级。

### D3: 研究先于实现

在写每一行代码前，先完成对应的架构文档。当前已有 25+ 份文档覆盖所有子系统。

---

## 7. 环境信息

- **操作系统**: macOS (darwin)
- **Python**: 3.14 系列（本机 `.venv` 为 3.14.6；mypy/pytest/ruff 以 `.venv` 为准）
- **工作目录**: `/Users/username/Proj/udify`
- **Git 仓库**: 是
- **虚拟环境**: `.venv`（`scripts/typecheck.sh` 优先使用 `.venv/bin/mypy`）

---

## 8. 联系与决策

- **项目所有者**: JC
- **核心需求来源**: `docs/VISION.md`, `docs/PLAN.md`, `docs/ARCHITECTURE-v2.md`
- **最新进展**: `docs/PROGRESS-SESSION-3.md`
- **市场验证**: `docs/COMMUNITY-RESEARCH.md`, `docs/RESEARCH-v3-GitHub-UGC-Agent.md`

---

## 9. JC 的协作风格偏好

JC 对架构和文档工作的核心诉求是：先理解项目初心，再从宏观愿景、产业格局、开源生态和底层技术栈一路下钻到可执行工程细节。偏好的输出不是轻量建议，而是厚重、系统、可落地的技术文档体系。

工作时应遵循：

- **初心优先**：所有架构判断都要回到 Udify 的根本使命——让非技术用户用自然语言表达愿望，系统自动理解内容、规划修改、执行、验证、反馈。
- **文档先行**：在大规模编码前，先形成面向工程师的技术调研、架构蓝图、功能设计、接口契约和实施地图。
- **宏观到微观**：先站在产业和系统层面思考，再逐层下沉到功能域、模块、数据结构、接口、失败模式、测试夹具和 PR 切分。
- **开源优先**：优先调研并整合成熟开源框架和社区工具，把自研重点放在语义提升、意图接地、语义 Patch、自动验证、兼容性和反馈演化等差异化能力。
- **颗粒度足够细**：最终产出必须能让工程师直接拆任务开工，包括目录映射、模块职责、输入输出、验收标准、迁移顺序和第一批任务卡。
- **宏大但落地**：允许从 AI 原生游戏工业、硬件/芯片、云基础设施、游戏引擎和生态平台的视角重塑方案，但必须回落到 Udify 当前可执行路径。

一句话：JC 需要的是从愿景到工业蓝图再到工程施工图的技术宪章，而不是泛泛的架构概念。

---

> **注意**: 如果修改了本文件中提到的任何模块结构、工具链配置或测试命令，请同步更新本文件。
