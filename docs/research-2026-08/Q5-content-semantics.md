# Q5：游戏内容语义建模深度研究

## 项目背景

Udify 的核心抽象是 ContentGraph（内容语义图）和 CDLPatch（语义补丁）。当前 miu2d 适配器已实现 INI/OBJ/NPC/Lua/DSL 解析器，能从游戏文件提取角色、物品、技能、地图等节点并构建语义图。Tree-sitter Lua 已接入（函数/调用/危险 API 检测）。

但跨引擎语义建模仍是开放问题：不同游戏引擎（RPG Maker MV/MZ、Unity、Godot、Unreal、GameMaker）的数据格式完全不同，如何建立统一的语义层？ContentGraph v3 的 semantic_tags/provenance/confidence/evidence_refs 如何跨引擎复用？

## 需要深度研究的问题

1. **跨引擎语义建模**：
   - 如何为不同引擎定义统一的 ResourceProvider/EngineAdapter 接口，输出标准化的 AssetManifest
   - 从"字节→语法→语义→机制"的分层提升管线如何抽象为可复用框架
   - 语义标签体系设计：boss、quest_reward、dialog_branch、difficulty_curve 等领域标签的 ontology
   - 不同引擎的内容结构差异如何映射到统一的 ContentGraph schema

2. **AST 解析与语言服务**：
   - Tree-sitter 在多语言解析中的最佳实践（Lua、C#、GDScript、JavaScript、Python）
   - Roslyn/LSP 用于 Unity C# 语义分析的可行性与集成路径
   - 如何利用 LSP 的 references/diagnostics/code-action 减少自研引用搜索
   - Semgrep 规则化静态扫描在游戏脚本安全检查中的应用
   - 现有 miu2d DSL 命令表（218 命令）如何扩展为通用游戏 DSL schema

3. **知识图谱与语义检索**：
   - ContentGraph 在 NetworkX 上的存储与查询优化（本地模式）
   - 向量检索集成：sentence-transformers + Qdrant/ChromaDB 的本地部署方案
   - 结构检索与语义检索的融合策略（图遍历 + 向量相似度）
   - 知识图谱的增量更新（修改游戏文件后如何 delta 更新 ContentGraph）

4. **Diff/影响分析与冲突检测**：
   - 语义三方合并（base/A/B）在 Mod 组合场景下的算法选型
   - Patch 影响分析：修改一个数值如何级联检测受影响的关卡/角色/机制
   - ModStack 语义兼容矩阵：多 Mod 叠加时的冲突检测与自动解决
   - 现有 GraphDiffer 的能力边界与扩展方向

5. **运行时语义验证**：
   - Headless 运行时探针（Playwright + miu2d web build）的状态读取与报错捕获
   - 如何从运行时观测反哺 ContentGraph（runtime_observations 字段）
   - 意图对齐评估：修改后的游戏是否真正满足用户意图（"更难了但不是单纯堆血量"）
   - RL/Game AI 自动试玩评估的可行性（Gymnasium/PettingZoo 在游戏测试中的应用）

## 交付物

- 跨引擎 EngineAdapter 统一接口设计（含 ResourceProvider 协议、AssetManifest schema）
- Tree-sitter 多语言解析框架选型与集成路径
- 知识图谱 + 向量检索的本地部署方案（具体库与配置）
- 语义三方合并算法选型与 ModStack 兼容矩阵设计
- 运行时验证体系的成熟开源组件推荐（Playwright、RL 框架）
- 每个结论需包含：开源选型、集成路径、对现有代码的改动评估

## 约束

- 优先使用成熟开源（AssetRipper、Tree-sitter、NetworkX、Playwright 已在调研中列出）
- 自研只做语义提升、意图接地、语义 Patch、自动验证（Udify 护城河）
- 本地优先：NetworkX/SQLite/文件缓存起步，Neo4j/Qdrant 是 P2 升级
- Python 3.12+ / mypy strict 兼容
- 不自研已有成熟工具的解析器（如 AssetRipper 做 Unity 资源提取）
