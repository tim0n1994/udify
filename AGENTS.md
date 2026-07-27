# AGENTS.md — Udify

> 本文件为 AI 编码助手提供项目上下文。人类贡献者请优先阅读 README.md。

---

## 1. 项目概述

**Udify** 是一个意图驱动的自动化内容魔改（Intent-Driven Automated Content Transformation）平台。

核心使命：让非技术用户用自然语言描述愿望，系统自动分析原始内容、规划修改方案、执行修改、验证结果。

首攻方向：游戏 Mod 自动化（RPG Maker MV/Unity/Godot/Unreal）。

---

## 2. 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 语言 | Python 3.12+ | 核心后端 |
| 数据科学 | NumPy | 嵌入向量、数值计算 |
| 测试 | pytest, hypothesis | TDD，目标 80%+ 覆盖率 |
| 类型检查 | mypy | strict mode |
| 代码风格 | ruff | 替代 black + isort + flake8 |
| 图数据库 | Neo4j (预留) | ContentGraph 持久化 |
| 关系数据库 | PostgreSQL (预留) | 元数据、审计日志 |
| 向量数据库 | Pinecone (预留) | 语义搜索 |
| 容器 | Docker, gVisor (预留) | 沙箱执行 |
| 前端 | React + ReactFlow (预留) | DAG 可视化编辑器 |
| 构建 | hatchling | pyproject.toml 标准 |

---

## 3. 目录结构

