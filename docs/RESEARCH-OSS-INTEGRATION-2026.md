<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 开源生态集成调研 2026

> 面向工程落地的技术选型报告。目标不是证明 Udify 可以从零做完一切，而是明确哪些能力应该直接集成开源项目，哪些能力只借鉴模式，哪些能力必须成为 Udify 的自研突破。

---

## 0. 结论先行

Udify 的原始动机是降低内容魔改门槛：用户表达意图，系统完成感知、规划、执行、验证和反馈。这个动机在开源生态调研后更加明确：绝大多数基础工具已经存在，真正缺口不在“能不能提取资源”，而在“能不能把资源、脚本、机制、用户意图和 Mod 兼容性提升到同一个可验证的语义层”。

因此，Udify 后续架构应遵循三条硬原则：

1. **工具能集成就不重写**：资源提取、AST 解析、浏览器验证、LLM 编排、图算法、静态扫描、供应链签名都已有成熟框架。
2. **核心只做语义和闭环**：ContentGraph/CDL Patch、意图接地、计划搜索、语义冲突合并、自动试玩评估、反馈学习是 Udify 的护城河。
3. **所有外部工具必须通过安全网关进入**：MCP 或 Tool Registry 只提供能力发现，不等于信任边界。Udify 需要签名、权限、沙箱、审计和回放。

推荐形成新的技术分工：

| 层 | 应该集成 | Udify 自研核心 |
|---|---|---|
| 资源提取 | AssetRipper, FModel/CUE4Parse, QuickBMS, UndertaleModTool, miu2d converter | 引擎适配器协议、资源血缘、资源语义标签 |
| 代码/脚本解析 | Tree-sitter, Roslyn, Language Server Protocol, luaparser | 跨语言脚本 IR、游戏事件语义图 |
| 工作流 | Temporal/LangGraph/Prefect 分层使用 | ModJob 状态机、可回放执行日志、人工确认点 |
| 工具调用 | MCP SDK/FastMCP, Tool Registry | Secure Tool Gateway, OPA 策略, capability manifest |
| 图和检索 | NetworkX, Neo4j GDS, Qdrant, sentence-transformers | ContentGraph v3 schema, 结构检索和语义检索融合 |
| 验证 | Playwright, Semgrep, Inspect AI, Ragas, Gymnasium/PettingZoo | Game Runtime Probe, Intent Alignment, Mod Quality Score |
| Mod 生态 | Modrinth API, Prism Launcher, Vortex/MO2 模式 | ModStack 语义兼容矩阵、Patch Marketplace、模板进化 |

---

## 1. 与项目初心的对齐

### 1.1 最初期动机

从 `VISION.md`、`PLAN.md` 和 `ARCHITECTURE-v2.md` 可以归纳出 Udify 的三个原始命题：

1. **创作是变换，不是生成**  
   系统应保存原始内容和变换路径，输出 Patch，而不是黑箱生成一个新文件。

2. **意图比技术更重要**  
   用户说“像魂系一样更硬核”，工程系统需要把它落到难度曲线、资源消耗、死亡惩罚、Boss 行为、UI 反馈等可执行目标。

3. **生态即产品**  
   Udify Core 没有 Udiface 只是一套工具；Udiface 没有 Core 只是托管平台。真正价值来自创作、分发、反馈、再演化闭环。

### 1.2 调研后的架构校准

现有 v2 架构的方向正确，但需要重新校准几个点：

| 现有方向 | 调研后的判断 | 建议 |
|---|---|---|
| Prefect 作为工作流引擎 | Prefect 适合数据流和可视化批处理，但长事务、人工确认、幂等补偿更像 durable execution | 引入 Temporal 作为生产级 ModJob 引擎，Prefect 保留给离线分析和实验管线 |
| MCP 作为工具接口 | MCP 生态价值高，但工具调用扩大了攻击面 | 增加 Secure Tool Gateway，MCP manifest 不直接等于授权 |
| MCTS + LLM 规划 | 适合开放式探索，但不应承载所有计划生成 | 拆成规则约束生成、启发式搜索、LLM 价值评估、人工确认四段 |
| Neo4j 作为图存储 | 大图查询适合 Neo4j，但本地 MVP 不应过早绑定服务依赖 | 本地 NetworkX/SQLite 起步，生产 Neo4j/Qdrant 双索引 |
| 游戏引擎解析器自研 | 自研所有解析器风险过高 | miu2d 自研深做，Unity/Unreal/RPG Maker/Godot 优先接开源工具和脚本 |

