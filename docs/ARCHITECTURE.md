# Udify 系统架构（初步方向）

> **TL;DR**: 分层、模块化、事件驱动的架构。核心原则是"媒介无关的抽象层 + 媒介特定的实现层"。系统由 Udify Core（后端引擎）、Udiface（前端平台）和 Udiscipline（理论与方法学）三大子系统构成，通过明确的消息协议和 API 接口协作。

---

## 目录

1. [架构设计原则](#1-架构设计原则)
2. [系统总体架构](#2-系统总体架构)
3. [Udify Core 详细架构](#3-udify-core-详细架构)
4. [Udiface 平台架构](#4-udiface-平台架构)
5. [Udiscipline 方法学框架](#5-udiscipline-方法学框架)
6. [数据模型](#6-数据模型)
7. [关键接口与协议](#7-关键接口与协议)
8. [扩展性设计](#8-扩展性设计)
9. [安全与隐私架构](#9-安全与隐私架构)
10. [部署架构](#10-部署架构)

---

## 1. 架构设计原则

### 1.1 核心原则

**P1: 媒介抽象（Media Abstraction）**

核心引擎不直接处理具体媒介格式，而是通过**内容描述语言（CDL）**作为中间表示。所有媒介特定的解析、生成、转换都封装在适配器中。

```
原始内容 → [媒介适配器] → CDL → [核心引擎] → CDL → [媒介适配器] → 改造内容
```

**P2: 组合优于继承（Composition over Inheritance）**

系统功能通过组合原子操作（Atomic Operations）实现，而非庞大的继承层次。每个原子操作是自包含的、可测试的、可复用的。

**P3: 事件驱动（Event-Driven）**

系统组件之间通过事件总线（Event Bus）异步通信，降低耦合，支持扩展和重放。

**P4: 失败即信息（Failure as Information）**

任何失败都被记录、分析、学习。系统不从失败中恢复就丢弃，而是提取知识用于未来改进。

**P5: 渐进披露（Progressive Disclosure）**

简单任务自动完成，复杂任务逐步引入人类决策。用户始终可以选择"信任系统"或"手动控制"。

**P6: 开放封闭（Open/Closed）**

核心系统对扩展开放（新媒介、新操作、新模型），对修改封闭（核心接口稳定）。

### 1.2 反模式（Anti-Patterns）

❌ **大泥球（Big Ball of Mud）**：所有逻辑耦合在一起，无法独立演进。  
❌ **过早优化（Premature Optimization）**：在验证用户需求前过度设计性能。  
❌ **上帝对象（God Object）**：一个类/模块负责太多事情。  
❌ **魔法字符串（Magic Strings）**：用硬编码字符串表示类型和状态，导致脆弱性。  
❌ **分布式单体（Distributed Monolith）**：服务之间高度耦合，失去微服务的独立性。

---

## 2. 系统总体架构

### 2.1 高层视图

```
┌─────────────────────────────────────────────────────────────────────┐
│                         用户层 (User Layer)                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Web App  │  │ Mobile   │  │ CLI      │  │ API      │            │
│  │ (React)  │  │ (Future) │  │ (Python) │  │ (REST)   │            │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘            │
└───────┼─────────────┼─────────────┼─────────────┼────────────────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────────┐
│                    Udiface 平台层 (Platform Layer)                   │
│  ┌──────────────┐  ┌───────┴───────┐  ┌──────────────────────┐     │
│  │ 内容管理      │  │ 用户与社交     │  │ 经济与治理            │     │
│  │ - 项目CRUD    │  │ - 认证授权     │  │ - 支付系统           │     │
│  │ - 版本控制    │  │ - 关注互动     │  │ - 收益分配           │     │
│  │ - 搜索发现    │  │ - 评论反馈     │  │ - 声誉系统           │     │
│  └──────┬───────┘  └───────┬───────┘  └──────────┬───────────┘     │
└─────────┼──────────────────┼─────────────────────┼───────────────────┘
          │                  │                     │
          └──────────────────┼─────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────────┐
│                      API 网关层 (API Gateway)                        │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  - 认证鉴权 (JWT/OAuth2)                                      │  │
│  │  - 速率限制 (Rate Limiting)                                   │  │
│  │  - 请求路由 (Routing)                                         │  │
│  │  - 日志监控 (Logging/Metrics)                                 │  │
│  └──────────────────────────────────────────────────────────────┘  │
└────────────────────────────┼────────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────────┐
│                    Udify Core 引擎层 (Core Engine)                   │
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌───────────┐ │
│  │  感知层      │  │  认知层      │  │  规划层      │  │  执行层    │ │
│  │ Perception  │  │ Cognition   │  │  Planning   │  │ Execution │ │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └─────┬─────┘ │
│         │                │                │               │       │
│         └────────────────┴────────────────┴───────────────┘       │
│                                      │                              │
│                           ┌──────────┴──────────┐                  │
│                           │     评估层          │                  │
│                           │   Evaluation       │                  │
│                           └─────────────────────┘                  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                     记忆系统 (Memory System)                   │  │
│  │  - 用户偏好向量                                                │  │
│  │  - 内容知识图谱                                                │  │
│  │  - 执行历史                                                    │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                   事件总线 (Event Bus)                         │  │
│  │  - 异步任务调度                                                │  │
│  │  - 状态变更通知                                                │  │
│  │  - 跨模块通信                                                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                             │
┌────────────────────────────┼────────────────────────────────────────┐
│                    基础设施层 (Infrastructure Layer)                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ PostgreSQL│  │  Redis   │  │ Object   │  │ LLM      │            │
│  │ (主数据库)│  │ (缓存)   │  │ Storage  │  │ Providers│            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
│                                                                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Celery   │  │ Docker   │  │ K8s      │  │ Monitoring│            │
│  │ (任务队列)│  │ (容器)   │  │ (编排)   │  │ (监控)    │            │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 模块职责

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **感知层** | 解析原始内容，提取结构和语义 | 内容文件包 | 内容图谱（CDL） |
| **认知层** | 理解用户意图，管理偏好和记忆 | 用户输入 + 内容图谱 | 结构化意图 + 偏好更新 |
| **规划层** | 生成可执行的改造计划 | 结构化意图 + 内容图谱 | 改造计划 DAG |
| **执行层** | 执行改造计划，调用工具链 | 改造计划 DAG | 改造后的内容 + 日志 |
| **评估层** | 评估改造质量 | 改造后内容 + 原始意图 | 质量报告 + 通过/失败 |
| **记忆系统** | 存储和学习用户偏好、内容知识 | 交互数据 + 反馈 | 个性化模型 + 推荐 |
| **事件总线** | 协调异步通信 | 事件 | 事件分发 |

---

## 3. Udify Core 详细架构

### 3.1 感知层（Perception Layer）

**职责**：将原始内容解析为媒介无关的内容描述语言（CDL）。

**架构**：

```
原始内容文件包
    │
    ▼
┌─────────────────────────────────────────┐
│          文件类型识别器                  │
│  (File Type Identifier)                 │
│  - 基于魔数和文件头识别格式              │
└──────────────────┬──────────────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌─────────────────┐  ┌─────────────────┐
│  引擎/格式检测   │  │  通用文件解析    │
│  (Unity/Unreal/ │  │  (ZIP/Archive/  │
│   Godot/Custom) │  │   Image/Audio)  │
└────────┬────────┘  └────────┬────────┘
         │                    │
         └─────────┬──────────┘
                   ▼
┌─────────────────────────────────────────┐
│          媒介特定解析器                  │
│  (Media-Specific Parser)                │
│  插件化架构，每种媒介一个解析器           │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          结构分析器                      │
│  (Structure Analyzer)                   │
│  - 提取依赖关系                          │
│  - 识别关键元素                          │
│  - 构建内容图                            │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          语义理解器                      │
│  (Semantic Understanding)               │
│  - LLM 分析内容含义                      │
│  - 生成人类可读的描述                    │
│  - 提取风格、主题、情绪                  │
└──────────────────┬──────────────────────┘
                   │
                   ▼
            CDL (Content Description Language)
```

**关键设计**：
- **插件化解析器**：新媒介类型通过实现 `MediaParser` 接口加入系统，无需修改核心代码。
- **增量解析**：大文件支持增量解析，避免内存爆炸。
- **缓存机制**：解析结果缓存，避免重复解析相同内容。

### 3.2 认知层（Cognition Layer）

**职责**：理解用户意图，管理用户记忆和偏好。

**架构**：

```
用户输入（自然语言/语音/表单）
    │
    ▼
┌─────────────────────────────────────────┐
│          输入预处理                      │
│  (Input Preprocessing)                  │
│  - 文本清洗                             │
│  - 语言检测                             │
│  - 实体链接（游戏名、风格名等）          │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          意图识别器                      │
│  (Intent Recognizer)                    │
│  - 意图分类（改造类型）                  │
│  - 实体提取（数值、参考）                │
│  - 约束解析（预算、时间）                │
│  - 冲突检测                             │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          参考解析器                      │
│  (Reference Resolver)                   │
│  - "像魂系" → 特征向量                  │
│  - "更黑暗" → 风格参数                  │
│  - 链接到知识图谱中的具体概念            │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          记忆查询                        │
│  (Memory Query)                         │
│  - 检索用户历史偏好                      │
│  - 检索相似用户的行为模式                │
│  - 检索内容相关的社区知识                │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          意图增强器                      │
│  (Intent Enricher)                      │
│  - 结合用户偏好补全隐含需求              │
│  - 添加个性化约束                        │
│  - 生成多个候选意图变体                  │
└──────────────────┬──────────────────────┘
                   │
                   ▼
            结构化意图（Structured Intent）
```

**记忆系统子架构**：

```
┌─────────────────────────────────────────┐
│           记忆系统                       │
│  (Memory System)                        │
├─────────────────────────────────────────┤
│                                         │
│  ┌─────────────┐    ┌─────────────┐    │
│  │  短期记忆    │    │  长期记忆    │    │
│  │  (Session)  │───→│  (Persistent)│    │
│  │  - 当前对话  │    │  - 偏好向量  │    │
│  │  - 近期行为  │    │  - 历史记录  │    │
│  └─────────────┘    └─────────────┘    │
│         │                    │          │
│         ▼                    ▼          │
│  ┌─────────────┐    ┌─────────────┐    │
│  │  情境记忆    │    │  语义记忆    │    │
│  │  (Context)  │    │  (Semantic)  │    │
│  │  - 时间地点  │    │  - 审美模型  │    │
│  │  - 设备环境  │    │  - 知识关联  │    │
│  └─────────────┘    └─────────────┘    │
│                                         │
│  ┌─────────────────────────────────┐   │
│  │        记忆更新机制              │   │
│  │  - 显式反馈（评分、选择）        │   │
│  │  - 隐式反馈（行为、停留时间）    │   │
│  │  - 对抗性更新（纠正错误）        │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
```

### 3.3 规划层（Planning Layer）

**职责**：将结构化意图和内容图谱转化为可执行的改造计划。

**架构**：

```
结构化意图 + 内容图谱
    │
    ▼
┌─────────────────────────────────────────┐
│          目标分解器                      │
│  (Goal Decomposer)                      │
│  - 将高层意图分解为子目标                │
│  - 识别目标之间的依赖关系                │
│  - 生成目标树（Goal Tree）               │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          操作检索                        │
│  (Operation Retrieval)                  │
│  - 根据目标从操作库检索候选操作          │
│  - 基于语义相似性排序                    │
│  - 考虑前置条件和后置效果                │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          计划生成器                      │
│  (Plan Generator)                       │
│  - LLM 生成候选计划                      │
│  - 基于规则的兜底方案                    │
│  - 生成多个候选计划（多样性）            │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          计划验证器                      │
│  (Plan Validator)                       │
│  - 静态检查（依赖满足、资源足够）        │
│  - 模拟执行（预测输出）                  │
│  - 冲突检测（操作之间的不一致）          │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          计划优化器                      │
│  (Plan Optimizer)                       │
│  - 成本最小化（时间、计算、金钱）        │
│  - 并行化（识别可并行操作）              │
│  - 回滚策略（为每个节点设计逆向操作）    │
└──────────────────┬──────────────────────┘
                   │
                   ▼
            改造计划 DAG（Transformation Plan）
```

**操作库设计**：

```python
# 原子操作的抽象接口
class AtomicOperation(ABC):
    """所有原子操作的基类"""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """操作名称"""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> Schema:
        """输入参数的模式"""
        pass
    
    @property
    @abstractmethod
    def output_schema(self) -> Schema:
        """输出产物的模式"""
        pass
    
    @property
    @abstractmethod
    def preconditions(self) -> List[Condition]:
        """前置条件"""
        pass
    
    @property
    @abstractmethod
    def postconditions(self) -> List[Condition]:
        """后置效果"""
        pass
    
    @abstractmethod
    def execute(self, inputs: Dict[str, Any], context: ExecutionContext) -> OperationResult:
        """执行操作"""
        pass
    
    @abstractmethod
    def rollback(self, result: OperationResult, context: ExecutionContext) -> None:
        """回滚操作"""
        pass
    
    @property
    def cost_model(self) -> CostModel:
        """成本模型（时间、计算资源）"""
        return CostModel.zero()
```

### 3.4 执行层（Execution Layer）

**职责**：安全、高效地执行改造计划。

**架构**：

```
改造计划 DAG
    │
    ▼
┌─────────────────────────────────────────┐
│          调度器                          │
│  (Scheduler)                            │
│  - 拓扑排序                             │
│  - 并行调度（无依赖的操作并行执行）      │
│  - 优先级调度（关键路径优先）            │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          沙箱执行器                      │
│  (Sandbox Executor)                     │
│  - Docker 容器隔离                      │
│  - 资源限制（CPU、内存、磁盘、网络）     │
│  - 超时控制                             │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          工具集成层                      │
│  (Tool Integration)                     │
│  - 外部工具调用（FFmpeg、AssetStudio等） │
│  - API 调用（云服务的图像/音频/视频API） │
│  - 脚本执行（Python、Bash）              │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          错误恢复                        │
│  (Error Recovery)                       │
│  - 重试（指数退避）                      │
│  - 备用方案（Fallback）                  │
│  - 回滚（Rollback）                      │
│  - 人工介入（Escalation）                │
└──────────────────┬──────────────────────┘
                   │
                   ▼
            执行结果 + 产物 + 日志
```

**执行状态机**：

```
          ┌─────────┐
          │ PENDING │
          └────┬────┘
               │ 调度器分配资源
               ▼
          ┌─────────┐
          │RUNNING  │
          └────┬────┘
               │
     ┌─────────┼─────────┐
     │         │         │
     ▼         ▼         ▼
┌────────┐ ┌────────┐ ┌────────┐
│SUCCESS │ │ FAILED │ │RETRYING│
└────┬───┘ └───┬────┘ └───┬────┘
     │         │          │
     │         ▼          │
     │    ┌────────┐      │
     │    │ROLLBACK│      │
     │    └───┬────┘      │
     │        │           │
     │        ▼           │
     │   ┌─────────┐      │
     └──→│COMPLETED│←─────┘
         └─────────┘
```

### 3.5 评估层（Evaluation Layer）

**职责**：多维度评估改造质量。

**评估管道**：

```
改造后内容 + 原始意图
    │
    ├──→ 完整性检查（文件齐全、可启动）
    │
    ├──→ 一致性检查（规则不冲突、资源引用正确）
    │
    ├──→ 意图对齐度（LLM 评估 + 规则匹配）
    │
    ├──→ 可玩性/可用性评估（启发式规则 + 基准对比）
    │
    └──→ 安全性检查（恶意代码、版权侵权）
         │
         ▼
    综合质量评分 + 详细报告
```

---

## 4. Udiface 平台架构

### 4.1 前端架构

```
Next.js App Router
├── app/
│   ├── (landing)/          # 营销页面
│   ├── (platform)/         # 主平台
│   │   ├── explore/        # 发现页
│   │   ├── project/[id]/   # 项目详情
│   │   ├── studio/         # 创作工作室
│   │   ├── profile/        # 个人中心
│   │   └── settings/       # 设置
│   └── api/                # API 路由
├── components/
│   ├── ui/                 # 基础组件
│   ├── forms/              # 表单组件
│   ├── media/              # 媒介预览组件
│   └── layout/             # 布局组件
├── lib/
│   ├── api.ts              # API 客户端
│   ├── auth.ts             # 认证逻辑
│   └── utils.ts            # 工具函数
└── hooks/
    ├── useProject.ts
    ├── useUser.ts
    └── useMutation.ts
```

### 4.2 后端服务

```
Udiface API (FastAPI)
├── routers/
│   ├── auth.py             # 认证
│   ├── users.py            # 用户管理
│   ├── projects.py         # 项目 CRUD
│   ├── content.py          # 内容管理
│   ├── search.py           # 搜索与发现
│   ├── payments.py         # 支付
│   ├── governance.py       # 社区治理
│   └── webhooks.py         # 外部集成
├── services/
│   ├── project_service.py
│   ├── user_service.py
│   ├── recommendation_service.py
│   └── payment_service.py
├── models/                  # SQLAlchemy 模型
└── tasks/                   # Celery 后台任务
```

### 4.3 关键功能模块

**内容发现系统**：
- **搜索**：全文搜索 + 向量搜索（语义相似性）+ 混合排序
- **推荐**：协同过滤 + 内容相似性 + 个性化偏好
- **策展**：官方精选 + 社区精选 + 算法趋势

**创作工作室**：
- **意图输入**：自然语言输入框 + 语音输入（未来）+ 模板选择
- **实时预览**：计划生成过程中的实时反馈
- **人工调整**：允许用户在自动计划基础上手动修改
- **版本管理**：Git-like 的版本控制，支持分叉和合并

---

## 5. Udiscipline 方法学框架

### 5.1 理论层

Udiscipline 不是单独的代码模块，而是**嵌入系统设计的理论框架**。

```
Udiscipline Framework
├── 理论基础 (Theory)
│   ├── 信息本体论      → 内容建模方式
│   ├── 进化论          → 生态设计原则
│   ├── 控制论          → 反馈机制设计
│   └── 美学理论        → 质量评估标准
├── 方法学 (Methodology)
│   ├── 感知方法论      → 如何理解内容
│   ├── 规划方法论      → 如何生成计划
│   ├── 评估方法论      → 如何判断质量
│   └── 演化方法论      → 如何持续改进
├── 评估标准 (Criteria)
│   ├── 完整性指标
│   ├── 一致性指标
│   ├── 创造性指标
│   └── 用户满意度指标
└── 伦理框架 (Ethics)
    ├── 版权与合理使用
    ├── 数据隐私
    ├── 内容安全
    └── 社区治理
```

### 5.2 代码中的体现

```python
# 示例：评估标准在代码中的体现
from udiscipline.aesthetics import AestheticModel
from udiscipline.ethics import CopyrightChecker

class QualityEvaluator:
    def __init__(self):
        self.aesthetic_model = AestheticModel()
        self.copyright_checker = CopyrightChecker()
    
    def evaluate(self, content: Content, intent: Intent) -> QualityReport:
        # 完整性（信息论）
        completeness = self.check_completeness(content)
        
        # 一致性（逻辑学）
        consistency = self.check_consistency(content)
        
        # 审美价值（美学）
        aesthetic_value = self.aesthetic_model.evaluate(content, intent)
        
        # 合法性（伦理学）
        legal_status = self.copyright_checker.check(content)
        
        return QualityReport(
            completeness=completeness,
            consistency=consistency,
            aesthetic_value=aesthetic_value,
            legal_status=legal_status
        )
```

---

## 6. 数据模型

### 6.1 核心实体关系图

```
┌─────────────┐       ┌─────────────┐       ┌─────────────┐
│    User     │       │   Project   │       │   Content   │
├─────────────┤       ├─────────────┤       ├─────────────┤
│ id          │──┐    │ id          │──┐    │ id          │
│ email       │  │    │ title       │  │    │ media_type  │
│ preferences │  └───→│ author_id   │  └───→│ project_id  │
│ reputation  │       │ content_id  │       │ cdl_data    │
│ created_at  │       │ status      │       │ files       │
└─────────────┘       │ tags        │       └─────────────┘
                      │ parent_id   │◄──────┐（版本分叉）
                      │ version     │       │
                      └─────────────┘       │
                             │              │
                             ▼              │
                      ┌─────────────┐       │
                      │  Intent     │       │
                      ├─────────────┤       │
                      │ id          │       │
                      │ user_id     │       │
                      │ raw_text    │       │
                      │ structured  │       │
                      │ status      │       │
                      └──────┬──────┘       │
                             │              │
                             ▼              │
                      ┌─────────────┐       │
                      │    Plan     │       │
                      ├─────────────┤       │
                      │ id          │       │
                      │ intent_id   │       │
                      │ dag_data    │       │
                      │ status      │       │
                      └──────┬──────┘       │
                             │              │
                             ▼              │
                      ┌─────────────┐       │
                      │ Execution   │       │
                      ├─────────────┤       │
                      │ id          │       │
                      │ plan_id     │       │
                      │ logs        │       │
                      │ result      │       │
                      └─────────────┘       │
                                            │
                      ┌─────────────┐       │
                      │  Feedback   │       │
                      ├─────────────┤       │
                      │ id          │       │
                      │ user_id     │       │
                      │ project_id  │◄──────┘
                      │ rating      │
                      │ comment     │
                      └─────────────┘
```

### 6.2 内容描述语言（CDL）Schema

```json
{
  "cdl_version": "1.0",
  "content": {
    "id": "uuid",
    "media_type": "game|music|video|novel",
    "format_version": "string",
    "metadata": {
      "title": "string",
      "description": "string",
      "tags": ["string"],
      "creation_date": "ISO8601",
      "source": "original|derivative"
    }
  },
  "structure": {
    "nodes": [
      {
        "id": "string",
        "type": "resource|mechanic|character|event|scene|track|chapter",
        "properties": {},
        "embedding": [0.1, 0.2, ...]
      }
    ],
    "edges": [
      {
        "source": "node_id",
        "target": "node_id",
        "type": "depends_on|triggers|contains|references|follows",
        "weight": 0.5
      }
    ]
  },
  "semantics": {
    "themes": ["string"],
    "mood": "string",
    "style": {
      "visual": {},
      "audio": {},
      "narrative": {}
    },
    "summary": "string"
  },
  "assets": [
    {
      "id": "string",
      "type": "texture|model|audio|script|text",
      "path": "string",
      "hash": "sha256",
      "size": 1024
    }
  ]
}
```

---

## 7. 关键接口与协议

### 7.1 内部 API（模块间通信）

```python
# 感知层接口
class PerceptionAPI:
    async def parse(self, file_package: FilePackage) -> ContentGraph:
        """解析内容文件包，返回内容图谱"""
        pass

# 认知层接口
class CognitionAPI:
    async def recognize_intent(self, user_input: str, context: UserContext) -> StructuredIntent:
        """识别用户意图"""
        pass
    
    async def query_memory(self, user_id: str, query: MemoryQuery) -> MemoryResult:
        """查询用户记忆"""
        pass

# 规划层接口
class PlanningAPI:
    async def generate_plan(self, intent: StructuredIntent, content: ContentGraph) -> TransformationPlan:
        """生成改造计划"""
        pass
    
    async def validate_plan(self, plan: TransformationPlan) -> ValidationResult:
        """验证计划可行性"""
        pass

# 执行层接口
class ExecutionAPI:
    async def execute_plan(self, plan: TransformationPlan, callback: ProgressCallback) -> ExecutionResult:
        """执行改造计划"""
        pass

# 评估层接口
class EvaluationAPI:
    async def evaluate(self, content: Content, intent: StructuredIntent) -> QualityReport:
        """评估内容质量"""
        pass
```

### 7.2 外部 API（第三方接入）

```yaml
# OpenAPI 3.0 规范（简化）
openapi: 3.0.0
info:
  title: Udify API
  version: 1.0.0
paths:
  /v1/projects:
    post:
      summary: 创建新魔改项目
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                source_content:
                  type: string
                  description: 原始内容的 URL 或文件 ID
                intent:
                  type: string
                  description: 用户的魔改意图描述
      responses:
        201:
          description: 项目创建成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Project'

  /v1/projects/{id}/plan:
    get:
      summary: 获取项目的改造计划
      responses:
        200:
          description: 返回改造计划
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TransformationPlan'

  /v1/projects/{id}/execute:
    post:
      summary: 执行改造计划
      responses:
        202:
          description: 执行已启动
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ExecutionJob'

  /v1/search:
    get:
      summary: 搜索魔改项目
      parameters:
        - name: q
          in: query
          schema:
            type: string
          description: 搜索查询（支持自然语言）
      responses:
        200:
          description: 搜索结果
```

### 7.3 事件协议

```python
# 核心事件类型
@dataclass
class Event:
    event_id: str
    event_type: str
    timestamp: datetime
    payload: Dict[str, Any]
    source: str

# 关键事件
class ContentParsed(Event):
    """内容解析完成"""
    event_type = "content.parsed"
    payload: {
        "content_id": str,
        "media_type": str,
        "node_count": int,
        "edge_count": int
    }

class IntentRecognized(Event):
    """意图识别完成"""
    event_type = "intent.recognized"
    payload: {
        "intent_id": str,
        "confidence": float,
        "categories": List[str]
    }

class PlanGenerated(Event):
    """计划生成完成"""
    event_type = "plan.generated"
    payload: {
        "plan_id": str,
        "step_count": int,
        "estimated_duration": int
    }

class StepCompleted(Event):
    """计划步骤完成"""
    event_type = "execution.step_completed"
    payload: {
        "execution_id": str,
        "step_id": str,
        "status": "success|failure|skipped",
        "duration": int
    }

class QualityEvaluated(Event):
    """质量评估完成"""
    event_type = "quality.evaluated"
    payload: {
        "project_id": str,
        "overall_score": float,
        "passed": bool
    }
```

---

## 8. 扩展性设计

### 8.1 水平扩展

**无状态服务**：API 服务器无状态，可通过负载均衡器水平扩展。

**任务队列**：Celery + Redis，工作节点可动态增减。

**数据库分片**：按用户 ID 或项目 ID 分片（Phase 3 后实施）。

**缓存层**：Redis 缓存热点数据，减轻数据库压力。

### 8.2 垂直扩展（新媒介类型）

添加新媒介类型只需：
1. 实现 `MediaParser` 接口（感知层插件）
2. 实现 `MediaGenerator` 接口（执行层插件）
3. 定义该媒介的 CDL 子集
4. 注册到操作库

```python
# 示例：添加"漫画"媒介类型
class MangaParser(MediaParser):
    def parse(self, file_package: FilePackage) -> ContentGraph:
        # 解析漫画文件（CBZ/CBR/PDF）
        # 提取页面、分镜、对话框、角色
        pass

class MangaGenerator(MediaGenerator):
    def generate(self, cdl: ContentGraph, output_path: Path) -> FilePackage:
        # 根据 CDL 生成漫画文件
        pass

# 注册
registry.register_parser("manga", MangaParser())
registry.register_generator("manga", MangaGenerator())
```

### 8.3 模型扩展

支持多种 LLM 后端：
- OpenAI API
- Anthropic API
- 本地模型（llama.cpp、vLLM）
- 未来模型

通过统一的 `LLMProvider` 接口切换：

```python
class LLMProvider(ABC):
    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> str:
        pass
    
    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        pass
```

---

## 9. 安全与隐私架构

### 9.1 内容安全

```
用户上传内容
    │
    ▼
┌─────────────────┐
│ 病毒扫描        │
│ (ClamAV)        │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 版权检测        │
│ (指纹匹配)      │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 恶意内容检测    │
│ (AI 分类器)     │
└────────┬────────┘
         │
         ▼
    安全/不安全
```

### 9.2 数据隐私

- **数据隔离**：用户数据严格隔离，跨用户数据不可见
- **最小权限**：每个组件只访问必要的数据
- **加密**：传输层 TLS，存储层 AES-256
- **审计日志**：所有数据访问记录审计日志
- **GDPR/CCPA 合规**：支持数据导出和删除请求

### 9.3 沙箱安全

- Docker 容器隔离执行环境
- 无网络访问（除非显式声明）
- 资源配额限制（CPU、内存、磁盘、时间）
- 只读挂载（原始内容不可修改）
- 输出扫描（防止沙箱逃逸）

---

## 10. 部署架构

### 10.1 开发环境

```
开发者机器
├── Docker Compose
│   ├── app (FastAPI + Next.js dev server)
│   ├── postgres
│   ├── redis
│   ├── minio (S3 compatible)
│   └── celery-worker
└── Local LLM (可选，用于离线开发)
```

### 10.2 生产环境（初期）

```
Cloud Provider (AWS/GCP)
├── CDN (CloudFront/CloudFlare)
│   └── 静态资源、用户上传文件
├── Load Balancer
│   └── API 服务器集群 (ECS/EKS)
├── PostgreSQL (RDS/Cloud SQL)
├── Redis (ElastiCache/MemoryStore)
├── S3 Bucket
│   └── 文件存储
├── Lambda/Cloud Functions
│   └── 轻量级任务（缩略图生成、格式转换）
└── GPU Instances (EC2/GCE)
    └── LLM 推理、媒体处理
```

### 10.3 持续部署

```
Git Push
    │
    ▼
GitHub Actions
    ├── 代码检查 (Ruff, MyPy)
    ├── 单元测试 (pytest)
    ├── 集成测试
    ├── 构建 Docker 镜像
    └── 部署到 Staging
         │
         ▼
    人工确认
         │
         ▼
    部署到 Production
```

---

## 附录：架构决策记录（ADR）

### ADR-001: 使用 Python 作为主要后端语言

**状态**: 已接受

**背景**: 需要选择后端主语言。候选：Python、Node.js、Go、Rust。

**决策**: 使用 Python 3.12+。

**理由**:
- AI/ML 生态最丰富（PyTorch、Transformers、LangChain）
- 开发速度快，适合 MVP 阶段
- 类型提示（Type Hints）和 MyPy 提供足够的类型安全

**权衡**:
- 性能不如 Go/Rust，但计算密集型任务（LLM 推理、媒体处理）由外部服务/GPU 处理，Python 只负责编排
- 并发性能一般，但使用异步（asyncio）和 Celery 可以缓解

### ADR-002: 使用 Next.js 作为前端框架

**状态**: 已接受

**背景**: 需要选择前端框架。候选：Next.js、Remix、Vue、Svelte。

**决策**: 使用 Next.js 14+ (App Router)。

**理由**:
- React 生态最丰富
- SSR/ISR 对 SEO 和首屏性能友好
- 与 Vercel 生态集成好

### ADR-003: 事件驱动架构

**状态**: 已接受

**背景**: 模块间通信方式选择。候选：同步调用、消息队列、事件总线。

**决策**: 使用事件总线（Redis Pub/Sub + 持久化队列）。

**理由**:
- 模块解耦，支持独立演进
- 支持重放和审计
- 易于扩展新消费者

**权衡**:
- 调试复杂度增加（需要追踪事件流）
- 一致性保证需要额外设计（ saga 模式）

### ADR-004: 多模型 LLM 策略

**状态**: 已接受

**背景**: LLM 选择。候选：单一模型、多模型切换。

**决策**: 多模型策略，根据任务选择最优模型。

**理由**:
- 不同任务需要不同能力（创意生成 vs 代码生成 vs 评估）
- 成本优化（简单任务用便宜模型，复杂任务用强模型）
- 避免供应商锁定

**策略**:
- 复杂推理/创意：Claude/GPT-4
- 简单分类/提取：轻量级模型（Haiku/GPT-3.5）
- 本地/敏感任务：本地模型（llama.cpp）
- 嵌入：专用嵌入模型

---

> **"架构不是画出来的，是长出来的。这个架构是种子，随着系统的生长，它会自然演化。我们的任务是保持根基的清晰，让枝叶自由伸展。"**
>
> —— Udify 架构哲学