```
udify/
├── pyproject.toml              # 项目配置
├── docs/                       # 架构文档（30+ 份）
│   ├── VISION.md               # 项目愿景（多学科根基）
│   ├── PLAN.md                 # 四阶段路线图
│   ├── ARCHITECTURE-v2.md      # v2.0 核心架构
│   ├── ARCHITECTURE-GAME-MOD-v1.md      # 游戏魔改特化架构
│   ├── ARCHITECTURE-GAME-MOD-v1.1-REVIEW.md  # 架构审查报告（47盲点+12模块）
│   ├── PROGRESS-SESSION-2.md   # 最新进展报告
│   └── ...
├── udify/                      # 主包
│   ├── __init__.py
│   ├── cli.py                  # 命令行入口
│   ├── models/                 # 数据模型
│   │   ├── content_graph.py    # ContentGraph / ContentNode / ContentEdge / ContentAsset（+v3 证据链字段、checksum）
│   │   ├── cdl_patch.py        # CDLPatch / PatchOperation(+ExecutionMode) / PatchValidator / PatchApplicator / GraphDiffer
│   │   └── source.py           # v3 证据链原语：SourceSpan / Provenance / Confidence / Evidence / ToolRunRef
│   └── core/                   # 核心引擎
│       ├── pipeline.py         # 统一端到端管道 UdifyPipeline（旧 pipeline_v2.AutomatedModPipeline 已合并，保留为别名）
│       ├── miu2d_pipeline.py   # miu2d 闭环编排器（NL→语义图→file_patch→VFS 预览，批次 2）
│       ├── adapters/           # v3 引擎适配器层（EngineAdapter 协议 + miu2d 实现）
│       │   ├── base.py         # EngineAdapter Protocol / DetectionResult
│       │   ├── miu2d.py        # Miu2dAdapter（复用现有 parser，输出带 SourceSpan）
│       │   ├── miu2d_dsl.py    # DslCommandRegistry（miu2d DSL 命令表，ADAPT-MIU2D-05）
│       │   └── miu2d_world.py  # GameWorldGraphBuilder（感知+提升+关系推断，ADAPT-MIU2D-06）
│       ├── tool_gateway/       # v3 Secure Tool Gateway（所有外部工具调用唯一入口）
│       │   ├── gateway.py      # ToolGateway（策略→沙箱→执行→消毒→审计）
│       │   ├── policy.py       # ToolPolicy / RiskLevel(R0-R4) / 路径 allowlist
│       │   ├── audit.py        # ToolAuditChain（链式哈希审计）
│       │   └── lockfile.py     # ToolLockfile / ToolPin（version+sha256 pin）
│       ├── llm_client.py       # LLMClient（OpenAI/Anthropic 统一接口）
│       ├── perception/         # 感知引擎
│       │   ├── engine_detector.py
│       │   ├── resource_extractor.py
│       │   ├── mechanism_analyzer.py
│       │   ├── incremental_perception.py   # 增量感知（P0）
│       │   ├── semantic_lifter.py          # 语义提升器（PER-LIFT-01..04：标签+证据+置信度）
│       │   └── parsers/        # miu2d 特化解析器
│       │       ├── ini_parser.py
│       │       ├── obj_parser.py
│       │       ├── npc_parser.py
│       │       ├── lua_parser.py
│       │       └── lua_ts_parser.py        # Tree-sitter Lua（ADAPT-MIU2D-04：函数/调用/危险 API）
│       ├── planning/           # 规划引擎
│       │   ├── state.py        # PlanState / Intent / PlanContext
│       │   ├── action_space.py # ActionSpace
│       │   ├── action_schemas.py # 动作 Schema（PLAN-ACTION-01..04：numeric/script/reward）
│       │   ├── patch_synthesizer.py # Patch 合成器（PATCH-SYN-01..06：SourceSpan+INI/Lua/DSL+reverse）
│       │   ├── value_function.py # ValueFunction / HeuristicValueFunction
│       │   ├── mcts.py         # MCTSNode / MCTSTree
│       │   ├── planner.py      # Planner / PlanResult
│       │   └── cost_controller.py # 成本控制器（P0）
│       ├── infrastructure/     # 基础设施层
│       │   ├── event_bus.py    # EventBus / EventType
│       │   ├── config_center.py # ConfigCenter
│       │   ├── config_loader.py # YAML/JSON 配置加载
│       │   ├── audit_log.py    # AuditLog（链式哈希）
│       │   ├── cache_manager.py # CacheManager（L1/L2/L3）
│       │   ├── state_persistence.py # 会话/图谱持久化
│       │   ├── backup_manager.py # 自动备份管理
│       │   └── preview_formatter.py # 预览格式化
│       ├── security/           # 安全层
│       │   └── sanitizer.py    # InputSanitizer / OutputValidator
│       ├── session/            # 会话管理
│       │   └── session_manager.py # ModSession / SessionManager
│       ├── knowledge/          # 知识图谱
│       │   └── knowledge_graph.py # GameKnowledgeGraph
│       ├── execution/          # 执行引擎
│       │   ├── vfs.py          # VirtualFileSystem（预览模式）
│       │   ├── sandbox.py      # SandboxExecutor
│       │   ├── patch_executor.py # PatchExecutor（Patch→VFS）
│       │   ├── scheduler.py    # ExecutionScheduler（依赖图/并行执行/回滚）
│       │   ├── tool_registry.py # ToolRegistry
│       │   ├── builtin_tools.py # 内置工具
│       │   └── mcp_server.py   # MCP 协议服务端
│       ├── memory/             # 记忆系统
│       │   └── memory_store.py # MemoryStore / MemoryEnricher
│       ├── feedback/           # 反馈闭环
│       │   └── feedback_loop.py # FeedbackLoop / LearningEngine
│       ├── mod_manager/        # 多 Mod 管理
│       │   ├── mod_manager.py  # MultiModManager / ModStack
│       │   └── mod_exporter.py # ModExporter / ModManifest
│       └── validation/         # 验证引擎
│           ├── enhanced_validator.py # EnhancedValidator（v2）
│           ├── static_validator.py   # StaticValidatorV3（VAL-STATIC-01..05：schema/引用/数值/语法/危险API）
│           └── runtime_probe.py      # HeadlessRuntimeProbe（VAL-RUNTIME-01..05：ProbeSpec/启动/状态/报错/报告）
└── tests/                      # 测试（337 个，全绿）
    ├── perception/ models/ infrastructure/          # v2 基础（含 test_source.py 证据链）
    ├── cognition/ evaluation/ toolchain/            # Session 4 测试债清偿（批次 0）
    └── core/
        ├── adapters/ tool_gateway/ perception/      # 批次 1-2（协议/网关/语义提升）
        ├── planning/（含 test_batch2_planning.py）   # 批次 2（动作 Schema/Patch 合成）
        └── validation/（含 test_batch3_validation.py，内含 UdifyBench 10 golden case）
```

---

## 4. 快速开始

### 安装依赖

项目使用 `pyproject.toml`，当前阶段依赖极少（仅 numpy）：

```bash
# 开发模式安装
pip install -e ".[dev]"

# 或仅安装核心依赖
pip install -e .
```

### 运行测试

```bash
# 全部测试（337 个，~0.7 秒）
python3 -m pytest tests/ -v

# 特定模块
python3 -m pytest tests/perception/ -v
python3 -m pytest tests/models/ -v
python3 -m pytest tests/core/planning/ -v
python3 -m pytest tests/infrastructure/ -v

# 覆盖率
python3 -m pytest tests/ --cov=udify --cov-report=term-missing
```

