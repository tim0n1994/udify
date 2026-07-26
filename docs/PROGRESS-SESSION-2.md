<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 开发进展报告 — Session 2

> **归档日期**: 2026-04-27
> **会话范围**: CDL Patch/Diff 系统 + Planning Engine（MCTS+LLM）完整实现
> **测试状态**: 81/81 全部通过
> **代码增量**: 5 个新模块 ~1,474 行 Python + 62 个新测试

---

## 目录

1. [工作背景与动机](#1-工作背景与动机)
2. [Phase 1 当前进度](#2-phase-1-当前进度)
3. [CDL Patch/Diff 系统](#3-cdl-patchdiff-系统)
4. [Planning Engine 规划引擎](#4-planning-engine-规划引擎)
5. [测试体系](#5-测试体系)
6. [架构决策记录 (ADR)](#6-架构决策记录-adr)
7. [已知问题与限制](#7-已知问题与限制)
8. [下一步建议](#8-下一步建议)
9. [文件清单](#9-文件清单)

---

## 1. 工作背景与动机

Session 1 完成了项目愿景、架构设计文档（v2.0/v2.1）和深度调研，并实现了**感知引擎（Perception Engine）**——能够将原始游戏文件解析为结构化的 `ContentGraph`。Session 1 遗留的核心缺口是：

1. **缺乏内容修改的中间表示**：系统需要一个标准化的方式来表达"对 ContentGraph 的修改"，而非直接生成完整的新文件。
2. **缺乏意图到修改的转换层**：用户用自然语言描述意图后，系统需要一种机制将这种意图转化为结构化的修改计划。

Session 2 的核心任务就是填补这两个缺口：
- **CDL Patch/Diff 系统**：定义"内容修改语言"，使修改可验证、可回滚、可审计、可合并
- **Planning Engine**：基于 MCTS + 启发式价值函数的意图驱动规划器，将用户意图转化为 CDLPatch

---

## 2. Phase 1 当前进度

根据 `docs/PLAN.md` 中 Phase 1 的模块划分：

| 模块 | 状态 | 说明 |
|------|------|------|
| **A. 感知引擎 v1** | ✅ 完成 | 引擎检测、资源提取、机制分析，19 测试通过 |
| **B. 规划引擎 v1** | ✅ 完成 | MCTS + ActionSpace + ValueFunction，30 测试通过 |
| **C. 执行引擎 v1** | ⬜ 未开始 | 需要 MCP 工具生态 + 沙箱执行环境 |
| **D. 记忆系统 v1** | ⬜ 未开始 | 需要 Neo4j/PostgreSQL 持久化层 |
| **E. 质量评估 v1** | ⬜ 未开始 | 需要 Patch 验证 + 运行时测试框架 |
| **F. 前端原型 v1** | ⬜ 未开始 | 需要 ReactFlow DAG 编辑器实现 |
| **G. 沙箱环境 v1** | ⬜ 未开始 | 需要 gVisor + 容器化执行 |

**当前已完成的数据流**：

```
[原始游戏文件] → PerceptionEngine.perceive() → ContentGraph
                                                     ↓
用户意图 (str) → Planner.plan() → MCTSTree.search() → PlanResult
                                                         ↓
                                              PlanResult.to_patch() → CDLPatch
```

---

## 3. CDL Patch/Diff 系统

### 3.1 设计哲学

CDL Patch 是 Udify 区别于其他 AI 内容生成系统的**核心创新点**：

| 特性 | 传统 AI 生成 | Udify CDL Patch |
|------|-------------|-----------------|
| 输出格式 | 完整文件重写 | 结构化 Diff |
| 可验证性 | ❌ 黑盒 | ✅ 每个操作独立验证 |
| 可回滚 | ❌ 需手动比对 | ✅ 原子性 + 快照回滚 |
| 冲突检测 | ❌ 文本级 diff | ✅ 语义级冲突建模 |
| 可审计 | ❌ 无法追溯 | ✅ 完整操作链 + 作者签名 |
| 可合并 | ❌ 手工解决 | ✅ 三路合并 + 冲突列表 |

### 3.2 核心类设计

```
PatchOperation (frozen dataclass)
├── op_type: OpType (9 种原子操作)
├── target_id: str
├── payload: Dict[str, Any]
└── __hash__: 递归哈希（支持嵌套 dict/list）

CDLPatch
├── operations: List[PatchOperation] (有序)
├── intent: str (人类可读意图)
├── author: str (人类用户名 / AI Agent ID)
├── parent_hash: Optional[str] (版本链)
├── conflicts: List[PatchConflict] (合并时产生)
└── to_dict() / from_dict() (完整序列化)

PatchValidator
├── validate(patch, graph) → List[PatchConflict]
│   ├── 阶段 1: 内部冲突检测（重复 ID、重复修改）
│   └── 阶段 2: 交叉引用验证（边→已删除节点）

PatchApplicator
├── apply(patch, graph, validate=True, atomic=True) → (bool, conflicts)
│   └── 失败时自动回滚（基于 deepcopy 快照）
├── rollback(patch, graph) → bool
│   └── 恢复到 _original_state 快照

GraphDiffer
├── diff(old_graph, new_graph) → CDLPatch
│   └── 节点差异 + 属性差异 + 边差异 + 资源差异
```

### 3.3 9 种原子操作

| 操作类型 | 作用 | 典型应用场景 |
|----------|------|-------------|
| `ADD_NODE` | 添加内容节点 | 新增角色、物品、任务 |
| `REMOVE_NODE` | 删除节点（连带删除相关边） | 移除废弃机制 |
| `MODIFY_PROPERTY` | 修改节点属性 | 调整数值参数 |
| `ADD_EDGE` | 添加关系边 | 建立新的依赖/引用 |
| `REMOVE_EDGE` | 删除关系边 | 解除错误关联 |
| `MODIFY_EDGE` | 修改边的权重/属性 | 调整关联强度 |
| `ADD_ASSET` | 添加原始资源 | 新增纹理/音频/脚本 |
| `REMOVE_ASSET` | 删除资源 | 清理未使用资源 |
| `MODIFY_ASSET` | 修改资源元数据 | 更新文件路径/哈希 |

### 3.4 冲突类型 (ConflictType)

系统显式建模了 9 种冲突：

1. `SAME_NODE_REMOVE_VS_MODIFY` — 一方删除节点，另一方修改
2. `SAME_PROPERTY_MODIFY` — 双方修改同一属性的不同值
3. `EDGE_SOURCE_REMOVED` / `EDGE_TARGET_REMOVED` — 边的端点被删除
4. `DUPLICATE_NODE_ID` — Patch 内或图中已存在相同 ID
5. `DUPLICATE_EDGE` — 重复添加同一条边
6. `ASSET_REFERENCED_BY_NODE` — 资源被引用但已被删除
7. `CIRCULAR_DEPENDENCY` — 操作后产生循环依赖（预留）
8. `METADATA_MISMATCH` — 元数据冲突（如版本号不一致）

### 3.5 技术要点

- **不可变性**: `PatchOperation` 使用 `@dataclass(frozen=True)`，创建后不可变。这是审计和重放的基础。
- **递归哈希**: `__hash__` 方法递归处理 `dict` / `list`，使包含复杂 payload 的操作仍可放入 `set` / 作为 `dict` 键。
- **原子性**: `atomic=True` 时，任何操作失败都会触发自动回滚，基于 `deepcopy` 的快照机制。
- **序列化**: 完整的 `to_dict() / from_dict()` 支持，为后续数据库存储和版本控制打下基础。

---

## 4. Planning Engine 规划引擎

### 4.1 设计哲学

Planning Engine 实现了文档中定义的 **"LLM 导演 + MCTS 制片人 + 工具演员"** 架构：

| 角色 | 对应组件 | 职责 |
|------|---------|------|
| **导演** | `ValueFunction` (LLM) | 评估状态好坏，提供创意判断 |
| **制片人** | `MCTSTree` | 系统性搜索最优动作序列，平衡探索与利用 |
| **演员** | `ActionSpace` | 在约束下生成可执行的具体操作 |

当前版本使用 `HeuristicValueFunction` 作为默认实现，`LLMValueFunction` 为占位接口。

### 4.2 核心类设计

```
PlanState
├── graph: ContentGraph (当前内容图谱)
├── intent: Intent (用户意图)
├── context: PlanContext (技术约束 + 用户偏好)
├── action_history: List[PatchOperation] (已执行序列)
├── depth: int (当前深度)
└── copy() / apply_action() / is_terminal() / get_hash()

Intent (结构化意图)
├── description: str (自然语言描述)
├── target_media_type: Optional[str]
├── priority_nodes: List[str] (重点节点)
├── constraints: List[str] (禁止行为)
└── style_hints: Dict[str, Any] (风格偏好)

PlanContext (规划上下文)
├── max_operations / max_depth (搜索限制)
├── risk_tolerance (风险容忍度 0.0-1.0)
├── preservative_bias (保守性偏好 0.0-1.0)
└── previous_patches / successful_patterns (历史记忆)

ActionSpace (动作生成器)
├── generate_actions(state) → List[PatchOperation]
│   ├── _generate_add_actions() — 根据意图关键词生成添加操作
│   ├── _generate_remove_actions() — 根据保守性偏好限制删除
│   ├── _generate_modify_actions() — 根据意图生成属性修改
│   ├── _deduplicate_actions() — 基于哈希去重
│   └── _score_action() — 意图关键词匹配 + 操作安全度打分

ValueFunction (ABC)
├── evaluate(state) → float [-1, 1]
├── evaluate_batch(states) → List[float]
└── is_terminal_good(state) → bool (早期终止)

HeuristicValueFunction (默认实现)
├── 结构完整性 (25%): 孤立节点比例、边密度
├── 意图匹配度 (35%): 关键词重叠、优先节点修改
├── 操作合理性 (20%): 操作数量适中、冗余检测
└── 保守性 (20%): 删除/修改/添加的加权破坏度

MCTSNode (MCTS 树节点)
├── state: PlanState
├── parent / action / children
├── visit_count / value_sum (UCT 统计)
├── untried_actions (待扩展动作)
├── best_child(c) → MCTSNode (UCT 公式)
├── update(value) (反向传播)
└── get_path() → List[PatchOperation]

MCTSTree (MCTS 搜索)
├── search(initial_state) → MCTSNode
│   ├── _select() — UCT 选择至叶子
│   ├── _expand() — 展开一个未尝试动作
│   ├── _simulate() — 随机 rollout + 价值评估
│   └── _backpropagate() — 统计更新

Planner (入口)
├── plan(graph, intent) → PlanResult
├── plan_with_intent(graph, intent) → PlanResult (结构化意图)
└── _generate_explanation() → 可解释性摘要
```

### 4.3 MCTS 配置参数

```python
MCTSConfig(
    num_iterations=100,           # 搜索迭代次数
    exploration_constant=1.414,   # UCT 探索常数 (√2)
    max_depth=10,                 # 最大搜索深度
    enable_rollout=True,          # 启用快速 rollout
    rollout_steps=5,              # 每次 rollout 随机步数
    early_termination_threshold=0.9,  # 提前终止阈值
    expand_threshold=1,           # 访问几次后扩展
)
```

### 4.4 ActionSpace 的意图感知设计

ActionSpace 不是盲目生成所有可能的动作，而是**根据意图关键词自适应**：

| 意图关键词 | 生成侧重 |
|-----------|---------|
| "add", "create" | 主要生成 ADD_NODE / ADD_EDGE |
| "remove", "delete" | 主要生成 REMOVE_NODE / REMOVE_EDGE |
| "modify", "change", "update" | 主要生成 MODIFY_PROPERTY |
| "increase difficulty" | 生成难度相关属性修改（difficulty, challenge_rating） |
| "reward", "loot" | 生成掉落率/金币/经验值修改 |
| "speed", "fast" | 生成速度倍率修改 |

**约束传播**：
- `priority_nodes` 不会被删除
- `preservative_bias` 限制删除操作数量
- `max_candidates` 限制候选动作上限（默认 20）

### 4.5 价值函数评估维度

`HeuristicValueFunction` 从四个维度评估状态（权重可配置）：

**结构完整性 (25%)**
- 孤立节点比例：节点不在任何边中时扣分
- 边密度惩罚：边数/节点数 > 3.0 时扣分（防止过度连接）

**意图匹配度 (35%)**
- 基础分：有操作执行 +0.2
- 关键词重叠：意图词与图属性词的重叠度
- 优先节点修改：对 priority_nodes 的操作加分

**操作合理性 (20%)**
- 数量适中：≤3 操作满分，>max_operations 扣分
- 冗余检测：同一目标操作超过 2 次时扣分

**保守性 (20%)**
- 删除操作权重 1.0（破坏最强）
- 修改操作权重 0.5
- 添加操作权重 0.2
- 最终分数 = 1.0 - destruction_score × (1 - preservative_bias)

---

## 5. 测试体系

### 5.1 测试概览

```
总计: 81 个测试
├── tests/models/test_cdl_patch.py: 32 个
├── tests/core/planning/test_planning.py: 30 个
└── tests/perception/test_perception.py: 19 个 (Session 1 遗留)
```

**全部通过**，运行时间约 0.23 秒。

### 5.2 CDL Patch 测试覆盖

| 测试类 | 测试数 | 覆盖点 |
|--------|--------|--------|
| `TestPatchOperation` | 3 | 创建、不可变性、可哈希性 |
| `TestCDLPatch` | 5 | 空 patch、链式添加、摘要、序列化往返、冲突 |
| `TestPatchValidator` | 5 | 有效 patch、重复 ID、删除不存在节点、修改已删除节点、边指向已删除节点 |
| `TestPatchApplicator` | 8 | 添加/修改/删除节点、添加边、添加资源、回滚、原子性失败、非原子部分应用 |
| `TestGraphDiffer` | 5 | 检测新增、删除、属性修改、边新增、复杂组合差异 |
| `TestConvenienceFunctions` | 6 | 6 个便捷函数的参数正确性 |

### 5.3 Planning Engine 测试覆盖

| 测试类 | 测试数 | 覆盖点 |
|--------|--------|--------|
| `TestIntent` | 2 | 创建、序列化 |
| `TestPlanContext` | 2 | 默认值、自定义值 |
| `TestPlanState` | 5 | 创建、拷贝、应用动作、终止判断、哈希变化 |
| `TestActionSpace` | 4 | 动作生成、类型检查、意图驱动、修改动作 |
| `TestValueFunction` | 5 | 启发式评估、缓存、终止判断、结构评估、保守性评估 |
| `TestMCTSNode` | 4 | 创建、更新、UCT 选择、路径获取 |
| `TestMCTSTree` | 3 | 搜索、统计、最佳路径 |
| `TestPlanner` | 4 | 基本规划、结构化意图、转 Patch、摘要 |

---

## 6. 架构决策记录 (ADR)

### ADR-001: PatchOperation 使用 frozen dataclass + 自定义哈希

**问题**: `PatchOperation` 包含 `Dict[str, Any]` payload，默认 `frozen=True` 的 dataclass 无法生成 `__hash__`（因为 dict 不可哈希）。

**方案**: 重写 `__hash__` 方法，递归将 dict/list 转换为 tuple。

**权衡**:
- ✅ PatchOperation 可放入 set/dict，支持 ActionSpace 去重
- ✅ 保持不可变性（审计和重放的基础）
- ⚠️ 哈希计算有轻微开销（对于嵌套较深的 payload）

### ADR-002: PatchApplicator 使用 deepcopy 快照实现回滚

**问题**: 如何支持原子性应用和回滚？

**方案**: 应用前创建 `deepcopy` 快照，失败时整体替换 graph 的 nodes/edges/assets/metadata/semantics。

**权衡**:
- ✅ 实现简单，100% 可靠
- ⚠️ 对于大型图可能有内存和性能开销（当前图规模较小，可接受）
- 🔄 未来优化：使用写时复制（COW）或操作日志（undo log）

### ADR-003: MCTS 使用启发式价值函数作为默认

**问题**: LLM API 调用成本高、延迟大，不适合高频 rollout。

**方案**: 默认使用 `HeuristicValueFunction`，`LLMValueFunction` 作为可选升级。

**权衡**:
- ✅ 零外部依赖，测试和原型验证速度快
- ✅ 0.23 秒完成 81 个测试（包含多次 MCTS 搜索）
- ⚠️ 启发式评估的质量上限低于 LLM
- 🔄 未来：LLMValueFunction 用于关键决策节点，HeuristicValueFunction 用于快速 rollout

### ADR-004: ActionSpace 基于意图关键词做动作类型过滤

**问题**: 动作空间爆炸（所有可能的 ADD/REMOVE/MODIFY 组合）。

**方案**: 解析意图描述中的关键词（"add", "remove", "modify", "difficulty" 等），只生成相关类型的动作。

**权衡**:
- ✅ 大幅减少搜索空间（从数百候选降到 <20）
- ✅ 意图与动作的关联性更强
- ⚠️ 关键词匹配是简单的字符串包含检查，可能被复杂意图误导
- 🔄 未来：使用 LLM 或 sentence embeddings 做意图→动作类型分类

---

## 7. 已知问题与限制

### 7.1 当前限制

1. **ActionSpace 的随机性**: 部分动作生成使用 `random.choice`，导致相同输入可能产生不同输出。MCTS 搜索的确定性受到影响。
   - **缓解**: 测试中使用固定种子或增加迭代次数
   - **修复计划**: 添加 `random_seed` 参数到 `ActionSpace`

2. **MCTS 搜索深度较浅**: 当前 `max_depth=10`，对于复杂修改链可能不够。
   - **缓解**: Phase 1 的场景以单步/多步局部修改为主
   - **修复计划**: Phase 2 引入分层规划（高层策略 + 低层战术）

3. **HeuristicValueFunction 质量天花板**: 基于规则启发式，无法理解深层语义（如"让游戏更像暗黑破坏神"）。
   - **缓解**: 预留了 `LLMValueFunction` 接口
   - **修复计划**: Phase 1 后期接入 LLM 做关键节点评估

4. **PlanState.apply_action 的副作用**: `apply_action` 会修改当前状态的 graph，调用方需自行 `copy()` 后再应用。
   - **缓解**: MCTS 代码中已在正确位置调用 `copy()`
   - **修复计划**: 考虑让 `apply_action` 始终返回新状态而不修改自身（函数式风格）

5. **缺少持久化**: CDLPatch 和 ContentGraph 仅在内存中操作，重启后数据丢失。
   - **缓解**: 有完整的 `to_dict()` 序列化，可轻松对接数据库
   - **修复计划**: 记忆系统 v1（Phase 1 模块 D）将实现 Neo4j + PostgreSQL 持久化

### 7.2 代码债务

1. `cdl_patch.py` 中的 `_apply_operation` 和 `_restore` 是大型 if-elif 块，未来可考虑策略模式
2. `action_space.py` 的 `_suggest_properties` 使用硬编码属性映射，应改为配置驱动
3. `mcts.py` 的 `_simulate` 使用纯随机 rollout，应改为更智能的默认策略

---

## 8. 下一步建议

### 8.1 短期（接下来 1-2 个会话）

1. **Execution Engine 脚手架** (`udify/core/execution/`)
   - MCP Server 基类
   - 工具注册与发现
   - 最简单的工具：文件读写、JSON 编辑
   - 目标：能将 CDLPatch 中的 `MODIFY_PROPERTY` 操作写入实际游戏文件

2. **端到端集成测试**
   - 从"Unity 游戏目录" → `ContentGraph` → `CDLPatch` → 文件修改的完整链路
   - 验证：修改后的游戏文件是否仍然可被感知引擎正确解析

3. **LLMValueFunction 接入**
   - 实现实际的 LLM prompt 构造和响应解析
   - A/B 测试：LLM 评估 vs 启发式评估在相同意图下的动作质量差异

### 8.2 中期（Phase 1 剩余模块）

4. **质量评估 v1** (`udify/core/validation/`)
   - Patch 的语法验证（引用完整性）
   - Patch 的语义验证（数值范围检查、依赖闭环检查）
   - 简单运行时测试：修改后的 JSON/YAML 是否合法

5. **记忆系统 v1** (`udify/core/memory/`)
   - CDLPatch 的持久化（PostgreSQL）
   - ContentGraph 的图存储（Neo4j）
   - 版本链查询（给定 patch_id 找父/子版本）

6. **前端原型 v1** (`frontend/` 或 `udify/web/`)
   - ReactFlow DAG 可视化 ContentGraph
   - Patch 的 diff 视图（类似 Git diff，但针对图结构）

### 8.3 长期决策

- **是否现在引入真实 LLM API？**
  - 建议：先完善 Execution Engine 和端到端测试，确保"修改→文件"链路可靠后再接入 LLM
  - 理由：LLM 是成本中心，在基础设施不稳定时频繁调用浪费资源

- **第一个真实游戏测试目标？**
  - 建议：RPG Maker MV 游戏（JSON 格式，易解析，社区大）
  - 场景："把主角初始 HP 从 100 改成 150" → 感知 → 规划 → 执行 → 验证

---

## 9. 文件清单

### 9.1 新增文件

| 文件 | 行数 | 说明 |
|------|------|------|
| `pyproject.toml` | ~85 | 项目配置、依赖、工具链 |
| `udify/models/cdl_patch.py` | ~350 | CDL Patch/Diff 核心模型 |
| `udify/core/planning/__init__.py` | ~20 | Planning 模块导出 |
| `udify/core/planning/state.py` | ~130 | PlanState / Intent / PlanContext |
| `udify/core/planning/action_space.py` | ~295 | ActionSpace 动作生成器 |
| `udify/core/planning/value_function.py` | ~220 | ValueFunction / HeuristicValueFunction / LLMValueFunction |
| `udify/core/planning/mcts.py` | ~270 | MCTSNode / MCTSTree |
| `udify/core/planning/planner.py` | ~180 | Planner 入口 / PlanResult |
| `tests/models/test_cdl_patch.py` | ~500 | CDL Patch 测试 |
| `tests/core/planning/test_planning.py` | ~435 | Planning Engine 测试 |

### 9.2 修改文件

| 文件 | 修改内容 |
|------|---------|
| 无 | Session 2 完全增量开发，未修改 Session 1 代码 |

### 9.3 遗留文件（Session 1）

| 文件 | 说明 |
|------|------|
| `udify/models/content_graph.py` | ContentGraph / ContentNode / ContentEdge / ContentAsset / ContentSemantics |
| `udify/core/perception/engine_detector.py` | 游戏引擎检测器 |
| `udify/core/perception/resource_extractor.py` | 资源提取器 |
| `udify/core/perception/mechanism_analyzer.py` | 机制分析器 |
| `tests/perception/test_perception.py` | 感知引擎测试（19 个） |

---

## 附录 A: 快速验证命令

```bash
# 运行全部测试
python3 -m pytest tests/ -v

# 只运行 CDL Patch 测试
python3 -m pytest tests/models/test_cdl_patch.py -v

# 只运行 Planning Engine 测试
python3 -m pytest tests/core/planning/test_planning.py -v

# 只运行 Perception 测试
python3 -m pytest tests/perception/test_perception.py -v
```

## 附录 B: 本轮贡献统计

| 指标 | 数值 |
|------|------|
| 新增 Python 文件 | 8 |
| 新增测试文件 | 2 |
| 新增 Python 代码行 | ~1,474 |
| 新增测试代码行 | ~935 |
| 测试总数 | 81 |
| 测试通过率 | 100% |
| 架构文档数 | 1（本文档） |

---

> **文档作者**: OpenCode Agent
> **会话 ID**: Session 2 (2026-04-27)
> **下一预期动作**: Execution Engine 脚手架 或 用户指定的其他方向
