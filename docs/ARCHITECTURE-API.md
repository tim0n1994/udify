# Udify API 架构设计

> **版本**: v1.0 | **日期**: 2026-04-27
>
> **范围**: REST API 设计、GraphQL、WebSocket 实时 API、版本控制、认证、OpenAPI 规范

---

## 目录

1. [API 架构总览](#1-api-架构总览)
2. [REST API 设计](#2-rest-api-设计)
3. [GraphQL API](#3-graphql-api)
4. [WebSocket 实时 API](#4-websocket-实时-api)
5. [API 版本控制策略](#5-api-版本控制策略)
6. [认证与授权](#6-认证与授权)
7. [OpenAPI 规范](#7-openapi-规范)
8. [API 网关设计](#8-api-网关设计)
9. [限流与配额](#9-限流与配额)
10. [SDK 与客户端生成](#10-sdk-与客户端生成)

---

## 1. API 架构总览

### 1.1 API 分层

```
API 架构
    │
    ├──→ 边缘层（Edge）
    │       ├──→ CDN 缓存
    │       ├──→ DDoS 防护
    │       └──→ WAF
    │
    ├──→ 网关层（API Gateway）
    │       ├──→ 路由
    │       ├──→ 认证
    │       ├──→ 限流
    │       ├──→ 请求合并
    │       └──→ 日志/追踪
    │
    ├──→ BFF 层（Backend for Frontend）
    │       ├──→ Web BFF
    │       ├──→ Mobile BFF
    │       └──→ CLI BFF
    │
    ├──→ 服务层（Microservices）
    │       ├──→ REST API（CRUD 操作）
    │       ├──→ GraphQL（灵活查询）
    │       ├──→ gRPC（内部服务通信）
    │       └──→ WebSocket（实时推送）
    │
    └──→ 数据层
            ├──→ 同步查询（PostgreSQL/Neo4j）
            └──→ 异步处理（消息队列）
```

### 1.2 协议选择矩阵

| 场景 | 协议 | 理由 |
|------|------|------|
| **CRUD 操作** | REST | 简单、缓存友好、标准化 |
| **复杂查询** | GraphQL | 减少请求次数、精确字段选择 |
| **实时协作** | WebSocket | 双向通信、低延迟 |
| **内部服务** | gRPC | 高性能、强类型、流支持 |
| **文件上传** | REST (multipart) | 标准支持、可断点续传 |
| **事件推送** | SSE (Server-Sent Events) | 单向实时、自动重连 |

---

## 2. REST API 设计

### 2.1 URL 规范

```
API Base: https://api.udify.dev/v1

# 项目资源
GET    /projects                    # 列表（支持过滤、分页、排序）
POST   /projects                    # 创建
GET    /projects/{id}               # 详情
PATCH  /projects/{id}               # 部分更新
PUT    /projects/{id}               # 完整替换
DELETE /projects/{id}               # 删除

# 项目子资源
GET    /projects/{id}/dag           # 获取 DAG
PUT    /projects/{id}/dag           # 更新 DAG
GET    /projects/{id}/patches       # 获取 Patch 列表
POST   /projects/{id}/patches       # 创建 Patch
GET    /projects/{id}/patches/{pid} # 获取 Patch 详情
POST   /projects/{id}/patches/{pid}/execute  # 执行 Patch
POST   /projects/{id}/patches/{pid}/rollback # 回滚 Patch

# 执行相关
GET    /projects/{id}/executions              # 执行历史
GET    /projects/{id}/executions/{eid}        # 执行详情
GET    /projects/{id}/executions/{eid}/logs   # 执行日志
GET    /projects/{id}/executions/{eid}/output # 执行输出

# 意图处理
POST   /intents/recognize          # 意图识别
POST   /intents/structured         # 结构化意图

# 内容分析
POST   /content/parse              # 解析内容
POST   /content/analyze            # 分析内容
GET    /content/engines            # 支持的引擎列表

# 模板
GET    /templates                  # 模板列表
GET    /templates/{id}             # 模板详情
POST   /templates/{id}/apply       # 应用模板

# 用户
GET    /users/me                   # 当前用户
PATCH  /users/me                   # 更新用户
GET    /users/me/projects          # 我的项目
GET    /users/me/stats             # 用户统计

# 社区
GET    /discover/trending          # Trending
GET    /discover/search            # 搜索
POST   /projects/{id}/endorse      # 点赞
POST   /projects/{id}/fork         # Fork

# 经济
GET    /marketplace/assets         # 资产市场
POST   /transactions               # 创建交易
GET    /transactions               # 交易历史
```

### 2.2 响应格式

```json
// 标准成功响应
{
  "success": true,
  "data": { ... },
  "meta": {
    "request_id": "req_abc123",
    "timestamp": "2026-04-27T10:00:00Z"
  }
}

// 列表响应
{
  "success": true,
  "data": {
    "items": [ ... ],
    "pagination": {
      "page": 1,
      "page_size": 20,
      "total": 150,
      "has_next": true,
      "has_prev": false
    }
  }
}

// 错误响应
{
  "success": false,
  "error": {
    "code": "PROJECT_NOT_FOUND",
    "message": "Project with ID 'abc123' not found",
    "details": {
      "project_id": "abc123"
    },
    "help_url": "https://docs.udify.dev/errors/PROJECT_NOT_FOUND"
  },
  "meta": {
    "request_id": "req_def456",
    "timestamp": "2026-04-27T10:00:00Z"
  }
}
```

### 2.3 HTTP 状态码映射

| 状态码 | 场景 | 示例 |
|--------|------|------|
| **200 OK** | 成功 | GET 请求成功 |
| **201 Created** | 创建成功 | POST 创建资源 |
| **202 Accepted** | 已接受，异步处理 | 提交执行请求 |
| **204 No Content** | 成功但无返回 | DELETE 成功 |
| **400 Bad Request** | 请求参数错误 | 缺少必填字段 |
| **401 Unauthorized** | 未认证 | Token 缺失/过期 |
| **403 Forbidden** | 无权限 | 尝试修改他人项目 |
| **404 Not Found** | 资源不存在 | 项目 ID 不存在 |
| **409 Conflict** | 资源冲突 | 名称已存在 |
| **422 Unprocessable** | 语义错误 | Patch 验证失败 |
| **429 Too Many Requests** | 限流 | 超出配额 |
| **500 Internal Error** | 服务器错误 | 内部异常 |
| **502 Bad Gateway** | 上游错误 | LLM 服务不可用 |
| **503 Service Unavailable** | 服务不可用 | 维护中 |

---

## 3. GraphQL API

### 3.1 Schema 设计

```graphql
# schema.graphql

scalar DateTime
scalar JSON
scalar UUID

# ===== 查询 =====

type Query {
  # 项目查询
  project(id: UUID!): Project
  projects(
    filter: ProjectFilter
    sort: ProjectSort
    pagination: PaginationInput
  ): ProjectConnection!
  
  # 用户查询
  me: User!
  user(id: UUID!): User
  
  # 内容查询
  search(query: String!, type: SearchType): SearchResult!
  trending(period: TrendingPeriod!, limit: Int): [Project!]!
  
  # 模板查询
  templates(filter: TemplateFilter): [Template!]!
  template(id: UUID!): Template
  
  # 实时状态
  executionStatus(executionId: UUID!): ExecutionStatus
}

# ===== 变更 =====

type Mutation {
  # 项目变更
  createProject(input: CreateProjectInput!): Project!
  updateProject(id: UUID!, input: UpdateProjectInput!): Project!
  deleteProject(id: UUID!): Boolean!
  
  # DAG 变更
  updateDag(projectId: UUID!, input: DagInput!): Dag!
  
  # Patch 变更
  createPatch(projectId: UUID!, input: CreatePatchInput!): Patch!
  executePatch(projectId: UUID!, patchId: UUID!): Execution!
  rollbackPatch(projectId: UUID!, patchId: UUID!): Patch!
  
  # 社区变更
  endorseProject(id: UUID!): Project!
  forkProject(id: UUID!, input: ForkInput): Project!
  
  # 意图处理
  recognizeIntent(input: IntentInput!): IntentResult!
}

# ===== 订阅 =====

type Subscription {
  # 执行进度
  executionProgress(executionId: UUID!): ExecutionUpdate!
  
  # 协作更新
  projectUpdates(projectId: UUID!): ProjectUpdate!
  
  # 通知
  userNotifications: Notification!
}

# ===== 类型定义 =====

type Project {
  id: UUID!
  name: String!
  slug: String!
  description: String
  mediaType: MediaType!
  targetGame: String
  targetEngine: String
  status: ProjectStatus!
  visibility: Visibility!
  aiAutomationLevel: AutomationLevel
  
  # 关联
  owner: User!
  dag: Dag
  patches: [Patch!]!
  executions: [Execution!]!
  forks: [Project!]!
  parent: Project
  
  # 统计
  viewCount: Int!
  downloadCount: Int!
  endorsementCount: Int!
  ratingAverage: Float
  ratingCount: Int!
  
  # 时间戳
  createdAt: DateTime!
  updatedAt: DateTime!
  publishedAt: DateTime
}

type Patch {
  id: UUID!
  project: Project!
  intent: Intent!
  status: PatchStatus!
  riskLevel: RiskLevel!
  
  operations: [Operation!]!
  evaluation: Evaluation
  execution: Execution
  
  requiresHumanApproval: Boolean!
  approvedBy: User
  
  createdAt: DateTime!
  appliedAt: DateTime
}

type Operation {
  id: UUID!
  type: OperationType!
  target: String!
  propertyChanges: JSON
  reason: String
  riskLevel: RiskLevel!
}

type Execution {
  id: UUID!
  patch: Patch!
  status: ExecutionStatus!
  progress: Float
  
  startedAt: DateTime
  completedAt: DateTime
  durationMs: Int
  
  logs: [LogEntry!]!
  output: JSON
  errors: [String!]!
}

type Dag {
  nodes: [DagNode!]!
  edges: [DagEdge!]!
  viewport: Viewport
}

type DagNode {
  id: String!
  type: String!
  position: Position!
  data: JSON!
}

type DagEdge {
  id: String!
  source: String!
  target: String!
  type: String
  data: JSON
}

type User {
  id: UUID!
  username: String!
  displayName: String
  avatar: String
  
  reputation: Reputation!
  badges: [String!]!
  subscriptionTier: String!
  
  projects: [Project!]!
  followers: Int!
  following: Int!
}

type Reputation {
  creator: Int!
  curator: Int!
  technical: Int!
  governance: Int!
}

type Evaluation {
  quality: Float!
  innovation: Float!
  compatibility: Float!
  safety: Float!
  performance: Float!
  overall: Float!
}

# ===== 输入类型 =====

input CreateProjectInput {
  name: String!
  description: String
  mediaType: MediaType!
  targetGame: String
  targetEngine: String
  visibility: Visibility = PUBLIC
}

input IntentInput {
  naturalLanguage: String!
  mediaType: MediaType
  targetEngine: String
}

input PaginationInput {
  page: Int = 1
  pageSize: Int = 20
}

input ProjectFilter {
  mediaType: MediaType
  engineType: String
  status: ProjectStatus
  visibility: Visibility
  tags: [String!]
  searchQuery: String
}

# ===== 枚举 =====

enum MediaType {
  GAME
  MUSIC
  VIDEO
  NOVEL
}

enum ProjectStatus {
  DRAFT
  PUBLISHED
  ARCHIVED
}

enum Visibility {
  PUBLIC
  PRIVATE
  UNLISTED
}

enum PatchStatus {
  PENDING
  APPROVED
  APPLIED
  ROLLED_BACK
  FAILED
}

enum ExecutionStatus {
  QUEUED
  RUNNING
  SUCCESS
  FAILED
  TIMEOUT
}

enum RiskLevel {
  LOW
  MEDIUM
  HIGH
  CRITICAL
}

enum OperationType {
  MODIFY_NODE
  ADD_NODE
  REMOVE_NODE
  ADD_EDGE
  REMOVE_EDGE
  REPLACE_ASSET
  MODIFY_SCRIPT
}

enum AutomationLevel {
  NONE
  ASSISTED
  HYBRID
  FULLY_AUTOMATED
}
```

### 3.2 GraphQL 解析器示例

```python
# udify/api/graphql/resolvers.py

from ariadne import QueryType, MutationType, SubscriptionType
from ariadne.contrib.federation import FederatedObjectType

query = QueryType()
mutation = MutationType()
subscription = SubscriptionType()

# ===== Query Resolvers =====

@query.field("project")
async def resolve_project(_, info, id):
    """解析项目查询"""
    loader = info.context["loaders"]["project"]
    return await loader.load(id)

@query.field("projects")
async def resolve_projects(_, info, filter=None, sort=None, pagination=None):
    """解析项目列表查询"""
    db = info.context["db"]
    
    # 构建查询
    query = select(Project).where(Project.visibility == "public")
    
    # 应用过滤
    if filter:
        if filter.get("mediaType"):
            query = query.where(Project.media_type == filter["mediaType"])
        if filter.get("engineType"):
            query = query.where(Project.target_engine == filter["engineType"])
        if filter.get("searchQuery"):
            query = query.where(
                Project.search_vector.match(filter["searchQuery"])
            )
    
    # 应用排序
    if sort:
        if sort.get("field") == "rating":
            query = query.order_by(Project.rating_average.desc())
        elif sort.get("field") == "created":
            query = query.order_by(Project.created_at.desc())
    
    # 分页
    page = pagination.get("page", 1) if pagination else 1
    page_size = pagination.get("pageSize", 20) if pagination else 20
    
    # 执行查询
    result = await db.execute(query.offset((page - 1) * page_size).limit(page_size))
    items = result.scalars().all()
    
    # 获取总数
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()
    
    return {
        "items": items,
        "page": page,
        "pageSize": page_size,
        "total": total,
        "hasNext": total > page * page_size,
    }

# ===== Mutation Resolvers =====

@mutation.field("createProject")
async def resolve_create_project(_, info, input):
    """创建项目"""
    db = info.context["db"]
    user = info.context["user"]
    
    project = Project(
        name=input["name"],
        slug=slugify(input["name"]),
        description=input.get("description"),
        media_type=input["mediaType"],
        target_game=input.get("targetGame"),
        target_engine=input.get("targetEngine"),
        visibility=input.get("visibility", "public"),
        owner_id=user.id,
    )
    
    db.add(project)
    await db.commit()
    
    return project

@mutation.field("executePatch")
async def resolve_execute_patch(_, info, projectId, patchId):
    """执行 Patch"""
    user = info.context["user"]
    
    # 验证权限
    patch = await get_patch(patchId)
    if patch.project.owner_id != user.id:
        raise Forbidden("Not authorized to execute this patch")
    
    # 提交异步执行
    execution = await submit_execution(projectId, patchId, user.id)
    
    return execution

# ===== Subscription Resolvers =====

@subscription.source("executionProgress")
async def execution_progress_source(_, info, executionId):
    """执行进度订阅源"""
    redis = info.context["redis"]
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"execution:{executionId}")
    
    async for message in pubsub.listen():
        if message["type"] == "message":
            yield json.loads(message["data"])

@subscription.field("executionProgress")
def execution_progress_resolver(update, info, executionId):
    """执行进度解析"""
    return ExecutionUpdate(
        execution_id=executionId,
        status=update["status"],
        progress=update.get("progress"),
        current_step=update.get("current_step"),
        logs=update.get("logs", []),
    )
```

---

## 4. WebSocket 实时 API

### 4.1 协议设计

```json
// 客户端 → 服务器：订阅执行进度
{
  "type": "subscribe",
  "channel": "execution:abc123",
  "auth": "Bearer eyJhbGciOiJIUzI1NiIs..."
}

// 服务器 → 客户端：进度更新
{
  "type": "message",
  "channel": "execution:abc123",
  "data": {
    "status": "running",
    "progress": 45,
    "current_step": "op-003",
    "logs": ["Extracting textures...", "Modifying enemy stats..."],
    "timestamp": "2026-04-27T10:00:00Z"
  }
}

// 客户端 → 服务器：协作光标位置
{
  "type": "cursor",
  "project_id": "proj-456",
  "position": {"x": 320, "y": 180},
  "selection": ["node-001", "node-002"]
}

// 服务器 → 客户端：广播光标位置
{
  "type": "cursor_update",
  "project_id": "proj-456",
  "user": {
    "id": "user-789",
    "name": "Alice",
    "color": "#3B82F6"
  },
  "position": {"x": 320, "y": 180},
  "selection": ["node-001"]
}

// 服务器 → 客户端：协作 DAG 变更
{
  "type": "dag_update",
  "project_id": "proj-456",
  "changes": [
    {
      "type": "node_add",
      "data": {
        "id": "node-new-1",
        "type": "operation",
        "position": {"x": 400, "y": 300},
        "data": {"label": "New Op", "status": "pending"}
      }
    }
  ],
  "timestamp": "2026-04-27T10:00:01Z"
}
```

### 4.2 WebSocket 服务实现

```python
# udify/api/websocket/server.py

from fastapi import WebSocket, WebSocketDisconnect
from typing import Dict, Set
import json
import asyncio

class CollaborationManager:
    """WebSocket 协作管理器"""
    
    def __init__(self):
        # project_id -> {user_id -> WebSocket}
        self.project_rooms: Dict[str, Dict[str, WebSocket]] = {}
        
        # user_id -> {project_id}
        self.user_projects: Dict[str, Set[str]] = {}
    
    async def connect(self, websocket: WebSocket, project_id: str, user_id: str):
        """用户连接到项目"""
        await websocket.accept()
        
        # 加入房间
        if project_id not in self.project_rooms:
            self.project_rooms[project_id] = {}
        self.project_rooms[project_id][user_id] = websocket
        
        if user_id not in self.user_projects:
            self.user_projects[user_id] = set()
        self.user_projects[user_id].add(project_id)
        
        # 广播用户加入
        await self.broadcast_to_project(
            project_id,
            {
                "type": "user_joined",
                "user": {"id": user_id},
            },
            exclude_user=user_id,
        )
    
    async def disconnect(self, project_id: str, user_id: str):
        """用户断开连接"""
        if project_id in self.project_rooms:
            self.project_rooms[project_id].pop(user_id, None)
            if not self.project_rooms[project_id]:
                del self.project_rooms[project_id]
        
        self.user_projects.get(user_id, set()).discard(project_id)
        
        # 广播用户离开
        await self.broadcast_to_project(
            project_id,
            {
                "type": "user_left",
                "user": {"id": user_id},
            },
        )
    
    async def broadcast_to_project(
        self,
        project_id: str,
        message: dict,
        exclude_user: str = None,
    ):
        """广播消息到项目所有参与者"""
        if project_id not in self.project_rooms:
            return
        
        message_json = json.dumps(message)
        
        # 并行发送
        tasks = []
        for user_id, websocket in self.project_rooms[project_id].items():
            if user_id != exclude_user:
                tasks.append(self._send_safe(websocket, message_json))
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _send_safe(self, websocket: WebSocket, message: str):
        """安全发送（忽略已断开连接）"""
        try:
            await websocket.send_text(message)
        except Exception:
            pass  # 连接已关闭
    
    async def handle_message(self, websocket: WebSocket, project_id: str, user_id: str, raw_message: str):
        """处理客户端消息"""
        try:
            message = json.loads(raw_message)
            msg_type = message.get("type")
            
            if msg_type == "cursor":
                # 广播光标位置
                await self.broadcast_to_project(
                    project_id,
                    {
                        "type": "cursor_update",
                        "user": {"id": user_id},
                        "position": message["position"],
                        "selection": message.get("selection", []),
                    },
                    exclude_user=user_id,
                )
            
            elif msg_type == "dag_change":
                # 广播 DAG 变更
                await self.broadcast_to_project(
                    project_id,
                    {
                        "type": "dag_update",
                        "changes": message["changes"],
                        "timestamp": datetime.utcnow().isoformat(),
                    },
                    exclude_user=user_id,
                )
            
            elif msg_type == "subscribe_execution":
                # 订阅执行进度（通过 Redis Pub/Sub）
                execution_id = message["execution_id"]
                asyncio.create_task(
                    self._relay_execution_updates(websocket, execution_id)
                )
                
        except json.JSONDecodeError:
            await websocket.send_json({"type": "error", "message": "Invalid JSON"})
    
    async def _relay_execution_updates(self, websocket: WebSocket, execution_id: str):
        """从 Redis 转发执行更新到 WebSocket"""
        redis = get_redis()
        pubsub = redis.pubsub()
        await pubsub.subscribe(f"execution:{execution_id}")
        
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    await websocket.send_text(message["data"])
        except Exception:
            pass
        finally:
            await pubsub.unsubscribe(f"execution:{execution_id}")


# FastAPI WebSocket Endpoint
from fastapi import APIRouter, WebSocket, Depends

ws_router = APIRouter()
manager = CollaborationManager()

@ws_router.websocket("/ws/projects/{project_id}")
async def project_websocket(websocket: WebSocket, project_id: str, token: str):
    """项目协作 WebSocket"""
    # 验证 token
    user = await verify_websocket_token(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return
    
    # 验证项目访问权限
    if not await can_access_project(user.id, project_id):
        await websocket.close(code=4003, reason="Forbidden")
        return
    
    await manager.connect(websocket, project_id, user.id)
    
    try:
        while True:
            raw_message = await websocket.receive_text()
            await manager.handle_message(websocket, project_id, user.id, raw_message)
    except WebSocketDisconnect:
        await manager.disconnect(project_id, user.id)
```

---

## 5. API 版本控制策略

### 5.1 版本策略对比

| 策略 | 实现方式 | 优点 | 缺点 | 适用场景 |
|------|---------|------|------|---------|
| **URL 路径** | `/v1/`, `/v2/` | 简单直观 | URL 混乱 | 外部 API |
| **Header** | `Accept: application/vnd.udify.v2+json` | URL 干净 | 不够直观 | 内部 API |
| **查询参数** | `?version=2` | 灵活 | 不规范 | 不推荐 |
| **GraphQL** | Schema 版本 | 字段级 | 复杂 | GraphQL |

**Udify 采用**：URL 路径（REST）+ Schema 演进（GraphQL）

### 5.2 REST 版本控制实现

```python
# udify/api/versions.py

from fastapi import APIRouter, Depends, Header, HTTPException

class APIVersion:
    CURRENT = "v1"
    SUPPORTED = ["v1"]
    DEPRECATED = []
    SUNSET = {}  # version -> sunset_date

def version_dependency(version: str = Path(..., regex=r"^v\d+$")):
    """版本依赖注入"""
    if version in APIVersion.SUNSET:
        sunset_date = APIVersion.SUNSET[version]
        if datetime.utcnow() > sunset_date:
            raise HTTPException(
                status_code=410,
                detail=f"API version {version} has been sunset. Please migrate to {APIVersion.CURRENT}",
            )
    
    if version in APIVersion.DEPRECATED:
        # 返回 Deprecation 头
        pass
    
    if version not in APIVersion.SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"API version {version} not supported. Supported: {APIVersion.SUPPORTED}",
        )
    
    return version

# 路由注册
router = APIRouter(prefix="/{version}", dependencies=[Depends(version_dependency)])

@router.get("/projects")
async def list_projects(version: str):
    if version == "v1":
        return await list_projects_v1()
    elif version == "v2":
        return await list_projects_v2()
```

### 5.3 版本迁移指南

```yaml
# api-versions.yml

versions:
  v1:
    status: current
    release_date: "2026-01-01"
    deprecated: false
    
  v2:
    status: beta
    release_date: "2026-07-01"
    changes:
      - "Project.reviewCount renamed to Project.ratingCount"
      - "POST /projects/{id}/execute now returns 202 instead of 200"
      - "Added GraphQL subscription for real-time updates"
      - "Removed deprecated field: Project.downloadUrl (use Project.assets)"
    
    migration_guide: |
      1. Update all references from `reviewCount` to `ratingCount`
      2. Handle 202 status for async execution endpoints
      3. Migrate polling to WebSocket subscriptions
      4. Update asset download logic
    
    backward_compatibility:
      v1: true  # v2 服务端兼容 v1 客户端
      shim_available: true
```

---

## 6. 认证与授权

### 6.1 认证流程

```
认证架构
    │
    ├──→ Session-based（Web App）
    │       ├──→ 登录 → JWT Access Token + Refresh Token
    │       ├──→ Access Token: 15 分钟，HTTP-only cookie
    │       ├──→ Refresh Token: 7 天，HTTP-only cookie
    │       └──→ 自动刷新（Access Token 过期前）
    │
    ├──→ API Key（程序化访问）
    │       ├──→ 用户生成 API Key
    │       ├──→ 存储哈希（bcrypt）
    │       └──→ Header: `X-API-Key: uk_...`
    │
    └──→ OAuth 2.0（第三方集成）
            ├──→ Authorization Code + PKCE
            ├──→ Scope: read, write, execute
            └──→ Token introspection
```

### 6.2 中间件实现

```python
# udify/api/middleware/auth.py

from fastapi import Request, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from datetime import datetime, timedelta

security = HTTPBearer(auto_error=False)

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """获取当前认证用户"""
    
    # 1. 从 Header 获取 Token
    if not credentials:
        # 尝试从 Cookie 获取
        token = request.cookies.get("access_token")
        if not token:
            raise HTTPException(status_code=401, detail="Not authenticated")
    else:
        token = credentials.credentials
    
    # 2. 验证 Token
    try:
        payload = jwt.decode(
            token,
            key=JWT_SECRET_KEY,
            algorithms=["HS256"],
            audience="udify-api",
            issuer="udify-auth",
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    
    # 3. 获取用户
    user_id = payload.get("sub")
    user = await get_user_by_id(user_id)
    
    if not user or user.account_status != "active":
        raise HTTPException(status_code=401, detail="User not found or inactive")
    
    # 4. 检查 Token 版本（用于强制登出）
    if payload.get("token_version") != user.token_version:
        raise HTTPException(status_code=401, detail="Token revoked")
    
    # 5. 附加到请求上下文
    request.state.user = user
    
    return user


async def require_permissions(*permissions: str):
    """权限要求装饰器"""
    async def checker(user: User = Depends(get_current_user)):
        user_permissions = await get_user_permissions(user.user_id)
        
        for permission in permissions:
            if permission not in user_permissions:
                raise HTTPException(
                    status_code=403,
                    detail=f"Missing permission: {permission}",
                )
        
        return user
    return checker


# 使用示例
from fastapi import APIRouter

router = APIRouter()

@router.post("/projects/{id}/execute")
async def execute_project(
    project_id: UUID,
    user: User = Depends(require_permissions("project:execute")),
):
    """执行项目（需要 execute 权限）"""
    pass
```

---

## 7. OpenAPI 规范

### 7.1 自动生成的 OpenAPI

```python
# udify/api/main.py

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

app = FastAPI(
    title="Udify API",
    description="""
    # Udify API
    
    The Udify API allows you to:
    - Manage content transformation projects
    - Generate and execute transformation patches
    - Browse and share community creations
    - Manage creator economy transactions
    
    ## Authentication
    All API requests require authentication via Bearer token or API key.
    
    ## Rate Limits
    - Free tier: 100 requests/day
    - Pro tier: 10,000 requests/day
    - Team tier: 100,000 requests/day
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={
        "name": "Udify API Support",
        "url": "https://udify.dev/support",
        "email": "api@udify.dev",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# 自定义 OpenAPI 生成
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title="Udify API",
        version="1.0.0",
        description="AI-powered content transformation platform",
        routes=app.routes,
    )
    
    # 添加安全方案
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Enter your JWT token",
        },
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
            "description": "Enter your API key",
        },
    }
    
    # 添加全局安全
    openapi_schema["security"] = [
        {"BearerAuth": []},
        {"ApiKeyAuth": []},
    ]
    
    # 添加标签分组
    openapi_schema["tags"] = [
        {"name": "Projects", "description": "Project management"},
        {"name": "Patches", "description": "Transformation patches"},
        {"name": "Executions", "description": "Execution management"},
        {"name": "Intents", "description": "Intent recognition"},
        {"name": "Users", "description": "User management"},
        {"name": "Community", "description": "Community features"},
        {"name": "Marketplace", "description": "Creator economy"},
    ]
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi
```

### 7.2 SDK 生成

```bash
# 从 OpenAPI 生成 TypeScript SDK
npx openapi-typescript https://api.udify.dev/openapi.json \
  --output frontend/lib/api.types.ts

# 生成 Python SDK
openapi-generator-cli generate \
  -i https://api.udify.dev/openapi.json \
  -g python \
  -o sdk/python \
  --additional-properties=packageName=udify_client

# 生成 Go SDK
openapi-generator-cli generate \
  -i https://api.udify.dev/openapi.json \
  -g go \
  -o sdk/go \
  --additional-properties=packageName=udify
```

---

## 8. API 网关设计

### 8.1 Kong Gateway 配置

```yaml
# kong.yml

_format_version: "3.0"
_transform: true

services:
  - name: udify-api
    url: http://udify-api.udify.svc.cluster.local:8000
    routes:
      - name: api-v1
        paths:
          - /v1
        strip_path: false
        preserve_host: true
      
      - name: api-v2
        paths:
          - /v2
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 100
          policy: redis
          redis_host: redis.udify.svc.cluster.local
          fault_tolerant: true
          hide_client_headers: false
      
      - name: cors
        config:
          origins:
            - "https://udify.dev"
            - "https://app.udify.dev"
          methods:
            - GET
            - POST
            - PUT
            - PATCH
            - DELETE
          headers:
            - Authorization
            - Content-Type
            - X-Request-ID
          max_age: 3600
          credentials: true
      
      - name: request-transformer
        config:
          add:
            headers:
              - X-Request-ID:$(uuid)
              - X-Forwarded-For:$(client_ip)
      
      - name: prometheus
        config:
          per_consumer: true
      
      - name: opentelemetry
        config:
          endpoint: http://otel-collector.monitoring.svc.cluster.local:4318
          resource_attributes:
            service.name: udify-gateway

consumers:
  - username: udify-cli
    keyauth_credentials:
      - key: uk_cli_...
  
  - username: udify-web
    jwt_credentials:
      - algorithm: HS256
        key: udify-web

plugins:
  - name: key-auth
    service: udify-api
    config:
      key_names:
        - X-API-Key
      hide_credentials: true
  
  - name: jwt
    service: udify-api
    config:
      uri_param_names: []
      cookie_names: []
      key_claim_name: iss
      secret_is_base64: false
      claims_to_verify:
        - exp
```

---

## 9. 限流与配额

### 9.1 分级限流

```python
# udify/api/rate_limit.py

from fastapi import Request, HTTPException
from redis.asyncio import Redis
import time

class RateLimiter:
    """多级速率限制器"""
    
    def __init__(self, redis: Redis):
        self.redis = redis
        self.limits = {
            # 全局限制（所有用户）
            "global": {"requests": 10000, "window": 60},
            
            # 按用户等级
            "free": {"requests": 100, "window": 86400},      # 100/天
            "pro": {"requests": 10000, "window": 86400},     # 10K/天
            "team": {"requests": 100000, "window": 86400},   # 100K/天
            "enterprise": {"requests": 1000000, "window": 86400},
            
            # 按端点
            "intent": {"requests": 10, "window": 60},        # 意图识别 10/分钟
            "execute": {"requests": 5, "window": 60},        # 执行 5/分钟
            "upload": {"requests": 10, "window": 60},        # 上传 10/分钟
            "search": {"requests": 60, "window": 60},        # 搜索 60/分钟
        }
    
    async def check(self, request: Request, user: User) -> dict:
        """检查速率限制"""
        
        now = int(time.time())
        client_id = user.user_id if user else request.client.host
        tier = user.subscription_tier if user else "anonymous"
        
        # 检查全局限制
        global_key = f"ratelimit:global:{now // self.limits['global']['window']}"
        global_count = await self.redis.incr(global_key)
        if global_count == 1:
            await self.redis.expire(global_key, self.limits["global"]["window"])
        
        if global_count > self.limits["global"]["requests"]:
            raise HTTPException(status_code=503, detail="Service temporarily unavailable")
        
        # 检查用户等级限制
        tier_key = f"ratelimit:{tier}:{client_id}:{now // self.limits[tier]['window']}"
        tier_count = await self.redis.incr(tier_key)
        if tier_count == 1:
            await self.redis.expire(tier_key, self.limits[tier]["window"])
        
        remaining = max(0, self.limits[tier]["requests"] - tier_count)
        
        if tier_count > self.limits[tier]["requests"]:
            reset_time = (now // self.limits[tier]["window"] + 1) * self.limits[tier]["window"]
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={
                    "X-RateLimit-Limit": str(self.limits[tier]["requests"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time - now),
                },
            )
        
        # 检查端点特定限制
        endpoint = self._get_endpoint_category(request)
        if endpoint in self.limits:
            ep_key = f"ratelimit:ep:{endpoint}:{client_id}:{now // self.limits[endpoint]['window']}"
            ep_count = await self.redis.incr(ep_key)
            if ep_count == 1:
                await self.redis.expire(ep_key, self.limits[endpoint]["window"])
            
            if ep_count > self.limits[endpoint]["requests"]:
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded for {endpoint}",
                )
        
        return {
            "limit": self.limits[tier]["requests"],
            "remaining": remaining,
            "reset": (now // self.limits[tier]["window"] + 1) * self.limits[tier]["window"],
        }
    
    def _get_endpoint_category(self, request: Request) -> str:
        """获取端点分类"""
        path = request.url.path
        
        if "/intents" in path:
            return "intent"
        elif "/execute" in path:
            return "execute"
        elif "/upload" in path:
            return "upload"
        elif "/search" in path:
            return "search"
        
        return "default"
```

---

## 10. SDK 与客户端生成

### 10.1 TypeScript SDK

```typescript
// sdk/typescript/src/client.ts

import { createClient, type NormalizeOAS, type OASClient } from 'fets';
import type openapi from './openapi.types';

export type UdifyClient = OASClient<NormalizeOAS<typeof openapi>>;

export interface UdifyConfig {
  baseUrl?: string;
  apiKey?: string;
  accessToken?: string;
  timeout?: number;
}

export function createUdifyClient(config: UdifyConfig = {}): UdifyClient {
  const baseUrl = config.baseUrl || 'https://api.udify.dev/v1';
  
  return createClient<NormalizeOAS<typeof openapi>>({
    endpoint: baseUrl,
    globalParams: {
      headers: {
        ...(config.apiKey && { 'X-API-Key': config.apiKey }),
        ...(config.accessToken && { 'Authorization': `Bearer ${config.accessToken}` }),
      },
    },
    fetchFn: (url, init) => {
      const controller = new AbortController();
      const timeout = config.timeout || 30000;
      
      const timeoutId = setTimeout(() => controller.abort(), timeout);
      
      return fetch(url, {
        ...init,
        signal: controller.signal,
      }).finally(() => clearTimeout(timeoutId));
    },
  });
}

// 使用示例
const client = createUdifyClient({
  accessToken: 'eyJhbGciOiJIUzI1NiIs...',
});

// Type-safe API 调用
const project = await client['/projects/{id}'].get({
  params: {
    id: '123e4567-e89b-12d3-a456-426614174000',
  },
});

// 自动类型推断：project 类型为 Project
console.log(project.name);  // ✅ TypeScript 知道 name 存在
```

---

> **"API 是产品的契约。好的 API 设计让开发者感到被尊重——一致的命名、清晰的错误、完善的文档。Udify 的 API 不仅是功能接口，更是创作者与平台之间的信任纽带。"**
>
> —— Udify API 设计原则
