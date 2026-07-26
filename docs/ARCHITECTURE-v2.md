<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 架构设计评审（Architecture Design Review）

> **版本**: v2.0 | **日期**: 2026-04-27 | **状态**: 评审中
>
> **评审依据**: RESEARCH.md 深度调研报告 | **评审范围**: 全系统架构重新审视与细化

---

## 目录

1. [评审摘要：关键变更](#1-评审摘要关键变更)
2. [系统架构总览](#2-系统架构总览)
3. [核心数据层：内容描述语言（CDL）](#3-核心数据层内容描述语言cdl)
4. [Udify Core 引擎层](#4-udify-core-引擎层)
   - 4.1 [感知层（Perception Layer）](#41-感知层perception-layer)
   - 4.2 [认知层（Cognition Layer）](#42-认知层cognition-layer)
   - 4.3 [规划层（Planning Layer）](#43-规划层planning-layer)
   - 4.4 [执行层（Execution Layer）](#44-执行层execution-layer)
   - 4.5 [评估层（Evaluation Layer）](#45-评估层evaluation-layer)
5. [记忆系统（Memory System）](#5-记忆系统memory-system)
6. [事件总线与消息协议](#6-事件总线与消息协议)
7. [工具层（Tool Layer）](#7-工具层tool-layer)
8. [Udiface 平台架构](#8-udiface-平台架构)
9. [安全架构](#9-安全架构)
10. [部署与运维架构](#10-部署与运维架构)
11. [架构决策记录（ADR）v2](#11-架构决策记录adr-v2)
12. [风险矩阵与技术债务](#12-风险矩阵与技术债务)

---

## 1. 评审摘要：关键变更

### 1.1 从 v1.0 到 v2.0 的核心调整

| 领域 | v1.0 设计 | v2.0 调整 | 调研依据 |
|------|----------|----------|---------|
| **代码解析** | 自定义解析器 | **Tree-sitter + Roslyn** | Tree-sitter 支持 50+ 语言增量解析；Roslyn 是 C# 语义分析的唯一选择 |
| **输出格式** | 完整文件重写 | **AST Diff / Patch** | Diff 节省 token、精确、易验证、易回滚（RESEARCH 3.5） |
| **工作流引擎** | Celery | **Prefect** | Prefect 原生支持 DAG 可视化、数据血缘、版本化（RESEARCH 1.4） |
| **图存储** | PostgreSQL JSONB | **Neo4j + PostgreSQL** | 内容图谱需要复杂图查询，Neo4j 是标准（RESEARCH 2.6） |
| **LLM 编排** | 自建 | **LangChain + MCP** | MCP 是 Anthropic 的开放工具调用标准（RESEARCH 3.3） |
| **前端 DAG** | 自建 | **ReactFlow** | ComfyUI 同款，行业标准（RESEARCH 1.4） |
| **版本控制** | Git | **DVC + Git** | DVC 专为 ML/大文件设计（RESEARCH 5.2） |
| **沙箱** | Docker | **gVisor** | 防容器逃逸，处理不可信用户上传（RESEARCH 5.2） |
| **规划算法** | LLM 直接生成 | **MCTS + LLM 价值函数** | AlphaGo 模式，搜索 + 启发（RESEARCH 5.1 P4） |
| **操作接口** | 自定义 | **MCP (Model Context Protocol)** | 标准化工具调用，生态兼容（RESEARCH 3.3） |

### 1.2 架构哲学更新

v1.0: "媒介无关的抽象层 + 媒介特定的实现层"
v2.0: **"Diff-First, Tool-Centric, Human-in-the-Loop"**

- **Diff-First**: 系统输出的是变换差异（patch），不是完整重写
- **Tool-Centric**: LLM 调度工具，不替代工具
- **Human-in-the-Loop**: 复杂任务必须有人类确认点

---

## 2. 系统架构总览

### 2.1 分层架构图

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              用户界面层 (Presentation Layer)                           │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │   Web App    │  │  CLI Tool    │  │   API/SDK    │  │  Browser Ext │              │
│  │ (Next.js 15) │  │  (Python)    │  │  (REST/GRPC) │  │  (Future)    │              │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘              │
└─────────┼─────────────────┼─────────────────┼─────────────────┼──────────────────────┘
          │                 │                 │                 │
          └─────────────────┴────────┬────────┴─────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                         Udiface API 网关层 (API Gateway)                             │
│  ┌─────────────────────────────────┼─────────────────────────────────────────────┐  │
│  │  Auth (OAuth2/OIDC)             │ Rate Limit (Token Bucket)                    │  │
│  │  Routing                        │ Load Balancing                               │  │
│  │  Request/Response Validation    │ Circuit Breaker                              │  │
│  │  Observability (OTel)           │ Audit Logging                                │  │
│  └─────────────────────────────────┴─────────────────────────────────────────────┘  │
└────────────────────────────────────┼─────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                      Udify Core 引擎层 (Core Engine)                                 │
│                                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │   感知层      │  │   认知层      │  │   规划层      │  │   执行层      │            │
│  │  Perception  │──│  Cognition   │──│  Planning    │──│  Execution   │            │
│  │              │  │              │  │              │  │              │            │
│  │ • Parse      │  │ • Intent     │  │ • Decompose  │  │ • Schedule   │            │
│  │ • Extract    │  │ • Reference  │  │ • Search     │  │ • Sandbox    │            │
│  │ • Analyze    │  │ • Memory     │  │ • Generate   │  │ • Execute    │            │
│  │ • Embed      │  │ • Enrich     │  │ • Validate   │  │ • Recover    │            │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘            │
│         │                 │                 │                 │                    │
│         └─────────────────┴─────────────────┴─────────────────┘                    │
│                                     │                                                │
│                          ┌──────────┴──────────┐                                   │
│                          │     评估层           │                                   │
│                          │   Evaluation       │                                   │
│                          │                    │                                   │
│                          │ • Completeness     │                                   │
│                          │ • Consistency      │                                   │
│                          │ • Intent Alignment │                                   │
│                          │ • Safety           │                                   │
│                          └──────────┬──────────┘                                   │
│                                     │                                                │
│  ┌──────────────────────────────────┼──────────────────────────────────────────┐   │
│  │                        记忆系统 (Memory System)                               │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │   │
│  │  │ User Pref   │  │ Content KG  │  │ Template Lib│  │ Execution   │         │   │
│  │  │ (Vectors)   │  │ (Neo4j)     │  │ (Versioned) │  │ History     │         │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘         │   │
│  └──────────────────────────────────┴──────────────────────────────────────────┘   │
│                                                                                      │
│  ┌──────────────────────────────────────────────────────────────────────────────┐  │
│  │                      事件总线 (Event Bus - Redis Streams)                      │  │
│  │  • Async Task Scheduling  • State Change Notifications  • Cross-Module Comms  │  │
│  └──────────────────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────┼─────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                        工具层 (Tool Layer - MCP Protocol)                            │
│                                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │  File System │  │  AST Engine  │  │  External    │  │  Media       │            │
│  │  (DVC+Git)   │  │(Tree-sitter  │  │  Tools       │  │  Processors  │            │
│  │              │  │ /Roslyn)     │  │  (AssetStudio│  │  (FFmpeg/    │            │
│  │              │  │              │  │   UABE etc.) │  │   ImageMagick│            │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘            │
└────────────────────────────────────┼─────────────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼─────────────────────────────────────────────────┐
│                     基础设施层 (Infrastructure Layer)                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ PostgreSQL   │  │ Neo4j        │  │ Redis        │  │ Object Store │            │
│  │ (Metadata)   │  │ (Graph DB)   │  │ (Cache/Queue)│  │ (S3/MinIO)   │            │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐            │
│  │ LLM Provider │  │ Prefect      │  │ gVisor       │  │ Monitoring   │            │
│  │ (Multi)      │  │ (Workflow)   │  │ (Sandbox)    │  │ (Prom+Graf)  │            │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘            │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心数据流

```
用户意图输入
    │
    ▼
[认知层] ──RAG──→ [记忆系统] 
    │                  │
    ▼                  ▼
结构化意图 ←────── 偏好增强
    │
    ▼
[感知层] ──CDL──→ [Neo4j 知识图谱]
    │                  │
    ▼                  ▼
内容图谱 ←────── 语义检索
    │
    ▼
[规划层] ──MCTS──→ [操作库]
    │                  │
    ▼                  ▼
改造计划(Patch DAG) ←── 候选操作
    │
    ▼
[执行层] ──MCP──→ [工具层]
    │                  │
    ▼                  ▼
执行日志 ←────── 工具调用结果
    │
    ▼
[评估层] ──规则──→ [质量报告]
    │                  │
    ▼                  ▼
通过/失败 ←────── 决策
    │
    ├──→ 失败 → [回滚] → [重试] → [人工介入]
    │
    └──→ 通过 → [Udiface 发布] → [用户反馈] → [记忆更新]
```

---

## 3. 核心数据层：内容描述语言（CDL）

### 3.1 CDL 设计原则

CDL 是 Udify 的**中间表示（IR）**，类似于 LLVM IR 在编译器中的地位。

**核心原则**：
1. **媒介无关**：不依赖于任何具体媒介的格式
2. **图原生**：基于图的结构表示（节点+边），不是树或文档
3. **可嵌入**：支持向量嵌入，用于语义搜索
4. **可差异**：支持 Diff/Patch 操作（RESEARCH 5.1 P3）
5. **可验证**：支持 Schema 验证和一致性检查

### 3.2 CDL Schema 详细定义

```yaml
# CDL v2.0 Schema
# 使用 YAML 表示便于人类阅读，实际序列化为 JSON/Protobuf

$schema: "https://udify.dev/schemas/cdl/2.0"
$id: "cdl://content-graph"

type: object
required: [version, content_id, media_type, metadata, graph, assets]

properties:
  version:
    type: string
    const: "2.0.0"
    description: "CDL 版本号，遵循 SemVer"

  content_id:
    type: string
    format: uuid
    description: "内容全局唯一标识"

  media_type:
    type: string
    enum: [game, music, video, novel, comic, unknown]
    description: "媒介类型"

  source:
    type: object
    required: [path, original_format]
    properties:
      path:
        type: string
        description: "原始内容文件路径（相对路径）"
      original_format:
        type: string
        description: "原始格式标识（如 'unity-2022.3', 'rpgmv-1.6.2'）"
      hash:
        type: string
        pattern: "^[a-f0-9]{64}$"
        description: "原始内容 SHA-256"
      size:
        type: integer
        description: "原始内容大小（字节）"

  metadata:
    type: object
    properties:
      title:
        type: [string, "null"]
      description:
        type: [string, "null"]
      version:
        type: [string, "null"]
      author:
        type: [string, "null"]
      tags:
        type: array
        items: { type: string }
      created_at:
        type: string
        format: date-time
      
      # 游戏特有
      engine:
        type: [string, "null"]
        enum: [unity, unreal, godot, rpg_maker, game_maker, custom, unknown]
      engine_version:
        type: [string, "null"]
      platform:
        type: array
        items:
          type: string
          enum: [pc, mac, linux, android, ios, web, switch, ps, xbox]

  graph:
    type: object
    required: [nodes, edges]
    properties:
      nodes:
        type: array
        items:
          $ref: "#/definitions/Node"
      edges:
        type: array
        items:
          $ref: "#/definitions/Edge"

  assets:
    type: array
    items:
      $ref: "#/definitions/Asset"

  semantics:
    type: object
    properties:
      themes:
        type: array
        items: { type: string }
      mood:
        type: [string, "null"]
      genre:
        type: [string, "null"]
      style_profile:
        type: object
        description: "风格参数向量，用于相似性计算"
        additionalProperties: { type: number }
      summary:
        type: [string, "null"]
        maxLength: 1000

      # 游戏特有语义
      game_genre:
        type: [string, "null"]
        enum: [rpg, fps, platformer, strategy, puzzle, roguelike, metroidvania, souls_like, visual_novel, other]
      perspective:
        type: [string, "null"]
        enum: [first_person, third_person, top_down, side_scrolling, isometric, other]
      pacing:
        type: [string, "null"]
        enum: [slow, moderate, fast, variable]
      difficulty_curve:
        type: [string, "null"]
        enum: [flat, linear, exponential, stepped, adaptive]

definitions:
  Node:
    type: object
    required: [id, type, name]
    properties:
      id:
        type: string
        format: uuid
      type:
        type: string
        enum:
          # 通用
          - resource
          - container
          # 游戏
          - mechanic
          - level
          - character
          - item
          - event
          - dialogue
          - quest
          - skill
          - buff
          # 音乐
          - track
          - chord_progression
          - melody
          - rhythm
          - instrument
          # 视频
          - scene
          - shot
          - transition
          - subtitle
          # 小说
          - chapter
          - plot_point
          - setting
          - theme
          - character_arc
      name:
        type: string
        maxLength: 256
      properties:
        type: object
        additionalProperties: true
        description: "类型特定的属性"
      embedding:
        type: array
        items: { type: number }
        description: "语义嵌入向量"
      source_refs:
        type: array
        items:
          type: object
          properties:
            asset_id:
              type: string
              format: uuid
            offset:
              type: integer
            length:
              type: integer
        description: "指向原始资源的引用"
      confidence:
        type: number
        minimum: 0
        maximum: 1
        description: "节点提取置信度"

  Edge:
    type: object
    required: [id, source, target, type]
    properties:
      id:
        type: string
        format: uuid
      source:
        type: string
        format: uuid
        description: "源节点 ID"
      target:
        type: string
        format: uuid
        description: "目标节点 ID"
      type:
        type: string
        enum:
          - depends_on      # 依赖
          - contains        # 包含
          - references      # 引用
          - triggers        # 触发
          - requires        # 需要
          - excludes        # 互斥
          - similar_to      # 相似
          - precedes        # 先于
          - follows         # 跟随
          - transforms_to   # 变换为（用于计划）
      weight:
        type: number
        minimum: 0
        maximum: 1
        default: 1.0
        description: "关系强度"
      properties:
        type: object
        additionalProperties: true

  Asset:
    type: object
    required: [id, path, type, format, size]
    properties:
      id:
        type: string
        format: uuid
      path:
        type: string
        description: "相对于内容根目录的路径"
      type:
        type: string
        enum:
          - texture
          - model
          - audio
          - video
          - script
          - config
          - shader
          - font
          - animation
          - scene
          - material
          - prefab
          - archive
          - unknown
      format:
        type: string
        description: "文件扩展名（如 png, fbx, wav, cs, json）"
      size:
        type: integer
        description: "文件大小（字节）"
      hash:
        type: string
        pattern: "^[a-f0-9]{64}$"
        description: "SHA-256"
      
      # 媒介特定元数据
      dimensions:
        type: object
        properties:
          width: { type: integer }
          height: { type: integer }
          depth: { type: integer }
      duration:
        type: number
        description: "音频/视频时长（秒）"
      sample_rate:
        type: integer
        description: "音频采样率"
      bitrate:
        type: integer
        description: "比特率"
```

### 3.3 CDL Diff/Patch 格式

**核心创新**：CDL 支持差异操作，这是 v2.0 最重要的设计。

```yaml
# CDL Patch v1.0
# 表示对 ContentGraph 的一组变换操作

patch_version: "1.0"
target_content_id: "uuid-of-original"
parent_patch: "uuid-of-parent"  # 支持链式补丁

operations:
  # 操作 1: 添加节点
  - type: add_node
    node:
      id: "new-node-uuid"
      type: mechanic
      name: "Hardcore Mode"
      properties:
        description: "Permadeath with increased enemy damage"
        death_penalty: "reset_all"
      embedding: [0.1, -0.2, ...]

  # 操作 2: 修改节点属性
  - type: modify_node
    node_id: "existing-node-uuid"
    property_changes:
      health:
        old: 100
        new: 150
      damage_multiplier:
        old: 1.0
        new: 1.5
    reason: "Increase difficulty to Dark Souls level"

  # 操作 3: 删除节点
  - type: remove_node
    node_id: "node-to-remove-uuid"
    cascade: false  # 是否级联删除关联边

  # 操作 4: 添加边
  - type: add_edge
    edge:
      id: "new-edge-uuid"
      source: "player-node"
      target: "new-node-uuid"
      type: depends_on

  # 操作 5: 修改资源文件
  - type: modify_asset
    asset_id: "asset-uuid"
    file_patch:
      type: json_patch  # 或 text_patch, binary_patch, ast_patch
      operations:
        - op: replace
          path: /enemies/0/health
          value: 200

  # 操作 6: 替换整个资源
  - type: replace_asset
    asset_id: "asset-uuid"
    new_hash: "sha256-of-new-file"
    new_size: 1024

  # 操作 7: 添加新资源
  - type: add_asset
    asset:
      id: "new-asset-uuid"
      path: "Resources/Textures/dark_souls_style.png"
      type: texture
      format: png
      size: 2048
      hash: "sha256..."

metadata:
  generated_by: "planner-v2.1"
  generation_time: "2026-04-27T10:00:00Z"
  estimated_impact:
    nodes_added: 3
    nodes_modified: 5
    nodes_removed: 1
    assets_modified: 2
    risk_level: medium  # low, medium, high, critical
```

**Patch 的优势**：
1. **可组合**：多个 Patch 可以串行或并行应用
2. **可回滚**：每个 Patch 有对应的逆向 Patch
3. **可冲突检测**：两个 Patch 如果修改同一节点/属性，就会冲突
4. **可审查**：人类可以阅读 Patch 内容，理解系统做了什么
5. **版本控制友好**：Patch 本身就是 Git diff 的超集

---

## 4. Udify Core 引擎层

### 4.1 感知层（Perception Layer）

**职责**：将原始内容解析为 CDL。

**架构细化**：

```
原始内容
    │
    ▼
┌──────────────────────────────────────────────┐
│  1. 文件系统分析器                            │
│     - 递归扫描目录结构                        │
│     - 识别文件类型（魔数 + 扩展名）            │
│     - 计算哈希值                              │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  2. 引擎检测器 (CompositeEngineDetector)      │
│     - UnityDetector (UnityFS/globalgamemanagers│
│     - UnrealDetector (.pak/.uproject)         │
│     - GodotDetector (project.godot/.pck)      │
│     - RPGMakerDetector (www/index.html)       │
│     - GameMakerDetector (.yyp/.gmk)           │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  3. 资源提取器 (ResourceExtractor)            │
│     策略：                                     │
│     • 源码项目 → 直接读取文件                  │
│     • 构建产物 → 调用外部工具：                │
│       - Unity: AssetStudio CLI / AssetRipper  │
│       - Unreal: UE Viewer / FModel            │
│       - Godot: 内置导入器                      │
│       - RPG Maker: 直接读取 JSON/二进制        │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  4. 结构解析器                                 │
│     • 配置文件: JSON Schema / Pydantic         │
│     • 脚本代码: Tree-sitter / Roslyn           │
│     • 二进制资源: 格式专用解析器               │
│     • 输出: 原始 AST（不同语言的统一包装）     │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  5. 语义提取器                                 │
│     • 静态分析: 提取变量名、函数名、类名       │
│     • LLM 增强: 生成人类可读描述               │
│     • 嵌入生成: 为每个节点生成向量             │
│     • 图构建: 建立节点间的关系                 │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
              CDL (ContentGraph)
```

**关键技术点**：

1. **Tree-sitter 集成**：
```python
from tree_sitter import Language, Parser

class TreeSitterAnalyzer:
    """基于 Tree-sitter 的代码分析器"""
    
    def __init__(self, language_name: str):
        self.parser = Parser()
        self.language = Language(f"build/{language_name}.so", language_name)
        self.parser.set_language(self.language)
    
    def parse_file(self, file_path: Path) -> ASTNode:
        """解析文件为 AST"""
        with open(file_path, 'rb') as f:
            tree = self.parser.parse(f.read())
        return self._convert_to_cdl_nodes(tree.root_node)
    
    def query(self, ast: ASTNode, query_string: str) -> List[ASTNode]:
        """使用 Tree-sitter 查询语言搜索 AST"""
        query = self.language.query(query_string)
        return query.captures(ast)

# 示例：查找所有类定义
# query = """
# (class_declaration
#   name: (identifier) @class.name) @class.def
# """
```

2. **Roslyn 集成（C# 分析）**：
```python
import subprocess
import json

class RoslynAnalyzer:
    """通过 CLI 调用 Roslyn 分析器"""
    
    def analyze_project(self, project_path: Path) -> Dict:
        """分析 C# 项目，返回类型信息、依赖关系"""
        result = subprocess.run(
            ['roslyn-analyzer', str(project_path), '--format=json'],
            capture_output=True,
            text=True
        )
        return json.loads(result.stdout)
    
    def get_semantic_model(self, file_path: Path) -> SemanticModel:
        """获取语义模型（类型推断、符号解析）"""
        # 通过 Roslyn 服务获取语义信息
        pass
```

3. **增量解析**：
```python
class IncrementalParser:
    """增量解析器，只处理变更的文件"""
    
    def __init__(self, cache_dir: Path):
        self.cache = ParseCache(cache_dir)
    
    def parse(self, content_path: Path, previous_graph: Optional[ContentGraph] = None) -> ContentGraph:
        changed_files = self._detect_changes(content_path, previous_graph)
        
        if not changed_files:
            return previous_graph  # 无变更，直接返回缓存
        
        # 只解析变更的文件
        for file in changed_files:
            new_ast = self._parse_file(file)
            self._update_graph(previous_graph, file, new_ast)
        
        return previous_graph
```

### 4.2 认知层（Cognition Layer）

**职责**：将用户意图转化为机器可执行的结构化意图。

**状态机**：

```
                    ┌──────────────┐
         ┌─────────│   START      │
         │         │ (等待输入)    │
         │         └──────┬───────┘
         │                │ 收到用户输入
         │                ▼
         │         ┌──────────────┐
         │         │  PARSING     │
         │         │ (解析文本)    │
         │         └──────┬───────┘
         │                │
         │    ┌───────────┼───────────┐
         │    │           │           │
         │    ▼           ▼           ▼
         │ ┌──────┐  ┌────────┐  ┌────────┐
         │ │文本  │  │语音    │  │结构化  │
         │ │输入  │  │(未来)  │  │表单    │
         │ └──┬───┘  └───┬────┘  └───┬────┘
         │    │          │           │
         │    └──────────┴───────────┘
         │                │
         │                ▼
         │         ┌──────────────┐
         │         │ CLASSIFYING  │
         │         │ (意图分类)    │
         │         └──────┬───────┘
         │                │
         │                ▼
         │         ┌──────────────┐
         │         │  EXTRACTING  │
         │         │ (实体/约束提取)│
         │         └──────┬───────┘
         │                │
         │                ▼
         │         ┌──────────────┐
         │         │  RESOLVING   │
         │         │ (参考解析)    │
         │         └──────┬───────┘
         │                │
         │                ▼
         │         ┌──────────────┐
         │         │   ENRICHING  │◄──────────┐
         │         │ (记忆增强)    │           │
         │         └──────┬───────┘           │
         │                │                   │
         │                ▼                   │
         │         ┌──────────────┐           │
         │         │  VALIDATING  │           │
         │         │ (冲突检测)    │           │
         │         └──────┬───────┘           │
         │                │                   │
         │    ┌───────────┴───────────┐       │
         │    │                       │       │
         │    ▼                       ▼       │
         │ ┌────────┐            ┌────────┐  │
         │ │有冲突  │            │无冲突  │  │
         │ └───┬────┘            └───┬────┘  │
         │     │                     │       │
         │     ▼                     ▼       │
         │ ┌────────┐            ┌────────┐  │
         │ │CLARIFY │───────────►│ENRICHED│  │
         │ │(请求澄清)│           │ INTENT │  │
         │ └────────┘            └───┬────┘  │
         │                           │       │
         └───────────────────────────┘       │
                                             │
         ┌───────────────────────────────────┘
         │
         ▼
  ┌──────────────┐
  │   DONE       │
  │ (输出结构化意图)│
  └──────────────┘
```

**结构化意图 Schema**：

```yaml
structured_intent:
  version: "2.0"
  intent_id: "uuid"
  
  # 用户原始输入
  raw_input:
    text: "我想让这个游戏更难，像魂系那种慢慢变强的感觉"
    language: "zh"
    timestamp: "2026-04-27T10:00:00Z"
  
  # 核心意图（分类结果）
  primary_goal:
    type: difficulty_adjustment  # 意图类型
    target: game_mechanics        # 目标域
    direction: increase          # 方向（增加/减少/改变）
    magnitude: significant       # 程度（轻微/中等/显著/极端）
  
  # 子目标（分解结果）
  sub_goals:
    - type: increase_enemy_damage
      target_mechanic: "combat.damage_enemy_to_player"
      parameter: "damage_multiplier"
      change: { type: multiply, value: 1.5 }
    
    - type: increase_death_penalty
      target_mechanic: "player.death"
      parameter: "penalty_type"
      change: { type: set, value: "lose_souls" }
    
    - type: adjust_progression_curve
      target_mechanic: "player.leveling"
      parameter: "experience_required"
      change: { type: multiply, value: 1.3 }
  
  # 参考案例（解析结果）
  references:
    - type: game_series
      name: "Dark Souls"
      extracted_features:
        - "gradual_power_progression"
        - "high_death_penalty"
        - "environmental_storytelling"
        - "methodical_combat_pacing"
      confidence: 0.92
  
  # 约束条件
  constraints:
    - type: balance
      expression: "death_penalty < 100% of progress"
      hard: true
    - type: difficulty
      expression: "boss_damage < 3 * player_max_health"
      hard: true
    - type: feel
      expression: "not frustrating"
      hard: false
      weight: 0.8
  
  # 用户偏好（从记忆系统注入）
  preferences:
    difficulty_baseline: "hard"
    preferred_genres: ["souls_like", "action_rpg"]
    disliked_mechanics: ["permadeath", "time_limits"]
  
  # 元数据
  metadata:
    parsing_confidence: 0.89
    ambiguity_flags: []  # 如果有歧义，列出需要澄清的点
    estimated_complexity: medium  # low, medium, high, extreme
```

**关键技术点**：

1. **意图分类器**：使用 fine-tuned 分类器或 few-shot LLM 分类
2. **参考解析器**：将"像魂系"映射到特征向量
```python
class ReferenceResolver:
    """将模糊参考解析为具体特征"""
    
    def resolve(self, reference: str) -> ResolvedReference:
        # 1. 在知识库中查找匹配
        candidates = self.knowledge_base.search(reference, top_k=5)
        
        # 2. 用 LLM 评估匹配度
        best_match = self.llm.rank_matches(reference, candidates)
        
        # 3. 提取特征向量
        features = self.feature_extractor.extract(best_match)
        
        return ResolvedReference(
            name=best_match.name,
            features=features,
            confidence=best_match.score
        )
```

3. **冲突检测器**：
```python
class ConflictDetector:
    """检测意图中的矛盾"""
    
    def detect(self, intent: StructuredIntent) -> List[Conflict]:
        conflicts = []
        
        # 检查约束矛盾
        for c1, c2 in combinations(intent.constraints, 2):
            if self._are_contradictory(c1, c2):
                conflicts.append(Conflict(
                    type="constraint_contradiction",
                    between=[c1, c2],
                    severity="high"
                ))
        
        # 检查偏好矛盾
        if "permadeath" in intent.preferences.disliked_mechanics:
            for subgoal in intent.sub_goals:
                if subgoal.type == "enable_permadeath":
                    conflicts.append(Conflict(
                        type="preference_violation",
                        description="User dislikes permadeath but goal enables it",
                        severity="medium"
                    ))
        
        return conflicts
```

### 4.3 规划层（Planning Layer）

**职责**：将结构化意图和内容图谱转化为可执行的 Patch DAG。

**v2.0 核心创新：MCTS + LLM 价值函数**

```
规划流程
    │
    ▼
┌──────────────────────────────────────────────┐
│  1. 目标分解 (Goal Decomposer)                │
│     将高层意图分解为原子子目标               │
│     输出: 目标树 (Goal Tree)                 │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  2. 操作空间构建 (Operation Space Builder)    │
│     根据子目标检索候选操作                   │
│     输出: 候选操作列表 (Candidate Ops)       │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  3. 计划搜索 (Plan Search - MCTS)             │
│                                              │
│     ┌─────────┐    ┌─────────┐    ┌────────┐ │
│     │ Selection│───►│Expansion│───►│Simulation│ │
│     │ (UCB1)  │    │ (LLM    │    │ (Rollout│ │
│     │         │    │ 生成)   │    │ + 评估) │ │
│     └────┬────┘    └────┬────┘    └───┬────┘ │
│          │              │             │      │
│          └──────────────┴─────────────┘      │
│                         │                    │
│                         ▼                    │
│                    ┌─────────┐               │
│                    │Backprop │               │
│                    │(更新值) │               │
│                    └────┬────┘               │
│                         │                    │
│                         └────────────────────┘
│                         │
│                         ▼
│              迭代 N 次后选择最优路径
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  4. 计划验证 (Plan Validator)                 │
│     • 静态检查: 依赖满足、资源足够             │
│     • 模拟执行: 预测输出（轻量级）             │
│     • 冲突检测: 操作之间的一致性               │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────┐
│  5. 计划优化 (Plan Optimizer)                 │
│     • 成本最小化                             │
│     • 并行化识别                             │
│     • 回滚策略生成                           │
└──────────────────────┬───────────────────────┘
                       │
                       ▼
              Patch DAG (改造计划)
```

**MCTS + LLM 详细设计**：

```python
@dataclass
class PlanNode:
    """MCTS 树节点"""
    state: ContentGraph  # 当前内容状态（应用了部分 Patch 后的 CDL）
    parent: Optional['PlanNode'] = None
    children: List['PlanNode'] = field(default_factory=list)
    
    # MCTS 统计
    visits: int = 0
    value: float = 0.0  # 累计价值
    
    # 操作信息
    operation: Optional[AtomicOperation] = None  # 导致这个状态的操作
    patch: Optional[CDLPatch] = None

class MCTSPlanner:
    """蒙特卡洛树搜索 + LLM 价值函数的规划器"""
    
    def __init__(
        self,
        llm_value_fn: LLMValueFunction,
        operation_library: OperationLibrary,
        rollout_depth: int = 5,
        num_simulations: int = 50,
    ):
        self.llm_value = llm_value_fn
        self.op_lib = operation_library
        self.rollout_depth = rollout_depth
        self.num_simulations = num_simulations
    
    def plan(
        self,
        intent: StructuredIntent,
        initial_graph: ContentGraph,
    ) -> TransformationPlan:
        """生成改造计划"""
        root = PlanNode(state=initial_graph)
        
        for _ in range(self.num_simulations):
            # 1. Selection: 选择最有潜力的节点
            node = self._select(root)
            
            # 2. Expansion: 扩展新节点
            if not self._is_terminal(node):
                node = self._expand(node, intent)
            
            # 3. Simulation: 模拟执行到终止状态
            value = self._simulate(node, intent)
            
            # 4. Backpropagation: 更新路径上的值
            self._backpropagate(node, value)
        
        # 选择最优路径
        best_path = self._get_best_path(root)
        return self._path_to_plan(best_path)
    
    def _select(self, node: PlanNode) -> PlanNode:
        """UCB1 选择"""
        while node.children and not self._is_terminal(node):
            node = max(
                node.children,
                key=lambda c: self._ucb1(c, node.visits)
            )
        return node
    
    def _ucb1(self, node: PlanNode, parent_visits: int) -> float:
        """UCB1 公式"""
        if node.visits == 0:
            return float('inf')
        exploitation = node.value / node.visits
        exploration = math.sqrt(2 * math.log(parent_visits) / node.visits)
        return exploitation + exploration
    
    def _expand(self, node: PlanNode, intent: StructuredIntent) -> PlanNode:
        """扩展：用 LLM 生成候选操作"""
        # 获取当前状态的上下文（用于 LLM）
        context = self._get_state_context(node.state, intent)
        
        # 用 LLM 生成候选操作
        candidates = self.llm_value.generate_candidates(context, top_k=5)
        
        # 验证候选操作的可行性
        valid_candidates = [
            c for c in candidates
            if self._check_preconditions(c, node.state)
        ]
        
        # 为每个候选创建子节点
        for candidate in valid_candidates:
            new_state = self._apply_patch(node.state, candidate.patch)
            child = PlanNode(
                state=new_state,
                parent=node,
                operation=candidate.operation,
                patch=candidate.patch,
            )
            node.children.append(child)
        
        # 返回第一个子节点进行模拟
        return node.children[0] if node.children else node
    
    def _simulate(self, node: PlanNode, intent: StructuredIntent) -> float:
        """模拟：从当前状态随机执行到终止"""
        state = node.state
        depth = 0
        
        while depth < self.rollout_depth and not self._is_goal(state, intent):
            # 随机选择操作（或基于启发式）
            op = self._random_operation(state, intent)
            if op is None:
                break
            state = self._apply_patch(state, op.patch)
            depth += 1
        
        # 用 LLM 评估最终状态的价值
        return self.llm_value.evaluate(state, intent)
    
    def _backpropagate(self, node: PlanNode, value: float) -> None:
        """反向传播价值"""
        while node:
            node.visits += 1
            node.value += value
            node = node.parent
```

**LLM 价值函数**：

```python
class LLMValueFunction:
    """用 LLM 评估状态和生成候选操作"""
    
    def __init__(self, llm_provider: LLMProvider):
        self.llm = llm_provider
    
    def generate_candidates(
        self,
        context: PlanningContext,
        top_k: int = 5,
    ) -> List[CandidateOperation]:
        """生成候选操作"""
        prompt = f"""
Given the current content state and user intent, suggest the next atomic operations to apply.

Current State Summary:
{context.state_summary}

User Intent:
{context.intent_text}

Progress So Far:
{context.applied_operations}

Available Operation Types:
{context.available_ops}

Suggest up to {top_k} candidate operations. Each should include:
- operation_type: string
- target: which node/asset to modify
- parameters: specific values
- expected_effect: what will change
- estimated_cost: time/compute cost

Format as JSON array.
"""
        response = self.llm.generate(prompt, temperature=0.7)
        return self._parse_candidates(response)
    
    def evaluate(self, state: ContentGraph, intent: StructuredIntent) -> float:
        """评估状态价值（0-1）"""
        prompt = f"""
Evaluate how well the current content state satisfies the user intent.

Intent: {intent.raw_input.text}
Sub-goals: {[g.type for g in intent.sub_goals]}

Current State:
{state.summary()}

Rate from 0.0 to 1.0 based on:
- Intent alignment (50%)
- Content consistency (30%)
- Quality preservation (20%)

Output only a float number.
"""
        response = self.llm.generate(prompt, temperature=0.0)
        return float(response.strip())
```

**计划验证器**：

```python
class PlanValidator:
    """验证改造计划的可行性"""
    
    def validate(self, plan: TransformationPlan, graph: ContentGraph) -> ValidationResult:
        issues = []
        
        # 1. 依赖检查
        issues.extend(self._check_dependencies(plan))
        
        # 2. 资源检查
        issues.extend(self._check_resources(plan, graph))
        
        # 3. 一致性检查
        issues.extend(self._check_consistency(plan, graph))
        
        # 4. 冲突检测
        issues.extend(self._check_conflicts(plan))
        
        # 5. 模拟执行（轻量级）
        sim_result = self._simulate_execution(plan, graph)
        if sim_result.has_errors:
            issues.extend(sim_result.errors)
        
        return ValidationResult(
            valid=len([i for i in issues if i.severity == "error"]) == 0,
            issues=issues,
            estimated_cost=self._estimate_cost(plan),
        )
    
    def _check_conflicts(self, plan: TransformationPlan) -> List[Issue]:
        """检测操作之间的冲突"""
        issues = []
        
        # 检查是否有两个操作修改同一节点/属性
        modifications = defaultdict(list)
        for op in plan.operations:
            if op.type in ["modify_node", "modify_asset"]:
                key = (op.node_id or op.asset_id, str(op.property_changes.keys()))
                modifications[key].append(op)
        
        for key, ops in modifications.items():
            if len(ops) > 1:
                issues.append(Issue(
                    severity="warning",
                    type="conflict",
                    message=f"Multiple operations modify {key}: {[o.id for o in ops]}",
                ))
        
        return issues
```

### 4.4 执行层（Execution Layer）

**职责**：安全、高效地执行 Patch DAG。

**状态机（细化版）**：

```
                              ┌─────────┐
                              │ PENDING │
                              │ (等待调度)│
                              └────┬────┘
                                   │ 调度器分配 Worker
                                   ▼
                              ┌─────────┐
         ┌───────────────────│QUEUED   │
         │                   │ (队列中) │
         │                   └────┬────┘
         │                        │ Worker 开始执行
         │                        ▼
         │                   ┌─────────┐
         │                   │RUNNING  │
         │                   │ (执行中) │
         │                   └────┬────┘
         │                        │
    ┌────┼────┬────────┬─────────┼─────────┬────────┐
    │    │    │        │         │         │        │
    ▼    ▼    ▼        ▼         ▼         ▼        ▼
┌──────┐┌──────┐┌────────┐┌────────┐┌────────┐┌────────┐
│SUCCESS││FAILED││TIMEOUT ││CANCELLED││RETRYING││PAUSED  │
│(成功) ││(失败) ││(超时)  ││(取消)  ││(重试中)││(暂停)  │
└──┬───┘└──┬───┘└────┬───┘└────┬───┘└────┬───┘└────┬───┘
   │       │         │         │         │         │
   │       ▼         │         │         │         │
   │   ┌────────┐    │         │         │         │
   │   │RECOVER │◄───┘         │         │         │
   │   │(恢复)  │              │         │         │
   │   └───┬────┘              │         │         │
   │       │                   │         │         │
   │       ▼                   │         │         │
   │   ┌────────┐              │         │         │
   │   │ROLLBACK│              │         │         │
   │   │(回滚)  │              │         │         │
   │   └───┬────┘              │         │         │
   │       │                   │         │         │
   │       ▼                   │         │         │
   │   ┌────────┐              │         │         │
   └──►│COMPLETED│◄────────────┘◄────────┘◄────────┘
       │(完成)  │
       └────────┘
```

**执行引擎详细设计**：

```python
class ExecutionEngine:
    """改造计划执行引擎"""
    
    def __init__(
        self,
        sandbox_factory: SandboxFactory,
        tool_registry: ToolRegistry,
        event_bus: EventBus,
    ):
        self.sandbox_factory = sandbox_factory
        self.tools = tool_registry
        self.events = event_bus
    
    async def execute(
        self,
        plan: TransformationPlan,
        context: ExecutionContext,
    ) -> ExecutionResult:
        """执行改造计划"""
        # 1. 创建沙箱
        sandbox = await self.sandbox_factory.create(
            content_path=context.content_path,
            resources=context.resource_limits,
        )
        
        try:
            # 2. 拓扑排序，确定执行顺序
            execution_order = self._topological_sort(plan.operations)
            
            # 3. 识别可并行执行的操作
            parallel_groups = self._identify_parallel_groups(execution_order)
            
            # 4. 按组执行
            results = []
            for group in parallel_groups:
                group_results = await self._execute_group(group, sandbox, context)
                results.extend(group_results)
                
                # 检查是否有失败
                failures = [r for r in group_results if r.status == "failed"]
                if failures:
                    # 尝试恢复
                    recovered = await self._attempt_recovery(failures, sandbox, context)
                    if not recovered:
                        await self._rollback(results, sandbox)
                        return ExecutionResult(
                            status="failed",
                            completed_operations=results,
                            error=failures[0].error,
                        )
            
            # 5. 收集产物
            artifacts = await self._collect_artifacts(sandbox)
            
            return ExecutionResult(
                status="success",
                completed_operations=results,
                artifacts=artifacts,
            )
            
        finally:
            await sandbox.destroy()
    
    async def _execute_group(
        self,
        group: List[Operation],
        sandbox: Sandbox,
        context: ExecutionContext,
    ) -> List[OperationResult]:
        """并行执行一组操作"""
        tasks = [
            self._execute_single(op, sandbox, context)
            for op in group
        ]
        return await asyncio.gather(*tasks)
    
    async def _execute_single(
        self,
        operation: Operation,
        sandbox: Sandbox,
        context: ExecutionContext,
    ) -> OperationResult:
        """执行单个操作"""
        start_time = time.monotonic()
        
        try:
            # 获取工具
            tool = self.tools.get(operation.tool_name)
            
            # 在沙箱中执行
            result = await sandbox.run(
                tool,
                args=operation.parameters,
                timeout=operation.timeout or 300,
            )
            
            duration = time.monotonic() - start_time
            
            return OperationResult(
                operation_id=operation.id,
                status="success",
                output=result.output,
                duration=duration,
            )
            
        except TimeoutError:
            return OperationResult(
                operation_id=operation.id,
                status="timeout",
                error="Operation exceeded time limit",
                duration=operation.timeout or 300,
            )
        except Exception as e:
            return OperationResult(
                operation_id=operation.id,
                status="failed",
                error=str(e),
                duration=time.monotonic() - start_time,
            )
```

**沙箱设计（gVisor）**：

```python
class GVisorSandbox:
    """基于 gVisor 的安全沙箱"""
    
    def __init__(
        self,
        image: str,
        cpu_limit: float = 1.0,
        memory_limit: str = "2g",
        disk_limit: str = "10g",
        network: bool = False,
    ):
        self.image = image
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.disk_limit = disk_limit
        self.network = network
    
    async def create(self) -> SandboxInstance:
        """创建沙箱实例"""
        cmd = [
            "runsc",  # gVisor 运行时
            "run",
            "--rootless",
            f"--cpu={self.cpu_limit}",
            f"--memory={self.memory_limit}",
            f"--disk={self.disk_limit}",
            "--network=none" if not self.network else "--network=host",
            "--overlay",  # 使用 overlayfs，保护原始文件
            "sandbox-id",
        ]
        
        self.process = await asyncio.create_subprocess_exec(*cmd)
        return SandboxInstance(self.process)
    
    async def run(
        self,
        tool: Tool,
        args: Dict[str, Any],
        timeout: int = 300,
    ) -> ToolResult:
        """在沙箱中运行工具"""
        # 将工具调用序列化为沙箱内的命令
        cmd = tool.to_command(args)
        
        try:
            proc = await asyncio.wait_for(
                self._exec_in_sandbox(cmd),
                timeout=timeout,
            )
            return ToolResult(
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except asyncio.TimeoutError:
            await self._kill_process(proc)
            raise TimeoutError(f"Tool execution exceeded {timeout}s")
    
    async def destroy(self):
        """销毁沙箱"""
        if self.process:
            self.process.terminate()
            await self.process.wait()
```

### 4.5 评估层（Evaluation Layer）

**职责**：多维度评估改造质量。

**评估管道**：

```
改造产物 + 原始意图
    │
    ├──→ [完整性检查] ──→ 文件齐全？引用正确？
    │       │
    │       └──→ 完整性评分 (0-100)
    │
    ├──→ [一致性检查] ──→ 规则冲突？数值溢出？循环依赖？
    │       │
    │       ├──→ AST 静态分析
    │       ├──→ 配置 Schema 验证
    │       └──→ 一致性评分 (0-100)
    │
    ├──→ [意图对齐度] ──→ 结果符合用户描述？
    │       │
    │       ├──→ LLM 评估 ("这个改造是否让游戏更难？")
    │       ├──→ 规则匹配 (检查具体参数是否达到目标)
    │       └──→ 对齐度评分 (0-100)
    │
    ├──→ [可运行性检查] ──→ 能启动？能运行？
    │       │
    │       ├──→ 沙箱内启动测试
    │       ├──→ 关键路径测试 (如"完成第一关")
    │       └──→ 可运行性评分 (0-100)
    │
    ├──→ [安全性检查] ──→ 恶意代码？版权侵权？
    │       │
    │       ├──→ 病毒扫描
    │       ├──→ 版权指纹匹配
    │       └──→ 安全评分 (0-100, 必须=100)
    │
    └──→ [性能检查] ──→ 加载时间？帧率？内存？
            │
            └──→ 性能评分 (0-100)

                  │
                  ▼
        ┌─────────────────┐
        │  综合评分计算    │
        │                 │
        │  weighted_sum(  │
        │    完整性 * 0.15│
        │    一致性 * 0.20│
        │    对齐度 * 0.30│
        │    可运行 * 0.25│
        │    性能   * 0.10│
        │  )              │
        └────────┬────────┘
                 │
        ┌────────┴────────┐
        │                 │
        ▼                 ▼
   ┌─────────┐      ┌─────────┐
   │ ≥ 阈值  │      │ < 阈值  │
   │ (通过)  │      │ (失败)  │
   └────┬────┘      └────┬────┘
        │                │
        ▼                ▼
   [发布产物]      [触发回滚]
                   [生成失败报告]
                   [通知用户]
```

---

## 5. 记忆系统（Memory System）

**架构**：

```
记忆系统
    │
    ├──→ 用户偏好存储 (User Preference Store)
    │       │
    │       ├──→ 显式偏好 (Explicit)
    │       │       • 评分历史
    │       │       • 标签选择
    │       │       • 设置配置
    │       │
    │       └──→ 隐式偏好 (Implicit)
    │               • 行为模式 (点击、停留、跳过)
    │               • 时间模式 (何时使用、使用频率)
    │               • 设备模式 (PC vs Mobile)
    │
    ├──→ 内容知识图谱 (Content Knowledge Graph)
    │       │
    │       ├──→ 游戏本体 (Game Ontology)
    │       │       • 机制类型、关系、属性
    │       │       • 流派特征向量
    │       │
    │       ├──→ 模板库 (Template Library)
    │       │       • 成功的改造模式
    │       │       • 版本化、可分叉
    │       │
    │       └──→ 社区知识 (Community Knowledge)
    │               • 热门 Mod 特征
    │               • 创作者风格
    │
    ├──→ 执行历史 (Execution History)
    │       • 成功/失败记录
    │       • 耗时、成本
    │       • 反馈评分
    │
    └──→ 语义索引 (Semantic Index)
            • 向量数据库 (pgvector)
            • 支持相似性搜索
            • 支持 RAG 检索
```

**更新机制**：

```python
class MemoryUpdater:
    """记忆更新器"""
    
    def update_from_feedback(
        self,
        user_id: str,
        project_id: str,
        feedback: UserFeedback,
    ) -> None:
        """从用户反馈更新记忆"""
        
        # 1. 更新显式偏好
        if feedback.rating:
            self._update_preference_vector(user_id, project_id, feedback.rating)
        
        # 2. 更新隐式偏好
        if feedback.behavior:
            self._update_behavior_pattern(user_id, feedback.behavior)
        
        # 3. 提取成功的改造模式（如果评分高）
        if feedback.rating and feedback.rating >= 4:
            self._extract_template(project_id)
        
        # 4. 记录失败原因（如果评分低）
        if feedback.rating and feedback.rating <= 2:
            self._record_failure_pattern(project_id, feedback.comment)
    
    def _update_preference_vector(
        self,
        user_id: str,
        project_id: str,
        rating: float,
    ) -> None:
        """更新用户偏好向量"""
        # 获取项目特征
        project_features = self._get_project_features(project_id)
        
        # 获取当前偏好向量
        current_pref = self._get_preference_vector(user_id)
        
        # 基于评分更新（类似梯度下降）
        # 正评分：向项目特征方向移动
        # 负评分：远离项目特征方向
        learning_rate = 0.1 * (rating - 3) / 2  # 3 分不更新，5 分正向，1 分负向
        
        new_pref = current_pref + learning_rate * (project_features - current_pref)
        
        self._save_preference_vector(user_id, new_pref)
```

---

## 6. 事件总线与消息协议

**事件 Schema（Protobuf）**：

```protobuf
// events.proto
syntax = "proto3";
package udify.events;

message Event {
  string event_id = 1;
  string event_type = 2;
  string timestamp = 3;  // ISO 8601
  string source = 4;     // 产生事件的组件
  map<string, string> metadata = 5;
  oneof payload {
    ContentParsedEvent content_parsed = 10;
    IntentRecognizedEvent intent_recognized = 11;
    PlanGeneratedEvent plan_generated = 12;
    StepCompletedEvent step_completed = 13;
    QualityEvaluatedEvent quality_evaluated = 14;
    UserFeedbackEvent user_feedback = 15;
  }
}

message ContentParsedEvent {
  string content_id = 1;
  string media_type = 2;
  int32 node_count = 3;
  int32 edge_count = 4;
  int32 asset_count = 5;
  float confidence = 6;
}

message IntentRecognizedEvent {
  string intent_id = 1;
  string user_id = 2;
  string primary_goal_type = 3;
  repeated string sub_goal_types = 4;
  float confidence = 5;
  repeated string ambiguity_flags = 6;
}

message PlanGeneratedEvent {
  string plan_id = 1;
  string intent_id = 2;
  int32 step_count = 4;
  float estimated_cost = 5;
  float estimated_duration = 6;
  float predicted_quality = 7;
}

message StepCompletedEvent {
  string execution_id = 1;
  string step_id = 2;
  string status = 3;  // success, failed, timeout, skipped
  int32 duration_ms = 4;
  string error_message = 5;
}

message QualityEvaluatedEvent {
  string project_id = 1;
  float overall_score = 2;
  bool passed = 3;
  map<string, float> dimension_scores = 4;
  repeated string issues = 5;
}

message UserFeedbackEvent {
  string user_id = 1;
  string project_id = 2;
  int32 rating = 3;  // 1-5
  string comment = 4;
  repeated string behavior_signals = 5;
}
```

**事件流拓扑**：

```
[感知层] ──ContentParsed──→ [事件总线]
    │                           │
    │                           ├──→ [认知层] ──IntentRecognized──→ [事件总线]
    │                           │                                     │
    │                           │                                     ├──→ [规划层]
    │                           │                                     │
    │                           │                                     └──→ [记忆系统]
    │                           │
    │                           ├──→ [评估层] ──QualityEvaluated──→ [事件总线]
    │                           │                                     │
    │                           │                                     ├──→ [Udiface]
    │                           │                                     │
    │                           │                                     └──→ [记忆系统]
    │                           │
    │                           └──→ [审计日志] ──→ [长期存储]
    │
    └──→ [错误处理] ──ErrorEvent──→ [告警系统]
```

---

## 7. 工具层（Tool Layer - MCP Protocol）

**MCP (Model Context Protocol) 集成**：

Udify 的所有工具都遵循 MCP 标准，这意味着：
1. 任何 MCP 兼容的工具都可以被 Udify 调用
2. Udify 的工具也可以被其他 MCP 客户端使用
3. 工具发现是自动化的（通过 MCP 的 capability 声明）

**MCP Tool Schema 示例**：

```json
{
  "name": "unity_modify_script",
  "description": "Modify a C# script in a Unity game using AST-based patching",
  "inputSchema": {
    "type": "object",
    "properties": {
      "target_file": {
        "type": "string",
        "description": "Path to the C# script file"
      },
      "modifications": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "type": {
              "type": "string",
              "enum": ["replace_method", "add_field", "modify_property"]
            },
            "target": {
              "type": "string",
              "description": "AST path to the target node"
            },
            "new_value": {
              "type": "string",
              "description": "New code to insert"
            }
          },
          "required": ["type", "target", "new_value"]
        }
      }
    },
    "required": ["target_file", "modifications"]
  }
}
```

**工具注册表**：

```python
class ToolRegistry:
    """工具注册表，基于 MCP"""
    
    def __init__(self):
        self._tools: Dict[str, MCPTool] = {}
        self._capabilities: Dict[str, ToolCapability] = {}
    
    def register(self, tool: MCPTool) -> None:
        """注册工具"""
        self._tools[tool.name] = tool
        self._capabilities[tool.name] = tool.capability
    
    def discover(self, requirement: ToolRequirement) -> List[MCPTool]:
        """根据需求发现合适的工具"""
        candidates = []
        for tool in self._tools.values():
            if self._matches(tool, requirement):
                candidates.append(tool)
        
        # 按匹配度排序
        candidates.sort(key=lambda t: self._score(t, requirement), reverse=True)
        return candidates
    
    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        sandbox: Sandbox,
    ) -> ToolResult:
        """执行工具"""
        tool = self._tools.get(tool_name)
        if not tool:
            raise ToolNotFoundError(tool_name)
        
        # 验证参数
        tool.validate_arguments(arguments)
        
        # 在沙箱中执行
        return await tool.execute(arguments, sandbox)
```

---

## 8. Udiface 平台架构

### 8.1 前端架构（细化）

```
Next.js 15 (App Router)
├── app/
│   ├── layout.tsx              # 根布局 (Providers, Auth)
│   ├── page.tsx                # 营销首页
│   │
│   ├── (auth)/                 # 认证路由组
│   │   ├── login/
│   │   └── register/
│   │
│   ├── (platform)/             # 平台路由组 (需要登录)
│   │   ├── explore/
│   │   │   └── page.tsx        # 发现页 (瀑布流)
│   │   ├── project/
│   │   │   └── [id]/
│   │   │       ├── page.tsx    # 项目详情
│   │   │       └── play/       # 在线运行
│   │   ├── studio/
│   │   │   └── page.tsx        # 创作工作室
│   │   │       └── components/
│   │   │           ├── IntentInput.tsx      # 意图输入
│   │   │           ├── PlanVisualizer.tsx   # 计划可视化 (ReactFlow)
│   │   │           ├── ProgressMonitor.tsx  # 进度监控
│   │   │           └── ResultPreview.tsx    # 结果预览
│   │   ├── profile/
│   │   │   └── [username]/
│   │   └── settings/
│   │
│   └── api/                    # API 路由 (BFF 模式)
│       └── trpc/               # tRPC 路由
│
├── components/
│   ├── ui/                     # shadcn/ui 组件
│   ├── graph/                  # ReactFlow 图组件
│   ├── media/                  # 媒介预览组件
│   └── layout/                 # 布局组件
│
├── hooks/
│   ├── useProject.ts
│   ├── usePlanExecution.ts     # 计划执行状态管理
│   └── useMemory.ts            # 用户偏好查询
│
├── lib/
│   ├── api.ts                  # tRPC 客户端
│   ├── auth.ts
│   └── utils.ts
│
└── types/
    ├── cdl.ts                  # CDL TypeScript 类型
    └── plan.ts                 # 计划类型
```

### 8.2 ReactFlow 集成（计划可视化）

```tsx
// PlanVisualizer.tsx
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  Node,
  Edge,
} from 'reactflow';
import 'reactflow/dist/style.css';

interface PlanVisualizerProps {
  plan: TransformationPlan;
  executionState?: ExecutionState;
}

const PlanVisualizer: React.FC<PlanVisualizerProps> = ({
  plan,
  executionState,
}) => {
  // 将 Patch DAG 转换为 ReactFlow 的 nodes/edges
  const nodes: Node[] = plan.operations.map((op, index) => ({
    id: op.id,
    type: 'operationNode',
    position: { x: index * 250, y: op.depth * 150 },
    data: {
      operation: op,
      status: executionState?.getStatus(op.id) || 'pending',
      progress: executionState?.getProgress(op.id) || 0,
    },
  }));

  const edges: Edge[] = plan.dependencies.map((dep) => ({
    id: `${dep.from}-${dep.to}`,
    source: dep.from,
    target: dep.to,
    type: 'smoothstep',
    animated: executionState?.isExecuting(dep.from) || false,
  }));

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={{ operationNode: OperationNode }}
      fitView
    >
      <Background />
      <Controls />
      <MiniMap />
    </ReactFlow>
  );
};

// 自定义节点组件
const OperationNode: React.FC<NodeProps> = ({ data }) => {
  const { operation, status, progress } = data;
  
  const statusColors = {
    pending: 'gray',
    running: 'blue',
    success: 'green',
    failed: 'red',
    retrying: 'yellow',
  };

  return (
    <div className={`operation-node status-${status}`}>
      <div className="node-header">
        <span className="node-type">{operation.type}</span>
        <span className={`node-status ${statusColors[status]}`}>
          {status}
        </span>
      </div>
      <div className="node-body">
        <p>{operation.description}</p>
        {status === 'running' && (
          <progress value={progress} max={100} />
        )}
      </div>
    </div>
  );
};
```

---

## 9. 安全架构

### 9.1 多层安全模型

```
用户输入
    │
    ▼
┌─────────────────┐  Layer 1: 输入验证
│ 输入校验        │  • Schema 验证
│ (JSON Schema)   │  • 长度限制
│                 │  • 字符过滤
└────────┬────────┘
         │
         ▼
┌─────────────────┐  Layer 2: 内容安全
│ 病毒扫描        │  • ClamAV
│ (ClamAV)        │  • YARA 规则
│                 │  • 启发式检测
└────────┬────────┘
         │
         ▼
┌─────────────────┐  Layer 3: 版权检测
│ 版权指纹        │  • 感知哈希 (pHash)
│ (Fingerprint)   │  • 音频指纹 (AcoustID)
│                 │  • 文本指纹 (SimHash)
└────────┬────────┘
         │
         ▼
┌─────────────────┐  Layer 4: 恶意内容
│ AI 分类器       │  • 毒性检测
│ (Safety Classifier)│ • 仇恨言论
│                 │  • 非法内容
└────────┬────────┘
         │
         ▼
┌─────────────────┐  Layer 5: 沙箱隔离
│ gVisor 沙箱     │  • 系统调用过滤
│                 │  • 资源限制
│                 │  • 网络隔离
└────────┬────────┘
         │
         ▼
┌─────────────────┐  Layer 6: 输出扫描
│ 输出审查        │  • 产物完整性检查
│ (Output Scan)   │  • 无 unexpectedly 大文件
│                 │  • 无 unexpectedly 网络请求
└─────────────────┘
```

### 9.2 隐私架构

```
用户数据
    │
    ├──→ 个人身份信息 (PII)
    │       ├──→ 加密存储 (AES-256-GCM)
    │       ├──→ 访问控制 (RBAC)
    │       └──→ 自动过期 (TTL)
    │
    ├──→ 偏好数据
    │       ├──→ 联邦学习 (差分隐私)
    │       ├──→ 本地处理优先
    │       └──→ 可删除 (GDPR Right to Erasure)
    │
    └──→ 行为数据
            ├──→ 匿名化 (k-anonymity)
            ├──→ 聚合统计
            └──→ 不出境 (数据本地化)
```

---

## 10. 部署与运维架构

### 10.1 开发环境

```yaml
# docker-compose.dev.yml
version: '3.8'

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile.dev
    volumes:
      - .:/app
      - /app/.venv
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/udify
      - REDIS_URL=redis://redis:6379
      - NEO4J_URL=bolt://neo4j:7687
      - LLM_PROVIDER=local
    depends_on:
      - db
      - redis
      - neo4j
      - minio

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    volumes:
      - .:/app
      - /app/.venv
      - /var/run/docker.sock:/var/run/docker.sock  # 用于创建沙箱
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/udify
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis

  db:
    image: postgres:16
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: udify
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  neo4j:
    image: neo4j:5-community
    environment:
      NEO4J_AUTH: neo4j/password
      NEO4J_PLUGINS: '["apoc", "gds"]'  # APOC + Graph Data Science
    volumes:
      - neo4j_data:/data
    ports:
      - "7474:7474"
      - "7687:7687"

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    environment:
      MINIO_ROOT_USER: minio
      MINIO_ROOT_PASSWORD: minio123
    volumes:
      - minio_data:/data
    ports:
      - "9000:9000"
      - "9001:9001"

  prefect:
    image: prefecthq/prefect:2-latest
    command: prefect server start
    ports:
      - "4200:4200"

volumes:
  postgres_data:
  neo4j_data:
  minio_data:
```

### 10.2 生产环境（K8s）

```yaml
# k8s/udify-core.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: udify-api
spec:
  replicas: 3
  selector:
    matchLabels:
      app: udify-api
  template:
    metadata:
      labels:
        app: udify-api
    spec:
      containers:
        - name: api
          image: udify/api:latest
          ports:
            - containerPort: 8000
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: udify-secrets
                  key: database-url
            - name: NEO4J_URL
              valueFrom:
                secretKeyRef:
                  name: udify-secrets
                  key: neo4j-url
          resources:
            requests:
              memory: "512Mi"
              cpu: "500m"
            limits:
              memory: "2Gi"
              cpu: "2000m"
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /ready
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: udify-worker
spec:
  replicas: 5
  selector:
    matchLabels:
      app: udify-worker
  template:
    metadata:
      labels:
        app: udify-worker
    spec:
      containers:
        - name: worker
          image: udify/worker:latest
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: udify-secrets
                  key: database-url
          resources:
            requests:
              memory: "1Gi"
              cpu: "1000m"
            limits:
              memory: "4Gi"
              cpu: "4000m"
      # gVisor 运行时用于沙箱
      runtimeClassName: gvisor
```

---

## 11. 架构决策记录（ADR）v2

### ADR-005: 使用 Diff/Patch 作为核心输出格式

**状态**: 已接受

**背景**: 改造计划的输出格式选择。候选：完整文件重写、AST Patch、文本 Diff。

**决策**: 使用 CDL Patch 格式（基于 JSON Patch 扩展）。

**理由**:
- 节省 LLM token（只生成变化部分）
- 精确（避免误改无关内容）
- 可验证（可以独立检查每个 patch 操作）
- 可回滚（每个 patch 有对应的 reverse patch）
- 版本控制友好（类似 Git diff）

**权衡**:
- 需要维护 patch 的兼容性（如果原始内容更新，patch 可能失效）
- 复杂变换可能需要大量 patch 操作

### ADR-006: 使用 MCTS + LLM 作为规划算法

**状态**: 已接受

**背景**: 规划器算法选择。候选：纯 LLM 生成、规则引擎、搜索算法、强化学习。

**决策**: 使用蒙特卡洛树搜索（MCTS），LLM 作为价值函数和策略网络。

**理由**:
- 搜索算法保证覆盖（不会遗漏可行的操作序列）
- LLM 提供高质量的启发（避免盲目搜索）
- 可解释（搜索树可以可视化）
- 可增量优化（更多数据 → 更好的 LLM 价值估计）

**权衡**:
- 计算成本高于纯 LLM 生成（需要多次模拟）
- 延迟较高（不适合实时场景）

### ADR-007: 使用 MCP (Model Context Protocol) 作为工具接口标准

**状态**: 已接受

**背景**: 工具调用接口选择。候选：自定义 JSON-RPC、OpenAPI、gRPC、MCP。

**决策**: 使用 Anthropic 的 MCP 标准。

**理由**:
- 开放标准，生态兼容
- 自动化的 capability 发现和 schema 验证
- 与 LangChain 集成良好
- 支持工具调用的人类可读描述

**权衡**:
- 较新的标准，可能有不稳定性
- 需要为每个工具编写 MCP manifest

### ADR-008: 使用 Neo4j 作为内容图谱存储

**状态**: 已接受

**背景**: 图存储选择。候选：PostgreSQL JSONB、Neo4j、Amazon Neptune、Dgraph。

**决策**: 使用 Neo4j Community Edition。

**理由**:
- 原生图数据库，Cypher 查询语言强大
- APOC 和 GDS 插件提供丰富的图算法
- 与 Python 生态集成好 (neo4j-python-driver)
- 自托管成本低（Community 版免费）

**权衡**:
- 学习曲线（Cypher 查询语言）
- 社区版无集群支持（Phase 3 后可能需要 Enterprise 或迁移）

### ADR-009: 使用 Prefect 作为工作流引擎

**状态**: 已接受

**背景**: DAG 执行引擎选择。候选：Celery、Airflow、Prefect、Dagster。

**决策**: 使用 Prefect 2.x。

**理由**:
- 原生支持现代 Python（async、type hints）
- 内置 DAG 可视化（与 ReactFlow 配合）
- 数据血缘追踪
- 版本化工作流

**权衡**:
- 较新的项目，社区不如 Airflow 大
- 某些高级功能需要 Cloud 版

### ADR-010: 使用 gVisor 作为沙箱运行时

**状态**: 已接受

**背景**: 沙箱技术选择。候选：Docker（默认）、Kata Containers、gVisor、Firecracker。

**决策**: 使用 gVisor。

**理由**:
- 用户态内核，系统调用过滤
- 防止容器逃逸（比 Docker 更安全）
- 启动速度快于 Kata/Firecracker（无需启动完整 VM）
- 与 Kubernetes 集成（runtimeClassName: gvisor）

**权衡**:
- 性能开销（用户态内核有 ~20% 性能损失）
- 某些系统调用可能不完全兼容

---

## 12. 风险矩阵与技术债务

### 12.1 技术风险矩阵

| 风险 | 可能性 | 影响 | 风险等级 | 缓解策略 | 负责人 |
|------|--------|------|---------|---------|--------|
| LLM 幻觉导致错误改造 | 高 | 高 | 🔴 极高 | 多层验证 + 人在环 | 架构组 |
| Patch 兼容性问题（原始内容更新后 patch 失效） | 中 | 高 | 🟠 高 | Patch 版本锚定 + 自动重试 | 核心引擎组 |
| MCTS 搜索空间爆炸 | 中 | 中 | 🟡 中 | 搜索深度限制 + LLM 剪枝 | 算法组 |
| Neo4j 性能瓶颈（大规模图） | 中 | 中 | 🟡 中 | 图分片 + 查询优化 | 基础设施组 |
| gVisor 系统调用不兼容 | 低 | 中 | 🟢 低 | 兼容性测试 + 回退到 Docker | 安全组 |
| MCP 标准变更 | 中 | 低 | 🟢 低 | 抽象层封装 | 工具组 |
| 引擎格式更新导致解析器失效 | 高 | 低 | 🟡 中 | 插件化 + 社区驱动更新 | 感知组 |

### 12.2 技术债务登记

| ID | 描述 | 引入原因 | 影响 | 偿还计划 |
|----|------|---------|------|---------|
| TD-001 | 感知层使用硬编码引擎特征 | MVP 快速验证 | 新引擎支持慢 | Phase 2 引入机器学习分类器 |
| TD-002 | 规划器无持久化搜索状态 | 复杂度控制 | 长任务中断后需重来 | Phase 2 引入检查点机制 |
| TD-003 | 评估层依赖启发式规则 | LLM 评估成本高 | 误报/漏报 | Phase 2 引入训练好的评估模型 |
| TD-004 | 单节点 Neo4j | 成本限制 | 无法水平扩展 | Phase 3 迁移到 Neo4j Enterprise 或 Amazon Neptune |
| TD-005 | 无分布式执行 | 复杂度控制 | 大规模改造慢 | Phase 3 引入 Kubernetes Jobs |

---

> **"架构是活的文档。这份评审不是终点，而是持续演化的起点。每次技术决策都应该被记录、被质疑、被验证。"**
>
> —— Udify 架构评审原则
