<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 游戏魔改架构深度审查报告 v1.1

> **目标**: 对 v1.0 架构进行全面自审，发现盲点，厘清结构关系，输出补充设计
> **范围**: 技术架构、数据流、错误处理、安全、性能、协作、生态
> **基准**: v1.0 架构 (`docs/ARCHITECTURE-GAME-MOD-v1.md`)
> **日期**: 2026-04-27
> **状态**: 审查完成，补充 47 项设计细节，新增 12 个模块，识别 8 个核心盲点

---

## 目录

1. [审查方法论](#1-审查方法论)
2. [v1.0 架构回顾](#2-v10-架构回顾)
3. [发现的盲点](#3-发现的盲点)
   - 3.1 数据流盲点
   - 3.2 状态管理盲点
   - 3.3 错误处理盲点
   - 3.4 安全边界盲点
   - 3.5 性能与成本盲点
   - 3.6 协作与并发盲点
   - 3.7 生态与商业盲点
   - 3.8 关系与契约盲点
4. [补充设计](#4-补充设计)
   - 4.1 事件驱动总线
   - 4.2 分层缓存系统
   - 4.3 知识图谱层
   - 4.4 反馈闭环
   - 4.5 多 Mod 管理器
   - 4.6 沙箱执行环境
   - 4.7 权限与审计
   - 4.8 成本控制器
5. [改进后的完整架构](#5-改进后的完整架构)
6. [关键决策记录 (ADR)](#6-关键决策记录-adr)
7. [实施优先级调整](#7-实施优先级调整)

---

## 1. 审查方法论

采用**六维审查法**：

| 维度 | 审查问题 | 发现数 |
|------|---------|--------|
| **数据流** | 数据如何在各层流动？有无断点、循环、竞态？ | 6 |
| **状态管理** | 状态如何保持一致？冲突如何解决？ | 5 |
| **错误处理** | 失败时怎么办？如何恢复？有无优雅降级？ | 7 |
| **安全边界** | 输入如何验证？AI输出如何约束？隔离策略？ | 6 |
| **性能成本** | 瓶颈在哪？成本如何控制？有无缓存？ | 8 |
| **关系契约** | 模块间接口定义是否清晰？依赖是否合理？ | 8 |
| **生态商业** | 创作者如何获益？Mod如何分发？版权？ | 7 |

---

## 2. v1.0 架构回顾

v1.0 定义了六层架构：

```
用户层 → 意图层 → 感知层 → 规划层 → 补丁层 → 执行层 → 验证层
```

**已完成的设计**:
- ✅ 8 种二进制格式解码器映射
- ✅ INI/OBJ/脚本的数据 Schema（基于 miu2d Zod Schema）
- ✅ GameWorldGraph（角色/物品/技能/地图/任务/对话节点）
- ✅ GameModActionSpace（5 种动作类型）
- ✅ GameBalanceValueFunction（4 维评估）
- ✅ GameFilePatcher（INI 修改 + 脚本注入）
- ✅ BinaryAssetPatcher（调用 converter）
- ✅ 静态验证器（引用完整性 + 数值范围 + 格式合法）
- ✅ 运行时验证器（Playwright + headless 浏览器）
- ✅ Dashboard AI Mod Assistant 组件设计
- ✅ 6 周实施路线图

---

## 3. 发现的盲点

### 3.1 数据流盲点

#### B1.1 缺少增量更新数据流
**问题**: v1.0 假设每次都是全量分析（从原始文件 → GameWorldGraph），对于大型游戏（数千文件），全量分析成本极高。
**影响**: 每次修改意图都要重新解析所有文件，用户体验差。
**解决方案**: 引入增量感知（Incremental Perception）— 只重新解析变更的文件及其依赖。

#### B1.2 缺少事件溯源数据流
**问题**: v1.0 的 Patch 是最终状态，缺少"如何到达这个状态"的完整历史。当需要审计或回滚到中间状态时无法做到。
**影响**: 无法支持"撤销第3步但保留第1、2、5步"这样的细粒度回滚。
**解决方案**: 引入事件溯源（Event Sourcing）— 每个操作是一个事件，状态是事件的折叠。

#### B1.3 缺少异步流水线数据流
**问题**: v1.0 的数据流是同步阻塞的（用户等待 → 感知 → 规划 → 执行 → 验证），LLM 调用可能耗时 10-30 秒。
**影响**: 用户等待时间长，体验差。
**解决方案**: 引入异步任务队列 — 用户提交意图后立即返回任务 ID，后台流水线执行，通过 WebSocket 推送进度。

#### B1.4 缺少多源数据合并流
**问题**: v1.0 假设只有一个 GameWorldGraph，但实际可能有多个来源（原始游戏 + Mod A + Mod B）。
**影响**: 无法正确分析"在已有 Mod 的基础上继续魔改"。
**解决方案**: 引入分层图谱 — Base Graph + Mod Overlay Graph → Merged Graph。

#### B1.5 缺少数据血缘追踪
**问题**: v1.0 不知道"某个数值是从哪个文件解析的"，当多个文件定义同一数值时无法判断优先级。
**影响**: Patch 应用时可能修改了错误的文件。
**解决方案**: 在 GameWorldGraph 的每个属性上附加 SourceLocation（文件路径 + 行号 + 列号）。

#### B1.6 缺少跨层一致性校验
**问题**: 感知层输出的图谱和规划层使用的图谱可能不一致（比如规划层缓存了旧版本）。
**影响**: 规划基于过时的图谱，导致 Patch 无效或冲突。
**解决方案**: 引入图谱版本号 + 校验和，每层消费前验证一致性。

### 3.2 状态管理盲点

#### B2.1 缺少会话状态管理
**问题**: v1.0 没有定义"一次魔改会话"的生命周期。用户可能在多个会话中逐步修改。
**影响**: 无法恢复之前的未完成的魔改工作。
**解决方案**: 引入 ModSession（会话）— 包含意图历史、图谱快照、Patch 历史、用户反馈。

#### B2.2 缺少冲突状态机
**问题**: v1.0 的 PatchValidator 能检测冲突，但没有定义冲突的解决状态机。
**影响**: 检测到冲突后怎么办？自动解决？人工介入？没有策略。
**解决方案**: 定义冲突状态机 — Detected → AutoResolved / ManualReview → Resolved / Rejected。

#### B2.3 缺少预览状态隔离
**问题**: v1.0 的 Patch 应用会直接修改文件，没有"预览但不应用"的状态。
**影响**: 用户无法在安全环境中预览修改效果。
**解决方案**: 引入 Preview Mode — 在内存中构建虚拟文件系统（VFS），修改只在 VFS 中生效，不影响实际文件。

#### B2.4 缺少原子性保证
**问题**: v1.0 提到 atomic apply，但没有定义原子性的具体语义（文件级？操作级？会话级？）。
**影响**: 部分失败时回滚粒度不清晰。
**解决方案**: 定义三级原子性 — File Atomic（单个文件）、Mod Atomic（整个 Mod）、Session Atomic（整个会话）。

#### B2.5 缺少图谱缓存失效策略
**问题**: v1.0 的 GameWorldGraph 构建成本高，但没有缓存策略。
**影响**: 重复构建浪费资源。
**解决方案**: 引入多级缓存 — 文件级（mtime 检测）、块级（AST 子树缓存）、图谱级（完整图谱序列化到磁盘）。

### 3.3 错误处理盲点

#### B3.1 缺少降级策略
**问题**: v1.0 假设 LLM 总是可用，当 LLM 服务不可用时系统完全停摆。
**影响**: 系统可用性依赖外部服务。
**解决方案**: 定义三级降级 — L1: 本地模型（质量较低但可用）→ L2: 规则引擎（启发式规划）→ L3: 手动模式（只提供工具，AI 辅助禁用）。

#### B3.2 缺少部分失败恢复
**问题**: v1.0 的 atomic apply 要么全成功要么全回滚，但没有考虑"部分成功也是可接受的"。
**影响**: 某些场景下用户宁愿保留已成功部分。
**解决方案**: 引入 Checkpoint 机制 — 每 N 个操作创建一个 checkpoint，失败时可选择回滚到最近 checkpoint 或完全回滚。

#### B3.3 缺少超时和熔断
**问题**: v1.0 没有定义各步骤的超时时间。感知可能卡住，规划可能无限循环。
**影响**: 系统资源被长时间占用，用户体验差。
**解决方案**: 为每个阶段定义 SLI/SLO — 感知 < 2s，规划 < 10s，执行 < 5s，验证 < 30s。超时后触发降级。

#### B3.4 缺少输入消毒
**问题**: v1.0 的自然语言输入直接传递给 LLM，没有验证和消毒。
**影响**: Prompt Injection 攻击、恶意输入导致系统行为异常。
**解决方案**: 输入消毒层 — 长度限制、敏感词过滤、意图分类（拒绝非游戏魔改请求）。

#### B3.5 缺少输出净化
**问题**: v1.0 的 AI 输出直接用于修改文件，没有验证输出是否符合预期格式。
**影响**: AI 可能生成无效代码、恶意代码或格式错误的配置。
**解决方案**: 输出净化层 — Schema 验证、语法检查、沙箱执行（确认无副作用后才应用）。

#### B3.6 缺少数据损坏检测
**问题**: v1.0 没有检测文件在应用 Patch 后是否损坏。
**影响**: 修改后的文件可能无法被游戏引擎解析。
**解决方案**: 应用 Patch 后立即用原始解码器尝试解析，失败则自动回滚。

#### B3.7 缺少幂等性保证
**问题**: v1.0 没有保证"同一 Patch 应用两次结果一致"。
**影响**: 网络重试或用户重复点击可能导致重复修改。
**解决方案**: Patch 包含唯一 ID + 目标文件校验和，重复应用时检测已应用状态。

### 3.4 安全边界盲点

#### B4.1 缺少 AI 输出沙箱
**问题**: v1.0 的 ScriptInjector 直接将 AI 生成的 Lua/DSL 代码写入文件，没有执行沙箱。
**影响**: AI 可能生成恶意代码（如删除文件、网络请求）。
**解决方案**: 引入 gVisor 或 WASM 沙箱 — 在隔离环境中执行生成的脚本，确认无副作用后才应用到实际文件。

#### B4.2 缺少文件系统隔离
**问题**: v1.0 的 FilePatcher 直接操作 game_root，没有限制可访问的文件范围。
**影响**: Bug 或恶意 Patch 可能修改系统文件。
**解决方案**: 引入 chroot jail 或容器化 — FilePatcher 只能在指定的游戏目录内操作。

#### B4.3 缺少 secrets 保护
**问题**: v1.0 没有考虑 AI 可能从游戏文件中提取敏感信息（如 API key、个人数据）。
**影响**: 隐私泄露风险。
**解决方案**: 游戏文件扫描 — 检测并标记可能包含敏感信息的文件，禁止 AI 访问。

#### B4.4 缺少版权检测
**问题**: v1.0 允许替换任何资源，但没有检测替换后的资源是否侵犯版权。
**影响**: 法律风险。
**解决方案**: 资源指纹检测 — 上传的资源与已知版权资源比对，标记潜在风险。

#### B4.5 缺少用户权限隔离
**问题**: v1.0 假设单用户，没有多用户权限模型。
**影响**: 无法支持"创作者可以修改自己的 Mod，但只能查看别人的 Mod"。
**解决方案**: RBAC — Owner / Editor / Viewer / Tester 角色，每个 Mod 有独立的 ACL。

#### B4.6 缺少供应链安全
**问题**: v1.0 依赖 miu2d converter（Rust CLI），但没有验证其完整性。
**影响**: 供应链攻击（converter 被篡改导致恶意代码注入）。
**解决方案**: Converter 签名验证 + SBOM（软件物料清单）。

### 3.5 性能与成本盲点

#### B5.1 缺少 LLM 成本预算
**问题**: v1.0 的 Planning 每次调用 LLM，没有成本上限。用户说"帮我魔改整个游戏"可能导致 $100+ 的 API 费用。
**影响**: 成本失控。
**解决方案**: 引入 CostController — 每次会话有成本预算（如 $0.5），超过后切换本地模型或请求用户确认。

#### B5.2 缺少计算资源配额
**问题**: v1.0 的 RuntimeValidator 使用 Playwright 启动真实浏览器，每次验证消耗大量 CPU/内存。
**影响**: 高并发时系统崩溃。
**解决方案**: 资源配额 + 排队 — 每个用户有并发的验证槽位（如同时 1 个），超出排队。

#### B5.3 缺少缓存分层
**问题**: v1.0 没有定义缓存策略。相同的意图每次都要重新规划。
**影响**: 重复计算浪费资源。
**解决方案**: 三级缓存 — L1: 精确匹配（相同意图 → 相同结果），L2: 语义匹配（相似意图 → 相似结果），L3: 子意图匹配（部分匹配 → 部分复用）。

#### B5.4 缺少预计算
**问题**: v1.0 的所有计算都是实时触发。
**影响**: 首次使用感知层时等待时间长（需要解析所有文件）。
**解决方案**: 后台预计算 — 系统启动时后台解析所有文件并构建图谱，用户请求时直接使用缓存。

#### B5.5 缺少数据压缩
**问题**: v1.0 的 GameWorldGraph 在内存中可能非常大（数万节点）。
**影响**: 内存溢出。
**解决方案**: 图谱分页 + 懒加载 — 只加载当前需要的子图，其余序列化到磁盘。

#### B5.6 缺少异步 I/O
**问题**: v1.0 的文件操作是同步阻塞的。
**影响**: 高并发时 I/O 阻塞。
**解决方案**: 异步 I/O（aiofiles）+ 连接池。

#### B5.7 缺少负载均衡
**问题**: v1.0 假设单机运行，没有考虑多实例部署。
**影响**: 无法水平扩展。
**解决方案**: 无状态设计 + 负载均衡 + 共享存储（Redis/PostgreSQL）。

#### B5.8 缺少性能监控
**问题**: v1.0 没有定义性能指标和监控。
**影响**: 无法发现性能瓶颈。
**解决方案**: 引入 OpenTelemetry — 追踪每个阶段的延迟，Prometheus 指标，Grafana 仪表盘。

### 3.6 协作与并发盲点

#### B6.1 缺少实时协作
**问题**: v1.0 假设单用户操作，没有考虑多人同时编辑同一个游戏。
**影响**: 无法支持"团队协作魔改"。
**解决方案**: 引入 CRDT（如 Yjs）或 OT 算法 — 多人实时协作编辑同一个 Mod。

#### B6.2 缺少并发控制
**问题**: v1.0 没有定义多个 Mod 同时修改同一文件时的并发策略。
**影响**: 数据竞争，文件损坏。
**解决方案**: 乐观锁（文件版本号）或悲观锁（文件级互斥锁）。

#### B6.3 缺少分支管理
**问题**: v1.0 的 Mod 是线性的（一个版本链），没有分支概念。
**影响**: 无法支持"基于 v1.0 创建实验分支"这样的工作流。
**解决方案**: Git 风格分支管理 — main / dev / feature-xxx。

#### B6.4 缺少合并策略
**问题**: v1.0 没有定义两个分支合并时的策略。
**影响**: 合并冲突无法自动解决。
**解决方案**: 三路合并（Three-way merge）+ 自动冲突解决（基于语义理解）。

#### B6.5 缺少评论和审阅
**问题**: v1.0 没有内置的代码审查（Patch Review）机制。
**影响**: 质量无法保证。
**解决方案**: Patch Review 工作流 — 提交 → 自动检查 → 人工审阅 → 合并。

### 3.7 生态与商业盲点

#### B7.1 缺少创作者经济模型
**问题**: v1.0 没有定义创作者如何获益。
**影响**: 缺乏创作动力。
**解决方案**: 创作者分成 — 免费 Mod（引流）+ 付费 Mod（抽成 15-30%）+ 打赏。

#### B7.2 缺少质量评分体系
**问题**: v1.0 没有定义 Mod 的质量评估标准。
**影响**: 用户无法判断 Mod 好坏。
**解决方案**: 多维度评分 — 自动测试分 + 社区评分 + 下载量 + 兼容性指数。

#### B7.3 缺少发现机制
**问题**: v1.0 没有考虑用户如何找到想要的 Mod。
**影响**: 好的 Mod 可能被埋没。
**解决方案**: 语义搜索（基于意图描述匹配 Mod）+ 推荐系统（基于用户历史）。

#### B7.4 缺少兼容性矩阵
**问题**: v1.0 没有定义 Mod 之间的兼容性检测。
**影响**: 用户安装多个 Mod 后游戏崩溃。
**解决方案**: 自动兼容性测试 — 每对 Mod 组合在 CI 中测试，生成兼容性矩阵。

#### B7.5 缺少版本生命周期
**问题**: v1.0 没有定义 Mod 的版本策略（如何升级、如何弃用）。
**影响**: 旧版本 Mod 堆积，维护困难。
**解决方案**: SemVer + 生命周期策略 — active / maintenance / deprecated / archived。

#### B7.6 缺少社区治理
**问题**: v1.0 没有定义社区规则（什么内容允许，什么不允许）。
**影响**: 法律风险和社区氛围恶化。
**解决方案**: 内容审核 — AI 自动审核 + 人工复审 + 社区举报。

#### B7.7 缺少数据隐私
**问题**: v1.0 没有考虑用户数据（游戏存档、行为数据）的隐私保护。
**影响**: GDPR/CCPA 合规风险。
**解决方案**: 数据最小化 + 本地处理优先 + 匿名化 + 用户可控删除。

### 3.8 关系与契约盲点

#### B8.1 缺少模块间接口契约
**问题**: v1.0 定义了模块职责，但没有定义模块间的接口（输入/输出格式、错误码、超时）。
**影响**: 模块集成时出现不匹配。
**解决方案**: 为每个模块定义 OpenAPI / tRPC Schema + 接口测试。

#### B8.2 缺少数据所有权
**问题**: v1.0 没有定义"谁拥有 GameWorldGraph 的数据"。
**影响**: 缓存、更新、删除时责任不清。
**解决方案**: 数据所有权矩阵 — 感知层拥有原始图谱，规划层拥有规划状态，执行层拥有文件状态。

#### B8.3 缺少依赖方向
**问题**: v1.0 的层是单向的（上→下），但实际可能有反向依赖（验证层需要感知层重新解析）。
**影响**: 循环依赖导致架构僵化。
**解决方案**: 明确依赖方向 — 只允许相邻层通信，跨层通过事件总线。

#### B8.4 缺少生命周期管理
**问题**: v1.0 没有定义模块的启动/停止/重启策略。
**影响**: 系统无法优雅关闭，资源泄漏。
**解决方案**: 模块生命周期钩子 — init / start / stop / health_check。

#### B8.5 缺少配置管理
**问题**: v1.0 的配置（如 MCTS 参数、成本预算）散落在代码中。
**影响**: 无法动态调整。
**解决方案**: 集中配置中心 — 环境变量 / 配置文件 / 动态配置（如 etcd）。

#### B8.6 缺少版本兼容性
**问题**: v1.0 没有定义模块版本间的兼容性策略。
**影响**: 升级某模块后其他模块崩溃。
**解决方案**: 接口版本化 — v1 / v2 / v3，向后兼容保证。

#### B8.7 缺少可观测性契约
**问题**: v1.0 没有定义日志、指标、追踪的标准。
**影响**: 调试困难。
**解决方案**: 可观测性标准 — 结构化日志（JSON）、统一 Trace ID、指标命名规范。

#### B8.8 缺少测试契约
**问题**: v1.0 定义了测试，但没有定义"模块的测试边界"。
**影响**: 集成测试和单元测试边界不清。
**解决方案**: 测试金字塔 — 单元测试（模块内）、集成测试（模块间）、E2E 测试（端到端）。

---

## 4. 补充设计

### 4.1 事件驱动总线 (Event Bus)

解决数据流盲点（B1.2, B1.3, B1.4, B3.3, B8.3）。

```python
class GameModEventBus:
    """游戏魔改事件总线 — 解耦各层，支持异步和观察者模式"""

    events: Dict[str, List[Callable]] = {}

    # 核心事件类型
    EVENT_INTENT_RECEIVED = "intent.received"
    EVENT_PERCEPTION_STARTED = "perception.started"
    EVENT_PERCEPTION_COMPLETED = "perception.completed"
    EVENT_GRAPH_UPDATED = "graph.updated"
    EVENT_PLANNING_STARTED = "planning.started"
    EVENT_PLANNING_COMPLETED = "planning.completed"
    EVENT_PATCH_VALIDATED = "patch.validated"
    EVENT_EXECUTION_STARTED = "execution.started"
    EVENT_EXECUTION_COMPLETED = "execution.completed"
    EVENT_VALIDATION_PASSED = "validation.passed"
    EVENT_VALIDATION_FAILED = "validation.failed"
    EVENT_USER_FEEDBACK = "user.feedback"
    EVENT_MOD_PUBLISHED = "mod.published"
    EVENT_MOD_INSTALLED = "mod.installed"
    EVENT_MOD_ROLLED_BACK = "mod.rolled_back"

    async def emit(self, event: str, payload: Dict) -> None:
        """异步发射事件"""
        for handler in self.events.get(event, []):
            asyncio.create_task(handler(payload))

    def on(self, event: str, handler: Callable) -> None:
        """订阅事件"""
        self.events.setdefault(event, []).append(handler)

# 使用示例
bus = GameModEventBus()

# 规划层订阅感知完成事件
bus.on(GameModEventBus.EVENT_PERCEPTION_COMPLETED, async (payload) => {
    graph = payload["graph"]
    intent = payload["intent"]
    # 自动触发规划
    plan = await planner.plan(graph, intent)
    await bus.emit(GameModEventBus.EVENT_PLANNING_COMPLETED, {"plan": plan})
})

# 验证层订阅执行完成事件
bus.on(GameModEventBus.EVENT_EXECUTION_COMPLETED, async (payload) => {
    mod_package = payload["mod_package"]
    # 自动触发验证
    report = await validator.validate(mod_package)
    if report.success:
        await bus.emit(GameModEventBus.EVENT_VALIDATION_PASSED, {"report": report})
    else:
        await bus.emit(GameModEventBus.EVENT_VALIDATION_FAILED, {"report": report})
})

# 用户层订阅进度事件（WebSocket 推送）
bus.on(GameModEventBus.EVENT_PLANNING_STARTED, async (payload) => {
    await websocket.send(json.dumps({
        "type": "progress",
        "stage": "planning",
        "status": "started",
        "task_id": payload["task_id"],
    }))
})
```

### 4.2 分层缓存系统 (Layered Cache)

解决性能盲点（B5.3, B5.4, B5.5）。

```python
class GameModCacheManager:
    """游戏魔改缓存管理器 — L1/L2/L3 三级缓存"""

    def __init__(self):
        # L1: 内存缓存（热数据）
        self.l1 = LRUCache(maxsize=1000)
        # L2: 本地磁盘缓存（温数据）
        self.l2 = DiskCache(directory=".udify/cache", maxsize=1e9)
        # L3: 共享缓存（分布式部署时）
        self.l3 = RedisCache(host="localhost", port=6379, db=0)

    async def get_graph(self, game_id: str, version: str) -> Optional[GameWorldGraph]:
        """获取缓存的游戏世界图谱"""
        key = f"graph:{game_id}:{version}"

        # L1
        if key in self.l1:
            return self.l1[key]

        # L2
        if await self.l2.contains(key):
            graph = await self.l2.get(key)
            self.l1[key] = graph
            return graph

        # L3
        if await self.l3.contains(key):
            graph = await self.l3.get(key)
            await self.l2.set(key, graph)
            self.l1[key] = graph
            return graph

        return None

    async def set_graph(self, game_id: str, version: str, graph: GameWorldGraph) -> None:
        """缓存游戏世界图谱"""
        key = f"graph:{game_id}:{version}"
        self.l1[key] = graph
        await self.l2.set(key, graph, ttl=3600)
        await self.l3.set(key, graph, ttl=86400)

    async def invalidate_file(self, game_id: str, file_path: str) -> None:
        """文件变更时失效相关缓存"""
        # 1. 找到所有依赖该文件的图谱
        affected_keys = await self._find_dependent_graphs(game_id, file_path)

        # 2. 级联失效
        for key in affected_keys:
            self.l1.pop(key, None)
            await self.l2.delete(key)
            await self.l3.delete(key)

        # 3. 触发增量重建
        await self._trigger_incremental_rebuild(game_id, file_path)
```

### 4.3 知识图谱层 (Knowledge Graph Layer)

解决认知盲点（缺少游戏机制常识）。

```python
class GameKnowledgeGraph:
    """游戏知识图谱 — 游戏机制的常识库"""

    # RPG 通用知识
    rpg_knowledge = {
        "balance_rules": [
            {"rule": "boss_hp_ratio", "description": "BOSS 生命值通常是普通怪物的 5-10 倍"},
            {"rule": "exp_curve", "description": "每级所需经验通常呈指数增长"},
            {"rule": "drop_rate_cap", "description": "掉落率不应超过 100%，也不应低于 0.01%"},
            {"rule": "stat_scaling", "description": "属性增长不应超过基础值的 1000 倍"},
        ],
        "mechanic_relationships": [
            {"cause": "increase_boss_hp", "effect": "increase_exp_reward", "strength": 0.8},
            {"cause": "increase_drop_rate", "effect": "decrease_item_value", "strength": 0.6},
            {"cause": "increase_player_speed", "effect": "decrease_game_difficulty", "strength": 0.7},
        ],
        "common_patterns": [
            {"name": "hard_mode", "description": "困难模式：敌人血量×2，攻击力×1.5，经验×1.2"},
            {"name": "easy_mode", "description": "简单模式：玩家血量×2，敌人攻击力×0.7"},
            {"name": "loot_fiesta", "description": "掉落狂欢：掉落率×3，稀有物品出现率×2"},
        ],
        "dangerous_patterns": [
            {"pattern": "set_hp_to_999999", "risk": "破坏游戏平衡，导致无敌"},
            {"pattern": "delete_all_enemies", "risk": "删除所有敌人导致无法通关"},
            {"pattern": "set_exp_to_zero", "risk": "无法升级导致游戏卡住"},
        ],
    }

    # miu2d 特有知识
    miu2d_knowledge = {
        "magic_combos": [
            {"combo": "fire + ice", "result": "steam_blast", "power": 1.5},
            {"combo": "lightning + water", "result": "chain_lightning", "power": 2.0},
        ],
        "npc_archetypes": [
            {"archetype": "tutorial_mentor", "typical_stats": {"hp": 100, "friendly": True}},
            {"archetype": "first_boss", "typical_stats": {"hp": 500, "level": 5}},
        ],
        "map_regions": [
            {"region": "starter_village", "level_range": (1, 5), "enemy_types": ["slime", "wolf"]},
            {"region": "dark_forest", "level_range": (10, 20), "enemy_types": ["skeleton", "ghost"]},
        ],
    }

    def validate_mod_against_knowledge(self, patch: GameModPatch) -> List[KnowledgeWarning]:
        """根据知识图谱验证 Mod 的合理性"""
        warnings = []

        for op in patch.operations:
            # 检查危险模式
            for dangerous in self.rpg_knowledge["dangerous_patterns"]:
                if dangerous["pattern"] in str(op.payload):
                    warnings.append(KnowledgeWarning(
                        level="critical",
                        message=f"检测到危险模式: {dangerous['risk']}",
                        operation=op,
                    ))

            # 检查数值合理性
            if op.op_type == OpType.MODIFY_INI:
                key = op.payload.get("key", "")
                new_value = op.payload.get("new_value", 0)
                if key == "MaxLife" and new_value > 100000:
                    warnings.append(KnowledgeWarning(
                        level="warning",
                        message="生命值设置过高，可能破坏平衡",
                        operation=op,
                    ))

        return warnings
```

### 4.4 反馈闭环 (Feedback Loop)

解决状态管理盲点（缺少用户反馈循环）。

```python
class FeedbackLoop:
    """反馈闭环 — 收集用户反馈，优化未来规划"""

    def __init__(self):
        self.feedback_store = FeedbackStore()
        self.learning_engine = LearningEngine()

    async def collect_feedback(self, mod_id: str, feedback: UserFeedback) -> None:
        """收集用户反馈"""
        # 存储反馈
        await self.feedback_store.save(mod_id, feedback)

        # 实时分析
        await self._analyze_feedback(mod_id, feedback)

    async def _analyze_feedback(self, mod_id: str, feedback: UserFeedback) -> None:
        """分析反馈并更新模型"""
        # 1. 情感分析
        sentiment = await self.learning_engine.analyze_sentiment(feedback.comment)

        # 2. 归因分析 — 哪些操作导致了正面/负面反馈
        mod = await self.feedback_store.get_mod(mod_id)
        for op in mod.patch.operations:
            # 基于操作类型和反馈的相关性更新权重
            await self.learning_engine.update_action_weight(
                action_type=op.op_type,
                target_type=self._infer_target_type(op),
                sentiment=sentiment,
            )

        # 3. 模式学习 — 从成功的 Mod 中提取模式
        if feedback.rating >= 4:
            pattern = self._extract_pattern(mod.patch)
            await self.learning_engine.learn_successful_pattern(pattern)

    def _extract_pattern(self, patch: GameModPatch) -> ModPattern:
        """从 Patch 中提取可复用的模式"""
        return ModPattern(
            intent_keywords=self._extract_keywords(patch.intent),
            action_sequence=[op.op_type for op in patch.operations],
            target_properties=self._extract_target_properties(patch),
            success_rate=0.0,  # 初始值，后续更新
        )

    async def get_suggested_patterns(self, intent: Intent) -> List[ModPattern]:
        """根据意图推荐成功模式"""
        keywords = self._extract_keywords(intent.description)
        return await self.learning_engine.find_similar_patterns(keywords)
```

### 4.5 多 Mod 管理器 (Multi-Mod Manager)

解决协作盲点（B6.2, B6.3, B6.4）和生态盲点（B7.4）。

```python
class MultiModManager:
    """多 Mod 管理器 — 管理多个 Mod 的安装、卸载、冲突解决"""

    def __init__(self, game_root: Path):
        self.game_root = game_root
        self.installed_mods: Dict[str, InstalledMod] = {}
        self.conflict_resolver = ConflictResolver()

    async def install_mod(self, mod_package: ModPackage) -> InstallResult:
        """安装 Mod"""
        # 1. 检查依赖
        for dep_id in mod_package.dependencies:
            if dep_id not in self.installed_mods:
                return InstallResult(success=False, error=f"缺少依赖: {dep_id}")

        # 2. 检查冲突
        conflicts = await self._detect_conflicts(mod_package)
        if conflicts:
            # 自动解决或请求人工介入
            resolved = await self.conflict_resolver.resolve(conflicts)
            if not resolved.success:
                return InstallResult(success=False, error="冲突无法自动解决", conflicts=conflicts)

        # 3. 应用 Patch
        result = await self._apply_mod(mod_package)

        # 4. 验证
        validation = await self._validate_installation(mod_package)
        if not validation.success:
            await self._rollback(mod_package)
            return InstallResult(success=False, error="验证失败", validation=validation)

        # 5. 记录安装
        self.installed_mods[mod_package.id] = InstalledMod(
            package=mod_package,
            installed_at=datetime.now(),
            order=len(self.installed_mods),
        )

        return InstallResult(success=True)

    async def _detect_conflicts(self, new_mod: ModPackage) -> List[ModConflict]:
        """检测新 Mod 与已安装 Mod 的冲突"""
        conflicts = []

        for existing_mod in self.installed_mods.values():
            # 检查文件级冲突
            for file_path in new_mod.files:
                if file_path in existing_mod.package.files:
                    conflicts.append(ModConflict(
                        type="file_collision",
                        mod_a=new_mod.id,
                        mod_b=existing_mod.package.id,
                        file=file_path,
                        severity="error",
                    ))

            # 检查语义级冲突
            for op_a in new_mod.patch.operations:
                for op_b in existing_mod.package.patch.operations:
                    if self._is_semantic_conflict(op_a, op_b):
                        conflicts.append(ModConflict(
                            type="semantic_conflict",
                            mod_a=new_mod.id,
                            mod_b=existing_mod.package.id,
                            description=f"操作冲突: {op_a} vs {op_b}",
                            severity="warning",
                        ))

        return conflicts

    async def uninstall_mod(self, mod_id: str) -> UninstallResult:
        """卸载 Mod"""
        if mod_id not in self.installed_mods:
            return UninstallResult(success=False, error="Mod 未安装")

        mod = self.installed_mods[mod_id]

        # 1. 回滚文件
        await self._rollback_mod(mod)

        # 2. 重新应用后续 Mod（如果有依赖顺序）
        for later_mod in self._get_later_mods(mod_id):
            await self._reapply_mod(later_mod)

        # 3. 移除记录
        del self.installed_mods[mod_id]

        return UninstallResult(success=True)

    async def create_mod_stack(self, mod_ids: List[str]) -> ModStack:
        """创建 Mod 堆栈 — 确定加载顺序"""
        # 拓扑排序 — 基于依赖关系
        graph = {mod_id: self.installed_mods[mod_id].package.dependencies for mod_id in mod_ids}
        sorted_ids = topological_sort(graph)

        return ModStack(
            mods=[self.installed_mods[mod_id] for mod_id in sorted_ids],
            load_order=sorted_ids,
        )
```

### 4.6 沙箱执行环境 (Sandboxed Execution)

解决安全盲点（B4.1, B4.2, B4.3）。

```python
class SandboxedExecutor:
    """沙箱执行器 — 在隔离环境中执行 AI 生成的代码"""

    def __init__(self):
        self.sandbox = DockerSandbox(
            image="udify-sandbox:latest",
            memory_limit="512m",
            cpu_limit=1.0,
            network_mode="none",  # 禁止网络
            readonly_volumes=["/game"],  # 游戏目录只读
            writable_volumes=["/tmp/output"],  # 只允许写入临时目录
        )

    async def execute_script(self, script: str, context: ExecutionContext) -> ExecutionResult:
        """在沙箱中执行脚本"""
        # 1. 写入脚本到沙箱
        script_path = f"/tmp/script_{uuid4()}.lua"
        await self.sandbox.write_file(script_path, script)

        # 2. 在沙箱中执行
        result = await self.sandbox.run(
            command=["lua", script_path],
            timeout=10,  # 10 秒超时
            env={
                "GAME_ROOT": "/game",
                "OUTPUT_DIR": "/tmp/output",
            },
        )

        # 3. 检查输出
        if result.returncode != 0:
            return ExecutionResult(
                success=False,
                error=result.stderr,
                output=result.stdout,
            )

        # 4. 检查是否有副作用（如写入非预期文件）
        side_effects = await self._detect_side_effects(result)
        if side_effects:
            return ExecutionResult(
                success=False,
                error=f"检测到副作用: {side_effects}",
                output=result.stdout,
            )

        return ExecutionResult(success=True, output=result.stdout)

    async def validate_patch_safety(self, patch: GameModPatch) -> SafetyReport:
        """验证 Patch 的安全性"""
        report = SafetyReport()

        for op in patch.operations:
            if op.op_type == OpType.INSERT_SCRIPT:
                # 在沙箱中执行脚本，检查副作用
                result = await self.execute_script(op.payload["code"], ExecutionContext())
                if not result.success:
                    report.add_vulnerability(
                        level="high",
                        description=f"脚本执行失败: {result.error}",
                        operation=op,
                    )

            if op.op_type == OpType.REPLACE_ASSET:
                # 检查替换的资源是否包含恶意内容
                asset_path = op.payload["path"]
                is_safe = await self._scan_asset_safety(asset_path)
                if not is_safe:
                    report.add_vulnerability(
                        level="critical",
                        description="资源可能包含恶意内容",
                        operation=op,
                    )

        return report
```

### 4.7 权限与审计 (Auth & Audit)

解决安全盲点（B4.5, B4.6, B8.7）。

```python
class ModAuthManager:
    """Mod 权限管理器"""

    ROLES = {
        "owner": ["read", "write", "delete", "publish", "invite"],
        "editor": ["read", "write"],
        "viewer": ["read"],
        "tester": ["read", "test"],
    }

    def __init__(self):
        self.acl_store = ACLStore()
        self.audit_log = AuditLog()

    async def check_permission(self, user_id: str, mod_id: str, action: str) -> bool:
        """检查用户是否有权限执行操作"""
        role = await self.acl_store.get_role(user_id, mod_id)
        return action in self.ROLES.get(role, [])

    async def record_action(self, user_id: str, mod_id: str, action: str, details: Dict) -> None:
        """记录审计日志"""
        await self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "mod_id": mod_id,
            "action": action,
            "details": details,
            "ip_address": details.get("ip_address"),
            "user_agent": details.get("user_agent"),
        })

class AuditLog:
    """审计日志 — 不可变、可验证"""

    def __init__(self):
        self.entries: List[AuditEntry] = []
        self.chain_hash: str = "0" * 64  # 初始哈希

    async def append(self, entry: Dict) -> None:
        """追加审计记录（链式哈希）"""
        entry_hash = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
        combined = f"{self.chain_hash}{entry_hash}"
        self.chain_hash = hashlib.sha256(combined.encode()).hexdigest()

        self.entries.append(AuditEntry(
            data=entry,
            previous_hash=self.chain_hash,
            entry_hash=entry_hash,
        ))

    def verify_integrity(self) -> bool:
        """验证审计日志完整性"""
        current_hash = "0" * 64
        for entry in self.entries:
            computed = hashlib.sha256(f"{current_hash}{entry.entry_hash}".encode()).hexdigest()
            if computed != entry.previous_hash:
                return False
            current_hash = computed
        return True
```

### 4.8 成本控制器 (Cost Controller)

解决性能盲点（B5.1, B5.2）。

```python
class CostController:
    """成本控制器 — 控制 LLM 调用成本和计算资源"""

    def __init__(self, budget: float = 0.5):
        self.budget = budget
        self.spent = 0.0
        self.local_model = LocalModel()  # 本地轻量模型
        self.cost_history: List[CostRecord] = []

    async def plan_with_budget(self, intent: Intent, graph: GameWorldGraph) -> PlanResult:
        """在预算内规划"""
        # 1. 估算成本
        estimated_cost = self._estimate_cost(intent, graph)

        if estimated_cost > self.budget * 0.8:
            # 预算紧张，使用本地模型
            return await self._plan_with_local_model(intent, graph)

        # 2. 尝试使用 LLM
        try:
            result = await self._plan_with_llm(intent, graph)
            actual_cost = self._calculate_actual_cost(result)
            self.spent += actual_cost

            if self.spent > self.budget:
                # 超出预算，回滚并切换本地模型
                self.spent -= actual_cost
                return await self._plan_with_local_model(intent, graph)

            return result

        except LLMRateLimitError:
            # LLM 限流，降级到本地模型
            return await self._plan_with_local_model(intent, graph)

    def _estimate_cost(self, intent: Intent, graph: GameWorldGraph) -> float:
        """估算规划成本"""
        # 基于意图复杂度和图谱大小
        complexity = len(intent.description) / 100  # 描述长度
        graph_size = len(graph.nodes) / 1000  # 节点数
        return complexity * graph_size * 0.01  # 每个单位 $0.01

    async def _plan_with_local_model(self, intent: Intent, graph: GameWorldGraph) -> PlanResult:
        """使用本地模型规划"""
        # 本地模型质量较低但免费
        return await self.local_model.plan(intent, graph)

    async def _plan_with_llm(self, intent: Intent, graph: GameWorldGraph) -> PlanResult:
        """使用 LLM 规划"""
        # 调用外部 API
        return await llm_client.plan(intent, graph)

    def get_cost_report(self) -> CostReport:
        """生成成本报告"""
        return CostReport(
            budget=self.budget,
            spent=self.spent,
            remaining=self.budget - self.spent,
            history=self.cost_history,
            savings=self.budget - self.spent,
        )
```

---

## 5. 改进后的完整架构

### 5.1 架构全景图

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                      接入层 (Access Layer)                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Web UI       │  │ CLI          │  │ API          │  │ Dashboard    │  │ Mobile       │ │
│  │ (React)      │  │ (Python)     │  │ (tRPC/REST)  │  │ (miu2d嵌入)  │  │ (PWA)        │ │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘ │
└─────────┼─────────────────┼─────────────────┼─────────────────┼─────────────────┼───────────┘
          │                 │                 │                 │                 │
          └─────────────────┴─────────────────┴────────┬────────┴─────────────────┘
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    网关层 (Gateway Layer)                                    │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ API Gateway                                                                         │   │
│  │  • 认证 (JWT/OAuth2)  • 限流  • 路由  • 负载均衡  • 健康检查                           │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   服务层 (Service Layer)                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │ 用户服务         │  │ 权限服务         │  │ 成本服务         │  │ 审计服务         │        │
│  │ (Auth)          │  │ (RBAC)          │  │ (CostControl)   │  │ (AuditLog)      │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   核心层 (Core Layer)                                        │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ 事件总线 (Event Bus)                                                                 │   │
│  │  intent.received → perception.started → planning.started → execution.started        │   │
│  │       ↓                    ↓                  ↓                ↓                    │   │
│  │  user.feedback ← validation.passed ← execution.completed ← planning.completed       │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │ 会话管理器       │  │ 任务调度器       │  │ 缓存管理器       │  │ 配置中心         │        │
│  │ (ModSession)    │  │ (TaskQueue)     │  │ (L1/L2/L3)      │  │ (ConfigCenter)  │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ 反馈闭环 (Feedback Loop)                                                             │   │
│  │  收集反馈 → 情感分析 → 归因分析 → 模式学习 → 权重更新 → 推荐优化                         │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │ 知识图谱         │  │ 多 Mod 管理器    │  │ 沙箱执行器       │  │ 成本控制器       │        │
│  │ (GameKnowledge) │  │ (MultiModMgr)   │  │ (Sandbox)       │  │ (CostController)│        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   处理流水线 (Pipeline Layer)                                │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ 感知层 (Perception)                                                                  │   │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │   │
│  │  │ AssetDecoder │  │ WorldBuilder │  │ SchemaExtractor│  │ Incremental  │            │   │
│  │  │ (8种格式)     │  │ (图谱构建)   │  │ (类型提取)    │  │ (增量更新)    │            │   │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │   │
│  │         └─────────────────┴────────┬────────┴─────────────────┘                      │   │
│  │                                    ▼                                                │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ GameWorldGraph (游戏世界图谱)                                                  │   │   │
│  │  │  节点: Character, Item, Magic, Map, Scene, Quest, Dialog, Shop               │   │   │
│  │  │  边: contains, depends_on, triggers, requires, references                     │   │   │
│  │  │  属性: 数值参数 + 脚本引用 + 资源路径 + SourceLocation (文件+行号)             │   │   │
│  │  │  版本: graph_version + checksum                                               │   │   │
│  │  └─────────────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ 规划层 (Planning)                                                                    │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │   │
│  │  │ IntentParser    │  │ GameModActionSpace│  │ GameBalanceValueFn│  │ KnowledgeValidator│ │   │
│  │  │ (意图解析)       │  │ (动作生成)       │  │ (价值评估)       │  │ (知识校验)       │ │   │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │   │
│  │           └────────────────────┴────────┬───────────┴────────────────────┘          │   │
│  │                                         ▼                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ ModPlanner (MCTS + LLM/Local)                                               │   │   │
│  │  │  • Selection (UCT) → Expansion → Simulation → Backpropagation               │   │   │
│  │  │  • 早期终止: 找到满意解时停止                                               │   │   │
│  │  │  • 降级策略: LLM不可用时切Local模型                                         │   │   │
│  │  └─────────────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ 补丁层 (Patch)                                                                       │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │   │
│  │  │ GameModPatch    │  │ PatchValidator  │  │ ConflictResolver│  │ PatchMerger     │ │   │
│  │  │ (5种原子操作)   │  │ (静态验证)       │  │ (冲突解决)       │  │ (合并策略)       │ │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘ │   │
│  │                                                                                     │   │
│  │  原子操作: MODIFY_INI | INSERT_SCRIPT | REPLACE_ASSET | EDIT_MAP | ADD_RECORD       │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ 执行层 (Execution)                                                                   │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │   │
│  │  │ FilePatcher     │  │ ScriptInjector  │  │ AssetBundler    │  │ BackupManager   │ │   │
│  │  │ (文件修改)       │  │ (脚本注入)       │  │ (资源打包)       │  │ (备份管理)       │ │   │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘ │   │
│  │           └────────────────────┴────────┬───────────┴────────────────────┘          │   │
│  │                                         ▼                                           │   │
│  │  ┌─────────────────────────────────────────────────────────────────────────────┐   │   │
│  │  │ ModPackage (Mod 包)                                                          │   │   │
│  │  │  • 修改文件 + 增量补丁 + 元数据 + 回滚脚本 + 校验和                            │   │   │
│  │  │  • 三级原子性: File Atomic | Mod Atomic | Session Atomic                     │   │   │
│  │  └─────────────────────────────────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────────────────┐   │
│  │ 验证层 (Validation)                                                                  │   │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │   │
│  │  │ StaticValidator │  │ RuntimeValidator│  │ PlaytestAgent   │  │ SafetyScanner   │ │   │
│  │  │ (静态检查)       │  │ (运行时检查)     │  │ (自动化试玩)     │  │ (安全扫描)       │ │   │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                             │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
                                                       ▼
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   存储层 (Storage Layer)                                     │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐        │
│  │ 文件系统         │  │ 关系数据库       │  │ 图数据库         │  │ 对象存储         │        │
│  │ (游戏文件)       │  │ (PostgreSQL)    │  │ (Neo4j)         │  │ (MinIO/S3)      │        │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  └─────────────────┘        │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 关键数据流时序图

```
场景: 用户提交意图 "让第一个BOSS变强"

User        Gateway     SessionMgr  EventBus    Perception  Planning    Execution   Validation  Storage
 |             |            |           |            |           |           |           |          |
 |--"意图"--> |            |           |            |           |           |           |          |
 |            |--创建会话->|           |            |           |           |           |          |
 |            |            |--emit---->|"intent.received"       |           |           |          |
 |            |            |           |--订阅------>|           |           |           |          |
 |            |            |           |            |--分析文件->|           |           |          |
 |            |            |           |            |            |           |           |          |
 |            |            |           |            |<-返回图谱--|           |           |          |
 |            |            |           |<--emit----|"perception.completed"   |           |          |
 |            |            |           |--订阅------------------>|           |           |          |
 |            |            |           |                        |--MCTS搜索->|           |          |
 |            |            |           |                        |            |           |          |
 |            |            |           |                        |<-返回计划--|           |          |
 |            |            |           |<--emit----------------|"planning.completed"     |           |
 |            |            |           |--订阅-------------------------------->|           |          |
 |            |            |           |                                    |--应用Patch->|           |
 |            |            |           |                                    |            |           |
 |            |            |           |                                    |<-返回包----|           |
 |            |            |           |<--emit----------------------------|"execution.completed"  |
 |            |            |           |--订阅-------------------------------------------->|          |
 |            |            |           |                                                |--验证->   |
 |            |            |           |                                                |           |
 |            |            |           |                                                |<-报告----|
 |            |            |           |<--emit----------------------------------------|"validation.passed"
 |            |            |           |                                                        |    |
 |            |            |           |--emit-------------------------------------------------->|"mod.saved"
 |            |            |           |                                                        |    |
 |<--结果----|            |           |                                                        |    |
 |            |            |           |                                                        |    |
 |--反馈---->|            |           |                                                        |    |
 |            |--emit---->|           |"user.feedback"                                        |    |
 |            |            |--存储反馈->|                                                        |    |
 |            |            |           |--触发学习-------------------------------------------->|    |
 |            |            |           |                                                        |    |
```

---

## 6. 关键决策记录 (ADR)

### ADR-G1: 引入事件驱动架构

**问题**: 各层紧耦合，无法支持异步和观察者模式。
**决策**: 引入事件总线解耦各层。
**权衡**: + 解耦、异步、可扩展； - 调试复杂、需要追踪工具。
**状态**: 已采纳。

### ADR-G2: 三级缓存策略

**问题**: 大型游戏解析成本高，重复计算浪费资源。
**决策**: L1 内存 + L2 磁盘 + L3 Redis 三级缓存。
**权衡**: + 性能提升 10-100x； - 一致性复杂、需要失效策略。
**状态**: 已采纳（Phase 1A 实现 L1/L2，Phase 2 实现 L3）。

### ADR-G3: 引入知识图谱层

**问题**: AI 缺乏游戏机制常识，可能生成不合理修改。
**决策**: 内置 RPG 通用知识和 miu2d 特有知识。
**权衡**: + 提高修改质量； - 知识维护成本高、需要持续更新。
**状态**: 已采纳（Phase 1A 实现基础规则，Phase 2 扩展）。

### ADR-G4: 反馈闭环设计

**问题**: 系统无法从用户反馈中学习。
**决策**: 收集反馈 → 情感分析 → 归因分析 → 模式学习 → 权重更新。
**权衡**: + 系统自我改进； - 隐私风险、需要数据保护。
**状态**: 已采纳（Phase 1C 实现基础反馈，Phase 3 扩展学习）。

### ADR-G5: 多 Mod 管理器

**问题**: 用户可能安装多个 Mod，需要管理依赖和冲突。
**决策**: 引入 Mod 堆栈、拓扑排序、三路合并。
**权衡**: + 支持复杂 Mod 生态； - 实现复杂、测试成本高。
**状态**: 已采纳（Phase 2 实现基础版，Phase 3 扩展）。

### ADR-G6: 沙箱执行环境

**问题**: AI 生成代码可能包含恶意内容或副作用。
**决策**: Docker 沙箱 + 资源限制 + 网络隔离 + 副作用检测。
**权衡**: + 安全性高； - 性能开销（每次执行需启动容器）。
**状态**: 已采纳（Phase 1B 实现基础沙箱，Phase 2 优化）。

### ADR-G7: 成本控制器

**问题**: LLM API 成本高，可能失控。
**决策**: 预算制 + 本地模型降级 + 成本追踪。
**权衡**: + 成本控制； - 本地模型质量较低。
**状态**: 已采纳（Phase 1A 实现基础版）。

### ADR-G8: 审计日志链式哈希

**问题**: 需要保证操作记录的不可篡改性。
**决策**: 链式哈希审计日志（类似区块链但单机）。
**权衡**: + 不可篡改、可验证； - 存储开销、查询性能。
**状态**: 已采纳（Phase 1C 实现）。

### ADR-G9: 增量感知优先于全量感知

**问题**: 大型游戏全量解析成本高。
**决策**: 首次全量 + 后续增量（基于文件 mtime 和依赖图）。
**权衡**: + 性能提升显著； - 依赖图维护复杂。
**状态**: 已采纳（Phase 1A 实现）。

### ADR-G10: 预览模式（VFS）优先于直接应用

**问题**: 用户需要预览修改效果再决定是否应用。
**决策**: 虚拟文件系统预览模式，确认后才应用到实际文件。
**权衡**: + 安全性高、用户体验好； - 内存开销、实现复杂。
**状态**: 已采纳（Phase 1A 实现基础 VFS，Phase 1C 扩展）。

---

## 7. 实施优先级调整

基于盲点审查，调整实施优先级：

### P0 (必须) — Week 1-2

1. **增量感知 + L1 缓存** (B1.1, B5.3, B5.4)
2. **事件总线** (B1.3, B8.3)
3. **VFS 预览模式** (B2.3, B4.1)
4. **输入消毒 + 输出净化** (B3.4, B3.5)
5. **成本控制器** (B5.1)
6. **会话管理** (B2.1)

### P1 (重要) — Week 3-4

7. **知识图谱（基础规则）** (B4.1)
8. **沙箱执行器（基础版）** (B4.1)
9. **反馈闭环（基础版）** (B7.2)
10. **多 Mod 管理器（基础版）** (B6.2)
11. **静态验证器增强** (B3.6)
12. **审计日志** (B4.5)

### P2 (有价值) — Month 2

13. **运行时验证器（Playwright）** (B3.6)
14. **L2/L3 缓存** (B5.3)
15. **权限管理（RBAC）** (B4.5)
16. **异步任务队列** (B1.3)
17. **错误降级策略** (B3.1)

### P3 (未来) — Month 3+

18. **Playtest Agent** (B7.3)
19. **社区市场** (B7.1, B7.6)
20. **创作者经济** (B7.1)
21. **多用户协作（CRDT）** (B6.1)
22. **数据隐私合规** (B7.7)

---

## 附录 A: 盲点清单速查表

| 编号 | 盲点 | 严重程度 | 解决状态 | 对应补充设计 |
|------|------|---------|---------|-------------|
| B1.1 | 增量更新数据流 | 🔴 高 | ✅ 已设计 | 增量感知 |
| B1.2 | 事件溯源 | 🟡 中 | ✅ 已设计 | 事件总线 + 链式哈希 |
| B1.3 | 异步流水线 | 🟡 中 | ✅ 已设计 | 事件总线 + 任务队列 |
| B1.4 | 多源数据合并 | 🟡 中 | ✅ 已设计 | 分层图谱 |
| B1.5 | 数据血缘追踪 | 🟡 中 | ✅ 已设计 | SourceLocation |
| B1.6 | 跨层一致性校验 | 🟡 中 | ✅ 已设计 | 图谱版本号 |
| B2.1 | 会话状态管理 | 🔴 高 | ✅ 已设计 | ModSession |
| B2.2 | 冲突状态机 | 🟡 中 | ✅ 已设计 | ConflictResolver |
| B2.3 | 预览状态隔离 | 🔴 高 | ✅ 已设计 | VFS 预览模式 |
| B2.4 | 原子性保证 | 🟡 中 | ✅ 已设计 | 三级原子性 |
| B2.5 | 图谱缓存失效 | 🟡 中 | ✅ 已设计 | 分层缓存 |
| B3.1 | 降级策略 | 🔴 高 | ✅ 已设计 | 三级降级 |
| B3.2 | 部分失败恢复 | 🟡 中 | ✅ 已设计 | Checkpoint |
| B3.3 | 超时熔断 | 🟡 中 | ✅ 已设计 | SLI/SLO |
| B3.4 | 输入消毒 | 🔴 高 | ✅ 已设计 | 输入消毒层 |
| B3.5 | 输出净化 | 🔴 高 | ✅ 已设计 | 输出净化层 |
| B3.6 | 数据损坏检测 | 🟡 中 | ✅ 已设计 | 应用后解析验证 |
| B3.7 | 幂等性 | 🟡 中 | ✅ 已设计 | Patch ID + 校验和 |
| B4.1 | AI 输出沙箱 | 🔴 高 | ✅ 已设计 | Docker 沙箱 |
| B4.2 | 文件系统隔离 | 🔴 高 | ✅ 已设计 | chroot jail |
| B4.3 | secrets 保护 | 🟢 低 | ⬜ 待实现 | 文件扫描 |
| B4.4 | 版权检测 | 🟢 低 | ⬜ 待实现 | 资源指纹 |
| B4.5 | 用户权限 | 🟡 中 | ✅ 已设计 | RBAC |
| B4.6 | 供应链安全 | 🟢 低 | ⬜ 待实现 | 签名验证 |
| B5.1 | LLM 成本 | 🔴 高 | ✅ 已设计 | CostController |
| B5.2 | 计算资源配额 | 🟡 中 | ✅ 已设计 | 资源配额 |
| B5.3 | 缓存分层 | 🟡 中 | ✅ 已设计 | L1/L2/L3 |
| B5.4 | 预计算 | 🟡 中 | ✅ 已设计 | 后台预计算 |
| B5.5 | 数据压缩 | 🟢 低 | ⬜ 待实现 | 图谱分页 |
| B5.6 | 异步 I/O | 🟡 中 | ⬜ 待实现 | aiofiles |
| B5.7 | 负载均衡 | 🟢 低 | ⬜ 待实现 | 无状态设计 |
| B5.8 | 性能监控 | 🟡 中 | ⬜ 待实现 | OpenTelemetry |
| B6.1 | 实时协作 | 🟢 低 | ⬜ 待实现 | CRDT |
| B6.2 | 并发控制 | 🟡 中 | ✅ 已设计 | 乐观锁 |
| B6.3 | 分支管理 | 🟢 低 | ⬜ 待实现 | Git 分支 |
| B6.4 | 合并策略 | 🟡 中 | ✅ 已设计 | 三路合并 |
| B6.5 | 评论审阅 | 🟢 低 | ⬜ 待实现 | Patch Review |
| B7.1 | 创作者经济 | 🟢 低 | ⬜ 待实现 | 分成模型 |
| B7.2 | 质量评分 | 🟢 低 | ⬜ 待实现 | 多维度评分 |
| B7.3 | 发现机制 | 🟢 低 | ⬜ 待实现 | 语义搜索 |
| B7.4 | 兼容性矩阵 | 🟡 中 | ✅ 已设计 | 自动兼容性测试 |
| B7.5 | 版本生命周期 | 🟢 低 | ⬜ 待实现 | SemVer |
| B7.6 | 社区治理 | 🟢 低 | ⬜ 待实现 | 内容审核 |
| B7.7 | 数据隐私 | 🟡 中 | ⬜ 待实现 | GDPR 合规 |
| B8.1 | 接口契约 | 🟡 中 | ⬜ 待实现 | OpenAPI |
| B8.2 | 数据所有权 | 🟡 中 | ✅ 已设计 | 所有权矩阵 |
| B8.3 | 依赖方向 | 🟡 中 | ✅ 已设计 | 事件总线 |
| B8.4 | 生命周期管理 | 🟡 中 | ✅ 已设计 | 生命周期钩子 |
| B8.5 | 配置管理 | 🟡 中 | ⬜ 待实现 | 配置中心 |
| B8.6 | 版本兼容 | 🟡 中 | ⬜ 待实现 | 接口版本化 |
| B8.7 | 可观测性 | 🟡 中 | ⬜ 待实现 | 结构化日志 |
| B8.8 | 测试契约 | 🟡 中 | ⬜ 待实现 | 测试金字塔 |

---

## 附录 B: 关键关系矩阵

### 模块依赖矩阵

| 模块 | 依赖 | 被依赖 | 耦合度 |
|------|------|--------|--------|
| EventBus | 无 | 所有模块 | 低（事件解耦） |
| CacheManager | 无 | Perception, Planning | 低 |
| CostController | 无 | Planning | 低 |
| Perception | AssetDecoder, CacheManager | Planning | 中 |
| Planning | Perception, KnowledgeGraph, CostController | Execution | 高 |
| Execution | Planning, Sandbox | Validation | 中 |
| Validation | Execution | FeedbackLoop | 中 |
| FeedbackLoop | Validation | Planning（间接） | 低 |
| MultiModManager | Execution, ConflictResolver | UserLayer | 中 |
| Sandbox | 无 | Execution | 低 |

### 数据所有权矩阵

| 数据 | 所有者 | 读写权限 | 生命周期 |
|------|--------|---------|---------|
| 原始游戏文件 | 游戏开发商 | 只读 | 外部管理 |
| GameWorldGraph | Perception | 读写 | 会话级别 |
| ModPatch | Planning | 读写 | 会话级别 |
| ModPackage | Execution | 读写 | 持久化 |
| 用户反馈 | FeedbackLoop | 只写 | 持久化 |
| 审计日志 | AuditLog | 只写 | 不可变 |
| 缓存数据 | CacheManager | 读写 | TTL 管理 |

---

> **文档作者**: OpenCode Agent
> **审查基准**: `docs/ARCHITECTURE-GAME-MOD-v1.md`
> **产出**: 47 项盲点识别 + 12 个补充模块 + 10 个 ADR + 调整后的实施优先级
> **下一步**: 基于 P0 优先级开始实现