---

## 2. 开源生态地图

### 2.1 游戏资源提取与逆向

| 项目 | 能力 | 适配价值 | Udify 集成方式 |
|---|---|---|---|
| [AssetRipper](https://github.com/AssetRipper/AssetRipper) | Unity 资源、场景和脚本结构导出 | Unity 首选资源感知入口 | CLI/库封装为 UnityAssetExtractor |
| [AssetStudio](https://github.com/Perfare/AssetStudio) | Unity 资产浏览和导出 | 补充 AssetRipper，对老版本 Unity 有价值 | 作为降级工具 |
| [FModel](https://github.com/4sval/FModel) | Unreal pak/utoc/ucas 资源浏览 | Unreal 资源提取和蓝图探索入口 | CLI 自动化 + 输出清单解析 |
| [CUE4Parse](https://github.com/FabianFG/CUE4Parse) | Unreal 资源解析库 | 比 GUI 工具更适合服务端集成 | 长期封装为 UnrealResourceProvider |
| [UE Viewer / umodel](https://www.gildor.org/en/projects/umodel) | Unreal 模型和贴图查看导出 | 社区成熟，覆盖大量 UE 游戏 | 外部工具适配 |
| [QuickBMS](https://aluigi.altervista.org/quickbms.htm) | 大量游戏归档格式脚本化解包 | 处理非主流私有包格式 | 作为 ArchiveProbe 和 ExtractTool |
| [UndertaleModTool](https://github.com/UnderminersTeam/UndertaleModTool) | GameMaker/Undertale 类项目资源和脚本编辑 | 证明单引擎深度工具模式 | 借鉴 UI 和反编译管线 |
| miu2d converter | miu2d 二进制格式转换 | 首攻目标，最可控 | 作为一等公民 Tool Adapter |

工程结论：

- Unity/Unreal 的资源提取已被开源生态基本解决，Udify 不应在 Phase 1 重新发明。
- Udify 应该定义统一 `ResourceProvider` 接口，把不同工具输出标准化为 `AssetManifest + SourceLocation + Confidence + LicenseHint`。
- 真正难点是“资源提取后如何理解其机制意义”，例如一个贴图是 UI 图标、技能特效、剧情 CG，还是某个任务状态反馈。

### 2.2 Mod Loader 与运行时注入

| 项目 | 能力 | 对 Udify 的启示 |
|---|---|---|
| [BepInEx](https://github.com/BepInEx/BepInEx) | Unity/.NET 游戏插件加载和运行时 Hook | 对 Unity Mod 应优先生成插件而非直接改原包 |
| [Harmony](https://github.com/pardeike/Harmony) | .NET 方法 Patch | 可将“修改机制”表达为运行时补丁 |
| [Reloaded-II](https://github.com/Reloaded-Project/Reloaded-II) | 通用 Mod Loader 框架 | 借鉴 profile、依赖、加载顺序、冲突处理 |
| [MelonLoader](https://github.com/LavaGang/MelonLoader) | Unity Mod Loader | Unity 游戏的另一路径 |
| [Mod Organizer 2](https://github.com/ModOrganizer2/modorganizer) | 虚拟文件系统式 Mod 管理 | VFS 预览和 ModStack 冲突处理的重要参考 |
| [Vortex](https://github.com/Nexus-Mods/Vortex) | Nexus Mods 官方 Mod 管理器 | 用户侧安装、规则、冲突 UI 的参考 |

工程结论：

- Mod 修改有两种执行形态：**离线文件 Patch** 和 **运行时 Hook**。Udify 当前偏离线 Patch，后续应将 Hook 作为 Unity/.NET 的重要动作类型。
- `CDLPatch` 应扩展 `operation_runtime` 分支，描述 Harmony patch、BepInEx plugin、Lua hook、Godot autoload 等运行时注入。
- VFS 不是只用于预览，也是 ModStack 组合和冲突检测的核心模型。

### 2.3 解析器、语言服务与语义索引

| 项目 | 能力 | 集成建议 |
|---|---|---|
| [Tree-sitter](https://tree-sitter.github.io/tree-sitter/) | 增量解析和 query | 脚本、配置和 DSL 的基础 AST 入口 |
| [Roslyn](https://learn.microsoft.com/en-us/dotnet/csharp/roslyn-sdk/) | C# 编译器平台和语义模型 | Unity C# 插件、反编译代码分析必需 |
| [Language Server Protocol](https://microsoft.github.io/language-server-protocol/) | 语言能力标准化 | 统一 rename、references、diagnostics、code action |
| [Semgrep](https://semgrep.dev/docs/) | 规则化静态扫描 | 安全和游戏脚本规则检查 |
| [NetworkX](https://networkx.org/documentation/stable/) | Python 图算法 | 本地 ContentGraph 分析 |
| [Neo4j Graph Data Science](https://neo4j.com/docs/graph-data-science/current/) | 图算法和图嵌入 | 生产级关系查询和推荐 |

工程结论：

- Udify 感知层必须采用“字节到语法到语义到机制”的分层提升，不允许 LLM 直接从原始文件猜语义。
- `SourceLocation` 需要升级为 `SourceSpan`，覆盖文件、字节偏移、行列、AST 节点路径、工具版本、置信度。
- 语言服务能力可以减少自研成本，例如 references 用 LSP，不要每种语言自己写引用搜索。

### 2.4 Agent、工作流与工具协议

| 项目 | 能力 | 集成建议 |
|---|---|---|
| [LangGraph](https://langchain-ai.github.io/langgraph/) | 状态图、人类在环、持久化 Agent 流程 | 适合 Intent Compiler、Plan Critic、Review Agent |
| [Temporal](https://temporal.io/) | Durable execution、重试、补偿、长事务 | 适合生产级 ModJob |
| [Prefect](https://docs.prefect.io/) | Python 数据工作流、可视化任务编排 | 适合离线感知、批量评估和数据集构建 |
| [Dagster](https://docs.dagster.io/) | asset-oriented data orchestration | 适合数据资产血缘，但不是首选执行内核 |
| [MCP](https://modelcontextprotocol.io/) | 工具、资源、提示模板协议 | 作为工具能力标准入口 |
| [FastMCP](https://gofastmcp.com/) | Python MCP Server 快速构建 | 加速内部工具服务化 |

工程结论：

- Agent 逻辑和业务工作流要分离。LangGraph 管“推理状态”，Temporal 管“副作用状态”。
- MCP 只负责工具协议，不负责权限。每次工具调用前都必须经过 `PolicyDecision`。
- 人类确认点要变成架构对象，而不是 UI 逻辑。计划、风险高的 Patch、版权不确定资产、运行时注入都需要 confirmation gate。

### 2.5 验证、评测与自动试玩

| 项目 | 能力 | 集成建议 |
|---|---|---|
| [Playwright](https://playwright.dev/) | 浏览器自动化和端到端测试 | miu2d 和 Web 游戏运行时验证首选 |
| [Gymnasium](https://gymnasium.farama.org/) | RL 环境接口 | 抽象自动试玩环境 |
| [PettingZoo](https://pettingzoo.farama.org/) | 多智能体 RL 环境 | 多角色或多人机制验证参考 |
| [Godot RL Agents](https://github.com/edbeeching/godot_rl_agents) | Godot 与 RL 连接 | Godot 自动试玩方向 |
| [Inspect AI](https://inspect.aisi.org.uk/) | LLM eval 框架 | 评测 Intent Compiler、Plan Critic |
| [Ragas](https://docs.ragas.io/) | RAG 评估 | 知识检索和引用质量评测 |
| [DeepEval](https://docs.confident-ai.com/) | LLM 单元测试和指标 | Agent 输出回归测试 |
| [OpenAI Evals](https://github.com/openai/evals) | LLM 评测基准框架 | 构建 Udify 领域 benchmark |

工程结论：

- Udify 需要两套评估：**工程正确性** 和 **意图对齐质量**。前者可确定，后者概率化。
- 自动试玩不是一开始追求“通关智能体”，而是先做探针：启动、载入、进入战斗、读取数值、触发任务、保存退出。
- `IntentAlignmentEvaluator` 应升级为可回归的评测套件，每个 benchmark 包含原始游戏、意图、期望 patch pattern、禁止修改范围和运行时探针。

### 2.6 向量检索、知识和记忆

| 项目 | 能力 | 集成建议 |
|---|---|---|
| [Qdrant](https://qdrant.tech/documentation/) | 开源向量数据库 | 本地和云端语义索引 |
| [sentence-transformers](https://www.sbert.net/) | 本地 embedding | 降低成本、支持隐私模式 |
| [LlamaIndex](https://docs.llamaindex.ai/) | 文档和图谱 RAG | 知识库原型可借鉴 |
| [Haystack](https://docs.haystack.deepset.ai/) | RAG pipeline | 可用于知识检索实验 |

工程结论：

- 记忆系统不能只存用户偏好向量，也要存“成功 Patch 模式”和“失败原因”。
- 检索结果必须携带证据链，不允许只返回相似文本。每个建议都要能回溯到 Mod、文件、节点、历史评估结果。

### 2.7 安全、策略和供应链

| 项目 | 能力 | 集成建议 |
|---|---|---|
| [Open Policy Agent](https://www.openpolicyagent.org/docs/latest/) | 通用策略引擎 | 工具调用、文件访问、发布权限 |
| [Sigstore/cosign](https://docs.sigstore.dev/cosign/) | artifact 签名和验证 | Tool Adapter、ModPackage、发布包签名 |
| [Syft](https://github.com/anchore/syft) | SBOM 生成 | 外部工具和发布包物料清单 |
| [Grype](https://github.com/anchore/grype) | 漏洞扫描 | Toolchain 和容器镜像扫描 |
| [gVisor](https://gvisor.dev/docs/) | 容器沙箱运行时 | 高风险脚本和工具执行 |
| [Firecracker](https://firecracker-microvm.github.io/) | microVM | 更强隔离的未来选项 |

工程结论：

- 供应链安全不应等平台期再做。Udify 的核心风险来自外部工具、用户上传文件和 AI 生成脚本。
- 每个 Tool Adapter 必须有 `tool_id`、版本、哈希、签名状态、允许读写目录、网络权限、资源限额和审计日志。

---

## 3. 需要直接集成的技术清单

### 3.1 Phase 1 立即集成

| 优先级 | 技术 | 目的 | 验收标准 |
|---|---|---|---|
| P0 | Tree-sitter Lua | 替换弱 Lua 解析 | 能输出 AST、函数、调用、SourceSpan |
| P0 | Playwright | miu2d 运行时验证 | 能启动样例游戏并读取核心状态 |
| P0 | NetworkX | 本地图分析 | 能计算依赖子图、影响范围、冲突候选 |
| P0 | Semgrep 或自定义规则引擎 | 脚本安全规则 | 能拒绝文件/网络/危险 API |
| P0 | MCP Python SDK/FastMCP | 内部工具协议 | Tool Registry 可以发布 schema |
| P1 | Qdrant 或 SQLite 向量插件 | 语义检索 | 可按意图找历史 Patch 模式 |
| P1 | AssetRipper/AssetStudio 适配器 | Unity 入口 | 能产生标准 AssetManifest |
| P1 | QuickBMS 适配器 | 归档解包入口 | 能运行 allowlist 脚本并记录血缘 |

### 3.2 Phase 2 集成

| 技术 | 目的 |
|---|---|
| Temporal | 生产级长任务、重试、补偿、人工确认 |
| OPA | 统一工具调用策略 |
| Sigstore/cosign | 工具和 Mod 包签名 |
| FModel/CUE4Parse | Unreal 感知适配 |
| BepInEx/Harmony | Unity 运行时 Hook Patch |
| Inspect AI/Ragas/DeepEval | Udify benchmark 和 LLM 回归评测 |

### 3.3 Phase 3 集成

| 技术 | 目的 |
|---|---|
| Neo4j GDS | 平台级图谱和推荐 |
| Modrinth API/Prism 模式 | Modpack、依赖、分发生态参考 |
| Yjs | 多人协作编辑 |
| Firecracker | 高风险用户代码强隔离 |

---

## 4. 必须自研突破的算法

### A1. 游戏语义提升算法

输入是资源、配置、脚本、运行时 trace，输出是 `GameWorldGraph` 中的机制节点和关系。

关键难点：

- 同一个概念散落在多个文件，例如 Boss 血量在配置，行为在脚本，掉落在表格，视觉反馈在资源。
- 文件名和变量名经常没有语义，尤其是商业游戏。
- LLM 可以猜含义，但必须给出置信度和证据。

建议路线：

1. 规则和 schema 先行：miu2d/RPG Maker MV 等结构化引擎优先。
2. 图模式挖掘：用共现、引用、调用链、资源加载链发现候选语义。
3. LLM 只做标签提议：模型输出 `label + evidence + confidence`，不能直接写入核心图。
4. 运行时 trace 校准：通过启动游戏、触发行为、读取状态校验语义。

### A2. 意图接地与约束分解算法

输入自然语言，输出可规划的目标集合。

例如“让游戏像魂系一样更难，但不要数值膨胀”应拆成：

- 增加惩罚，而不是简单 HP 翻倍。
- 提升敌人行为和资源管理压力。
- 保持可通关，不破坏新手村。
- 修改范围限制在战斗、恢复、死亡、Boss 行为。

突破点：

- 从审美词汇映射到系统参数。
- 识别负约束和用户不想要的实现路径。
- 给每个目标附 `acceptance_probe`，否则无法验证。

### A3. 语义 Patch 合成与三路合并

传统文本 diff 无法理解 Mod 之间的语义冲突。Udify 需要在 ContentGraph/CDL 层做合并。

核心能力：

- Source-aware 三路合并：base graph、mod A overlay、mod B overlay。
- Conflict taxonomy：同属性冲突、引用冲突、机制冲突、体验冲突、资源覆盖冲突、加载顺序冲突。
- 自动解决策略：数值可组合、列表可合并、脚本 hook 可排序、互斥机制需人工确认。

### A4. 计划搜索的成本约束算法

MCTS 不能无边界展开。规划要同时优化质量、成本、风险和可解释性。

建议目标函数：

```text
score(plan) =
  intent_alignment * 0.35
  + static_validity * 0.20
  + runtime_probe_coverage * 0.15
  + reversibility * 0.10
  + user_preference_match * 0.10
  + novelty * 0.05
  - cost_penalty * 0.05
  - risk_penalty
```

### A5. 自动试玩探针生成

目标不是做通用游戏 AI，而是从 Patch 影响范围生成最小验证脚本。

示例：

- 修改 Boss HP：启动游戏，进入战斗场景，读取 Boss 实际 HP，验证战斗循环没有报错。
- 修改任务奖励：触发任务完成事件，读取背包和经验。
- 修改地图障碍：计算可达性，运行角色从入口到出口。

关键突破：

- 从影响子图生成 probe。
- 失败时定位根因，而不是只报告“游戏崩溃”。

### A6. Mod 质量评分和反馈学习

质量评分需要结合静态、动态、用户和生态指标。

候选指标：

- 结构正确性：解析、引用、格式、幂等。
- 运行正确性：启动、加载、核心 probe。
- 意图对齐：目标达成、约束满足、范围控制。
- 兼容性：与高频 ModStack 的冲突率。
- 社区反馈：评分、留存、回滚率、崩溃报告。

---

## 5. 新增盲点清单

在 v1.1 的 47 个盲点之外，本次调研补充 24 个工程盲点：

| 编号 | 盲点 | 风险 | 建议 |
|---|---|---|---|
| N1 | 外部工具输出格式不稳定 | 适配器频繁失效 | Tool Adapter contract test |
| N2 | GUI 工具难以服务端自动化 | 集成成本高 | 优先选择 CLI/库，GUI 工具只做兜底 |
| N3 | QuickBMS 脚本来源不可控 | 供应链和版权风险 | allowlist、hash pin、沙箱 |
| N4 | MCP 工具权限过宽 | prompt injection 触发危险工具 | OPA policy + per-call confirmation |
| N5 | LLM 评估自证循环 | 生成和评估同源偏差 | 规则、运行时 probe、人评混合 |
| N6 | 运行时 Hook 与离线 Patch 语义不同 | 同一意图多执行形态冲突 | Patch operation 增加 execution_mode |
| N7 | Mod Loader 生态碎片化 | Unity 不同 loader 不兼容 | RuntimeAdapter 分层 |
| N8 | License/版权状态缺失 | 平台发布风险 | LicenseHint + PolicyGate |
| N9 | 用户上传游戏含隐私和 secret | 数据泄露 | Secret scanner + 本地优先模式 |
| N10 | 评测数据集缺失 | 无法判断模型迭代是否变好 | 建立 UdifyBench |
| N11 | 自动试玩可重复性差 | flakey 验证 | 固定随机种子、状态快照、probe 重试 |
| N12 | 大型游戏图谱过大 | 内存和查询性能问题 | 子图懒加载、冷热分层 |
| N13 | 社区模板污染 | 低质模板被复用 | 模板评分、隔离和回滚 |
| N14 | 人类确认点过多 | 自动化体验变差 | risk-based confirmation |
| N15 | 人类确认点过少 | 错误修改和安全问题 | hard gate for high risk |
| N16 | 语义标签不可审计 | 用户不信任 | evidence-first labeling |
| N17 | 工具版本漂移 | 结果不可复现 | tool lockfile |
| N18 | Patch 无法跨游戏版本迁移 | 用户体验差 | semantic anchor + migration planner |
| N19 | 多语言社区输入 | 中文/英文/日文 Mod 语义不同 | multilingual intent/entity pipeline |
| N20 | 游戏更新破坏 Mod | 维护成本高 | compatibility CI |
| N21 | 可观测性缺口 | 失败难诊断 | trace_id 贯穿每个 patch op |
| N22 | 本地和云端能力分裂 | 开发复杂 | capability negotiation |
| N23 | 内容审核缺少上下文 | 误杀二创 | policy reason + appeal workflow |
| N24 | 平台激励扭曲 | 模板为评分优化而非质量 | 多指标反作弊 |

---

## 6. 参考资料

### 官方文档和项目

- Tree-sitter: <https://tree-sitter.github.io/tree-sitter/>
- Roslyn SDK: <https://learn.microsoft.com/en-us/dotnet/csharp/roslyn-sdk/>
- Language Server Protocol: <https://microsoft.github.io/language-server-protocol/>
- Model Context Protocol: <https://modelcontextprotocol.io/>
- FastMCP: <https://gofastmcp.com/>
- LangGraph: <https://langchain-ai.github.io/langgraph/>
- Temporal: <https://temporal.io/>
- Prefect: <https://docs.prefect.io/>
- Playwright: <https://playwright.dev/>
- Gymnasium: <https://gymnasium.farama.org/>
- PettingZoo: <https://pettingzoo.farama.org/>
- Inspect AI: <https://inspect.aisi.org.uk/>
- Ragas: <https://docs.ragas.io/>
- DeepEval: <https://docs.confident-ai.com/>
- NetworkX: <https://networkx.org/documentation/stable/>
- Neo4j Graph Data Science: <https://neo4j.com/docs/graph-data-science/current/>
- Qdrant: <https://qdrant.tech/documentation/>
- Open Policy Agent: <https://www.openpolicyagent.org/docs/latest/>
- Sigstore cosign: <https://docs.sigstore.dev/cosign/>
- gVisor: <https://gvisor.dev/docs/>

### 游戏和 Mod 工具

- AssetRipper: <https://github.com/AssetRipper/AssetRipper>
- AssetStudio: <https://github.com/Perfare/AssetStudio>
- FModel: <https://github.com/4sval/FModel>
- CUE4Parse: <https://github.com/FabianFG/CUE4Parse>
- UE Viewer: <https://www.gildor.org/en/projects/umodel>
- QuickBMS: <https://aluigi.altervista.org/quickbms.htm>
- UndertaleModTool: <https://github.com/UnderminersTeam/UndertaleModTool>
- BepInEx: <https://github.com/BepInEx/BepInEx>
- Harmony: <https://github.com/pardeike/Harmony>
- Reloaded-II: <https://github.com/Reloaded-Project/Reloaded-II>
- Mod Organizer 2: <https://github.com/ModOrganizer2/modorganizer>
- Vortex: <https://github.com/Nexus-Mods/Vortex>
- Modrinth API: <https://docs.modrinth.com/api/>
- Prism Launcher: <https://github.com/PrismLauncher/PrismLauncher>