### 类型检查

```bash
mypy udify/
```

### 代码风格

```bash
ruff check udify/ tests/
ruff format udify/ tests/
```

---

## 5. 核心数据流

```
[原始游戏目录]
    ↓
InputSanitizer.sanitize(intent) → SanitizationResult
    ↓
IncrementalPerception.perceive(path) → ContentGraph
    ↓
SessionManager.create_session() → ModSession
    ↓
IntentClassifier.classify() → Intent / StructuredIntent（认知层）
    ↓
ReferenceResolver.resolve_from_structured_intent() → [Reference]
    ↓
ConflictDetector.detect() → [Conflict]
    ↓
Planner.plan(graph, intent) → PlanResult
    ↓
CostController.plan_with_budget() → PlanResult（预算控制）
    ↓
PlanResult.to_patch() → CDLPatch
    ↓
EnhancedValidator.validate(patch) → ValidationReport
    ↓
GameKnowledgeGraph.validate_mod_against_knowledge() → KnowledgeWarnings
    ↓
VirtualFileSystem.write_file() → 预览模式
    ↓
IntentAlignmentEvaluator.evaluate() → 对齐评分（评估层）
    ↓
PatchApplicator.apply(patch, graph) → ContentGraph（修改后）
    ↓
SandboxExecutor.validate_script_safety() → SafetyReport
    ↓
MultiModManager.install_mod() → ModStack
    ↓
FeedbackLoop.collect_feedback() → LearningEngine 优化
    ↓
[修改后的游戏文件]
```

---

## 6. 编码规范

### Python

- **类型注解**: 所有函数必须有完整的 type hints（mypy strict mode）
- **不可变性优先**: 使用 `frozen=True` dataclass 表示核心数据结构
- **纯函数优先**: 副作用显式标记，状态修改函数命名用动词（`apply_`, `update_`）
- **错误处理**: 明确异常路径，不使用裸 `except`
- **文档字符串**: 所有公共类/方法使用 Google-style docstring

### 测试

- **TDD**: 新功能先写测试
- **Fixture**: 使用 pytest fixture 共享测试数据
- **参数化**: 类似场景使用 `@pytest.mark.parametrize`
- **覆盖率**: 目标 80%+

### 提交规范（建议）

```
<type>: <description>

<body>

type:
  - feat: 新功能
  - fix: 修复
  - docs: 文档
  - test: 测试
  - refactor: 重构
  - perf: 性能优化
  - chore: 构建/工具链
```

---

## 7. 当前状态快照

**截至 2026-07-27**（批次 0-3 完成，北极星达成；详见 docs/ITERATION-PLAN-2026-07.md）：

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
| 前端工作台 (web/, Next.js 15) | ✅ 审阅切片 | 2026-08 批次 5 |

**已完成代码行数**: ~24,500 行 Python + ~5,700 行测试（395 测试全绿）+ web/ 前端

**产品入口**：`udify serve`（API，127.0.0.1:8765）+ `cd web && pnpm dev`（工作台，localhost:3000）。状态目录 `./.udify/`（jobs.db + 任务工件）。

---

## 8. 关键设计决策

### D1: CDL Patch 作为核心抽象

系统不直接生成修改后的文件，而是生成结构化的 `CDLPatch`。这带来了可验证性、可回滚性、可审计性和可合并性。

### D2: LLM 导演 + MCTS 制片人

规划不依赖纯 LLM 生成（不可靠、成本高），而是使用 MCTS 做系统性搜索，LLM 仅作为价值评估函数。当前默认使用启发式价值函数，LLM 为可插拔升级。

### D3: 研究先于实现

在写每一行代码前，先完成对应的架构文档。当前已有 25+ 份文档覆盖所有子系统。

---

## 9. 环境信息

- **操作系统**: macOS (darwin)
- **Python**: 3.14.4 (Homebrew)
- **工作目录**: `/workspace/udify` (根据实际部署环境调整)
- **Git 仓库**: 是
- **虚拟环境**: 未强制要求（当前依赖极少）

---

## 10. 联系与决策

- **项目所有者**: JC
- **核心需求来源**: `docs/VISION.md`, `docs/PLAN.md`, `docs/ARCHITECTURE-v2.md`
- **最新进展**: `docs/PROGRESS-SESSION-3.md`
- **市场验证**: `docs/COMMUNITY-RESEARCH.md`, `docs/RESEARCH-v3-GitHub-UGC-Agent.md`

---

## 11. JC 的协作风格偏好

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
