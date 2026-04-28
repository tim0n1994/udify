# Udify 开发进展报告 — Session 3（归档版）

> **归档日期**: 2026-04-28
> **会话范围**: 核心引擎补全 — 记忆系统、执行调度器、LLM 集成、二进制解析、回滚机制
> **测试状态**: 183/183 全部通过
> **代码总量**: 58 个 Python 文件，15,217 行核心代码 + 2,927 行测试代码
> **会话状态**: 日后再战 — 阶段 1 骨架完成，认知层与评估层为最大缺口

---

## 目录

1. [Session 3 成果概览](#1-session-3-成果概览)
2. [新增模块详解](#2-新增模块详解)
3. [现有模块增强](#3-现有模块增强)
4. [与架构文档对照](#4-与架构文档对照)
5. [v1.1 盲点清单解决情况](#5-v11-盲点清单解决情况)
6. [已知问题与技术债务](#6-已知问题与技术债务)
7. [最大缺口：日后再战优先级](#7-最大缺口日后再战优先级)
8. [关键接口速查](#8-关键接口速查)
9. [文件清单与代码统计](#9-文件清单与代码统计)

---

## 1. Session 3 成果概览

Session 3 在 Session 2（CDL Patch + Planning Engine）的基础上，补全了核心引擎的多个关键子系统：

| 新增/增强模块 | 文件 | 代码行 | 说明 |
|-------------|------|--------|------|
| **记忆系统** | `core/memory/memory_store.py` | ~350 | 意图模板库、用户偏好、执行历史、知识库 |
| **LLM 客户端** | `core/llm_client.py` | ~120 | 统一 OpenAI/Anthropic 接口，自动降级 |
| **执行调度器** | `core/execution/scheduler.py` | ~572 | 依赖图、并行执行、原始状态捕获、完整回滚 |
| **MCP 服务器** | `core/execution/mcp_server.py` | ~362 | MCP 协议服务端基础实现 |
| **二进制资源解析** | `core/perception/incremental_perception.py` | 增强 | ASF/MSF/MPC/MAP/MMF/SHD 格式启发式解析 |
| **端到端管道** | `core/pipeline.py` | ~280 | 11 步完整流程：消毒→感知→规划→成本→验证→知识→VFS→Diff→确认→应用 |
| **CLI 入口** | `cli.py` | ~200 | mod/preview/apply/rollback/stats/validate 子命令 |
| **补丁执行器** | `core/execution/patch_executor.py` | ~150 | CDLPatch → VFS 文件修改的桥梁 |

**Session 3 总新增代码**: ~2,200 行核心代码

---

## 2. 新增模块详解

### 2.1 Memory System（记忆系统）

**文件**: `udify/core/memory/memory_store.py`

**架构定位**: ARCHITECTURE-v2.md §5 — 记忆系统（User Preference Store / Content Knowledge Graph / Template Library / Execution History）

**实现内容**:
- `MemoryStore`: JSON 文件持久化，四大存储区
  - 意图模板库 (`_intent_templates`): 关键词匹配 + 成功率加权 + 版本化
  - 用户偏好 (`_user_preferences`): 难度基线、喜爱/厌恶机制、保守倾向（0-1）
  - 执行历史 (`_execution_history`): 时间戳、意图、评分、耗时、引用
  - 知识库 (`_knowledge_base`): 事实性知识，领域分类
- `MemoryEnricher`: 从 Patch 提取模板、从反馈更新用户偏好、自动调整保守倾向
- 向量检索简化版: 基于关键词重叠的相似度匹配（预留向量数据库升级接口）

**持久化路径**: `.udify/memory_store.json`

### 2.2 LLMClient（LLM 统一接口）

**文件**: `udify/core/llm_client.py`

**架构定位**: ARCHITECTURE-v2.md §4.3 — LLM 价值函数 / §10.1 — LLM Provider (Multi)

**实现内容**:
- 统一接口: `complete()`, `chat()`, `is_available()`
- 支持 OpenAI (`openai` 库) 和 Anthropic (`anthropic` 库)
- 自动降级: 调用失败时返回 `None`，上层可切换至 HeuristicValueFunction
- 配置驱动: `UDIFY_LLM_PROVIDER` / `UDIFY_LLM_MODEL` / `UDIFY_LLM_API_KEY` 环境变量

**注意**: 当前为接口层，尚未接入真实 API 密钥进行端到端验证。

### 2.3 ExecutionScheduler（执行调度器）

**文件**: `udify/core/execution/scheduler.py`

**架构定位**: ARCHITECTURE-v2.md §4.4 — 执行层状态机 + §12.2 技术债务 TD-002

**实现内容**:
- `OperationNode`: 依赖图节点（dependencies/dependents/visits/value/status/error/original_state）
- `_build_dependency_graph()`: 基于 target_id 和 asset_id 的依赖关系自动构建
- `_execute_operations()`: 拓扑排序 + 并行组识别 + 串行执行
- `_capture_original_state()`: 执行前捕获节点/边/资产的原始属性快照
- `_create_rollback_operation()`: 利用快照生成精确的逆操作
  - add_node → remove_node
  - remove_node → add_node（含原始数据恢复）
  - modify_node → modify_node（恢复原属性）
  - add_edge → remove_edge
  - remove_edge → add_edge（含原始数据恢复）
  - modify_edge → modify_edge（恢复原属性）
  - add_asset → remove_asset
  - remove_asset → add_asset（含原始数据恢复）
  - modify_asset → modify_asset（含原始数据恢复）
- `_rollback_operations()`: 逆向遍历已执行操作，逐一回滚
- `_mark_dependents_failed()`: 级联标记依赖失败

**配置**: `SchedulerConfig`（enable_parallel/enable_rollback/max_concurrent_workers）

### 2.4 MCP Server

**文件**: `udify/core/execution/mcp_server.py`

**架构定位**: ARCHITECTURE-v2.md §7 — 工具层（MCP Protocol）/ ARCHITECTURE-MCP-ECOSYSTEM.md

**实现内容**:
- MCP 协议基础服务端（362 行）
- 工具发现 (capability 声明)
- 工具调用 JSON-RPC 接口
- 与 ToolRegistry 集成

**完成度**: ~20% — 基础协议实现完成，完整的 MCP 生态（外部工具注册、多客户端连接）待扩展。

### 2.5 Binary Asset Parser（二进制资源解析）

**文件**: `udify/core/perception/incremental_perception.py`（BinaryAssetParser 类）

**架构定位**: ARCHITECTURE-GAME-MOD-v1.md — 8 种二进制格式解码器映射

**实现内容**:
- ASF/MSF (音频): 格式检测、通道数/采样率/时长解析
- MPC (动画包): 条目统计
- MAP (地图): 维度/区块统计
- MMF (多媒体): 流计数
- SHD (Shader): 文本提取

**限制**: 当前为启发式解析（基于文件头特征），非完整的二进制格式逆向工程。对于 miu2d 引擎，足以支撑 Mod 自动化流程中的资源识别与元数据提取。

### 2.6 UdifyPipeline（端到端管道）

**文件**: `udify/core/pipeline.py`

**架构定位**: ARCHITECTURE-v2.md §2.2 — 核心数据流

**实现内容**（11 步完整流程）:
1. 输入消毒 (`InputSanitizer.sanitize`)
2. 感知分析 (`IncrementalPerception.perceive`)
3. 规划生成 (`Planner.plan`)
4. 成本检查 (`CostController.plan_with_budget`)
5. 静态验证 (`EnhancedValidator.validate`)
6. 知识验证 (`GameKnowledgeGraph.validate_mod_against_knowledge`)
7. 预览应用 (`VirtualFileSystem.write_file`)
8. 差异展示 (`PreviewFormatter.format`)
9. 等待确认（人工在环）
10. 执行应用 (`PatchExecutor.execute`)
11. 反馈收集（`FeedbackLoop.collect_feedback` 预留）

**注意**: 步骤 9（人工确认）在 CLI 模式下为自动确认（或需显式 `--dry-run`）。

### 2.7 CLI（命令行入口）

**文件**: `udify/cli.py`

**架构定位**: ARCHITECTURE-v2.md §2.1 — CLI Tool (Python)

**实现内容**:
- `udify mod <path> <intent>`: 创建 Mod（完整管道）
- `udify preview <path> <intent>`: 预览模式（不应用）
- `udify apply <path> <patch_file>`: 应用已有 Patch
- `udify rollback <path>`: 回滚最后 Mod
- `udify stats <path>`: 显示目录统计
- `udify validate <path>`: 验证目录可解析性

**入口**: `pyproject.toml` 中定义 `udify = "udify.cli:cli_entry"`

---

## 3. 现有模块增强

### 3.1 LLMValueFunction（规划层）

**文件**: `udify/core/planning/value_function.py`

**增强内容**:
- 接入 `LLMClient`，构造中文评估 prompt
- 响应解析：提取 0-1 评分，与启发式结果 7:3 混合
- 自动降级：LLM 不可用时 fallback 到 `HeuristicValueFunction`
- 结果缓存：避免重复调用

### 3.2 PatchExecutor（执行层）

**文件**: `udify/core/execution/patch_executor.py`

**增强内容**:
- CDLPatch → VFS 文件修改的精确映射
- 节点 ID 反解规则: `{file_path}_{section_name}` → 文件路径
- 支持 modify_property / modify_node 到 INI/OBJ/Lua 的转换
- 错误隔离：单操作失败不影响其他操作

### 3.3 ToolRegistry + BuiltinTools

**文件**: `udify/core/execution/tool_registry.py`, `builtin_tools.py`

**增强内容**:
- 内置工具注册（文件读写、图操作、配置修改）
- MCP 风格 capability 声明
- 工具发现接口 (`discover`)

---

## 4. 与架构文档对照

### ARCHITECTURE-v2.md 模块映射

| 章节 | 模块 | 代码映射 | 完成度 |
|------|------|----------|--------|
| §3 CDL | ContentGraph + Patch | `models/` | 100% |
| §4.1 感知层 | Perception Engine | `core/perception/` | 85%（缺 Tree-sitter/Roslyn） |
| §4.2 认知层 | Cognition Layer | ❌ 无 | 0% |
| §4.3 规划层 | Planning Engine | `core/planning/` | 90%（MCTS + LLMValueFunction + CostController） |
| §4.4 执行层 | Execution Engine | `core/execution/` | 80%（缺 gVisor/Docker 沙箱） |
| §4.5 评估层 | Evaluation Layer | `core/validation/` | 40%（静态+知识+安全，缺意图对齐/可运行性/性能） |
| §5 记忆系统 | Memory System | `core/memory/` | 80%（JSON 持久化，缺向量数据库） |
| §6 事件总线 | Event Bus | `core/infrastructure/event_bus.py` | 50%（内存实现，缺 Redis Streams） |
| §7 工具层 | Tool Layer (MCP) | `core/execution/mcp_server.py` | 20% |
| §8 Udiface | 前端/API | ❌ 无 | 0% |
| §9 安全 | 6 层安全 | `core/security/sanitizer.py` | 30%（L1+L2 部分） |
| §10 基础设施 | DB/Cache/Workflow | `core/infrastructure/` | 40%（内存/JSON 代替真实服务） |

---

## 5. v1.1 盲点清单解决情况

来自 `ARCHITECTURE-GAME-MOD-v1.1-REVIEW.md` 附录 A（共 52 项）：

| 类别 | 数量 | 已解决 | 待解决 | 解决率 |
|------|------|--------|--------|--------|
| 数据流盲点（B1.1-B1.6） | 6 | 6 | 0 | **100%** |
| 状态管理盲点（B2.1-B2.5） | 5 | 5 | 0 | **100%** |
| 错误处理盲点（B3.1-B3.7） | 7 | 7 | 0 | **100%** |
| 安全边界盲点（B4.1-B4.6） | 6 | 3 | 3 | 50% |
| 性能成本盲点（B5.1-B5.8） | 8 | 4 | 4 | 50% |
| 协作并发盲点（B6.1-B6.5） | 5 | 2 | 3 | 40% |
| 生态商业盲点（B7.1-B7.7） | 7 | 1 | 6 | 14% |
| 关系契约盲点（B8.1-B8.8） | 8 | 3 | 5 | 38% |
| **总计** | **52** | **31** | **21** | **60%** |

**Session 3 解决的盲点**:
- B3.1 降级策略: CostController + LLMClient 自动降级 ✅
- B3.2 部分失败恢复: ExecutionScheduler 原始状态捕获 + 回滚 ✅
- B5.1 LLM 成本: CostController ✅
- B5.3 缓存分层: CacheManager L1/L2/L3 ✅（L3 为占位）

---

## 6. 已知问题与技术债务

| ID | 描述 | 严重度 | 状态 |
|----|------|--------|------|
| TD-001 | 感知层使用硬编码引擎特征 | 低 | ✅ 接受（MVP 验证期） |
| TD-002 | 规划器无持久化搜索状态 | 中 | 🟡 ExecutionScheduler 已支持操作级回滚，但 MCTS 树本身无检查点 |
| TD-003 | 评估层依赖启发式规则 | 中 | 🟡 LLMValueFunction 已实现，但未接入真实 API 验证 |
| TD-004 | 单节点 Neo4j | 低 | ✅ 当前使用内存图，无此问题 |
| TD-005 | 无分布式执行 | 中 | 🟡 Scheduler 支持并行组，但无多进程/多机 |
| TD-006 | 认知层完全缺失 | **高** | ⬜ 阻塞端到端演示 |
| TD-007 | 评估层意图对齐缺失 | **高** | ⬜ 阻塞端到端演示 |
| TD-008 | Docker/gVisor 沙箱为占位 | 中 | 🟡 进程级沙箱已兜底 |
| TD-009 | Redis 事件总线为占位 | 中 | 🟡 内存 EventBus 可用 |
| TD-010 | 异步 I/O 未实现 | 中 | ⬜ 当前全同步阻塞 |

---

## 7. 最大缺口：日后再战优先级

### 🔴 P0：阻塞第一个真实 Mod 演示

1. **认知层 (`core/cognition/`)** — ARCHITECTURE-v2.md §4.2
   - `IntentClassifier`: 将自然语言分类为结构化意图类型
   - `ReferenceResolver`: 将"像魂系"映射到特征向量
   - `ConflictDetector`: 检测用户意图中的内在矛盾
   - **为什么阻塞**: 当前 `Intent` 只是简单字符串，Planning 层无法理解"更难"具体指什么参数变化

2. **评估层 — 意图对齐评估 (`core/evaluation/intent_alignment.py`)** — ARCHITECTURE-v2.md §4.5
   - `IntentAlignmentEvaluator`: LLM 评估"改造结果是否符合用户意图"
   - `ConsistencyEvaluator`: 检测规则冲突、数值溢出、循环依赖
   - `RunabilityTester`: 沙箱内启动测试
   - **为什么阻塞**: 没有这层，系统无法闭环验证"改对了没有"

### 🟡 P1：通用化与性能

3. **Tree-sitter AST 引擎** — ARCHITECTURE-v2.md §4.1
   - 通用代码分析能力（Unity C#/Godot GDScript 等）
   - 当前只有 miu2d 特化解析器

4. **异步 I/O + Redis 事件总线** — ARCHITECTURE-v2.md §6
   - 将 EventBus 从内存升级到 Redis Streams
   - aiofiles 异步文件操作
   - 支持真正的异步流水线和多 worker

5. **真实数据库接入** — ARCHITECTURE-v2.md §10.1
   - PostgreSQL 替代 JSON 文件持久化
   - Neo4j 替代内存图

### 🟢 P2：平台化

6. **API 网关层** — ARCHITECTURE-API.md
7. **前端 ReactFlow 编辑器** — ARCHITECTURE-FRONTEND.md
8. **可观测性（OpenTelemetry）** — ARCHITECTURE-OBSERVABILITY.md

---

## 8. 关键接口速查

### 8.1 端到端入口

```python
from udify.core.pipeline import UdifyPipeline

pipeline = UdifyPipeline()
result = pipeline.create_mod(
    game_root="/path/to/miu2d/game",
    intent="让游戏更难，像魂系那种慢慢变强的感觉",
    mod_name="hardcore_mode"
)
# result.success: bool
# result.patch: CDLPatch
# result.validation_report: ValidationReport
```

### 8.2 独立模块使用

```python
# 感知
from udify.core.perception.incremental_perception import IncrementalPerception
graph = IncrementalPerception().perceive("/path/to/game")

# 规划
from udify.core.planning.planner import Planner
plan = Planner().plan(graph, intent="增加敌人血量")

# 执行
from udify.core.execution.scheduler import ExecutionScheduler
result = ExecutionScheduler().execute_patch(plan.to_patch(), graph)

# 回滚
if not result.success:
    # result.rollback_operations 已生成
    pass
```

### 8.3 CLI 快速命令

```bash
# 开发模式安装
pip install -e ".[dev]"

# 完整测试
python3 -m pytest tests/ -v  # 183 passed

# 创建 Mod
udify mod /path/to/game "让游戏更难" --name hardcore

# 预览（不应用）
udify preview /path/to/game "增加敌人血量"

# 类型检查
mypy udify/

# 代码风格
ruff check udify/ tests/
ruff format udify/ tests/
```

---

## 9. 文件清单与代码统计

### 9.1 全部 Python 文件（58 个）

```
udify/
├── __init__.py
├── cli.py                              # 命令行入口
├── models/
│   ├── __init__.py
│   ├── content_graph.py                # ContentGraph / ContentNode / ContentEdge / ContentAsset
│   └── cdl_patch.py                    # CDLPatch / PatchOperation / PatchValidator / PatchApplicator / GraphDiffer
├── core/
│   ├── __init__.py
│   ├── pipeline.py                     # UdifyPipeline（端到端）
│   ├── llm_client.py                   # LLMClient（OpenAI/Anthropic）
│   ├── perception/
│   │   ├── __init__.py
│   │   ├── engine_detector.py          # 引擎检测器
│   │   ├── resource_extractor.py       # 资源提取器
│   │   ├── mechanism_analyzer.py       # 机制分析器
│   │   ├── incremental_perception.py   # 增量感知 + BinaryAssetParser
│   │   └── parsers/
│   │       ├── __init__.py
│   │       ├── ini_parser.py           # INI 配置解析
│   │       ├── obj_parser.py           # OBJ 数据解析
│   │       ├── npc_parser.py           # NPC 脚本解析（218 DSL 命令）
│   │       └── lua_parser.py           # Lua 脚本解析
│   ├── planning/
│   │   ├── __init__.py
│   │   ├── state.py                    # PlanState / Intent / PlanContext
│   │   ├── action_space.py             # ActionSpace
│   │   ├── value_function.py           # HeuristicValueFunction / LLMValueFunction
│   │   ├── mcts.py                     # MCTSNode / MCTSTree
│   │   ├── planner.py                  # Planner / PlanResult
│   │   └── cost_controller.py          # CostController
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── vfs.py                      # VirtualFileSystem
│   │   ├── sandbox.py                  # SandboxExecutor
│   │   ├── patch_executor.py           # PatchExecutor
│   │   ├── scheduler.py                # ExecutionScheduler
│   │   ├── tool_registry.py            # ToolRegistry
│   │   ├── builtin_tools.py            # 内置工具
│   │   └── mcp_server.py               # MCP 服务端
│   ├── infrastructure/
│   │   ├── __init__.py
│   │   ├── event_bus.py                # EventBus
│   │   ├── config_center.py            # ConfigCenter
│   │   ├── config_loader.py            # YAML/JSON/TOML 加载
│   │   ├── audit_log.py                # AuditLog（链式哈希）
│   │   ├── cache_manager.py            # CacheManager（L1/L2/L3）
│   │   ├── state_persistence.py        # StatePersistence
│   │   ├── backup_manager.py           # BackupManager
│   │   └── preview_formatter.py        # PreviewFormatter
│   ├── security/
│   │   ├── __init__.py
│   │   └── sanitizer.py                # InputSanitizer / OutputValidator
│   ├── session/
│   │   ├── __init__.py
│   │   └── session_manager.py          # ModSession / SessionManager
│   ├── knowledge/
│   │   ├── __init__.py
│   │   └── knowledge_graph.py          # GameKnowledgeGraph
│   ├── feedback/
│   │   ├── __init__.py
│   │   └── feedback_loop.py            # FeedbackLoop / LearningEngine
│   ├── mod_manager/
│   │   ├── __init__.py
│   │   ├── mod_manager.py              # MultiModManager / ModStack
│   │   └── mod_exporter.py             # ModExporter / ModManifest
│   ├── memory/
│   │   ├── __init__.py
│   │   └── memory_store.py             # MemoryStore / MemoryEnricher
│   └── validation/
│       ├── __init__.py
│       └── enhanced_validator.py       # EnhancedValidator
└── tests/                              # 测试目录
    ├── perception/test_perception.py
    ├── models/test_cdl_patch.py
    ├── core/planning/test_planning.py
    └── infrastructure/
        ├── test_infrastructure.py
        ├── test_advanced_modules.py
        └── test_parsers_and_pipeline.py
```

### 9.2 代码统计

| 类别 | 文件数 | 代码行数 |
|------|--------|----------|
| 核心代码 (`udify/`) | 58 | 15,217 |
| 测试代码 (`tests/`) | 6 | 2,927 |
| **总计** | **64** | **18,144** |

### 9.3 测试覆盖

| 测试文件 | 测试数量 | 状态 |
|----------|----------|------|
| `tests/perception/test_perception.py` | 19 | ✅ 通过 |
| `tests/models/test_cdl_patch.py` | 32 | ✅ 通过 |
| `tests/core/planning/test_planning.py` | 30 | ✅ 通过 |
| `tests/infrastructure/test_infrastructure.py` | 40 | ✅ 通过 |
| `tests/infrastructure/test_advanced_modules.py` | 38 | ✅ 通过 |
| `tests/infrastructure/test_parsers_and_pipeline.py` | 24 | ✅ 通过 |
| **总计** | **183** | **全部通过** |

---

## 10. 日后再战检查清单

当恢复开发时，按以下顺序检查：

- [ ] 运行 `python3 -m pytest tests/ -v` 确认 183 测试仍通过
- [ ] 运行 `mypy udify/` 确认类型检查无新增错误
- [ ] 检查 `docs/` 是否有新的架构文档需要对照
- [ ] 确认当前最大缺口是否变化（当前为认知层 + 评估层意图对齐）
- [ ] 决定是否接入真实 LLM API 验证 LLMValueFunction
- [ ] 准备真实 miu2d 游戏目录做端到端演示

---

> **"架构是活的文档，代码是骨架，血肉在于认知层和评估层的补全。日后再战，先把 miu2d 的第一个 Mod 跑通。"**
>
> —— Session 3 归档留言
