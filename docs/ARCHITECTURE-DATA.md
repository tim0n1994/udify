# Udify 数据架构与存储设计

> **版本**: v1.0 | **日期**: 2026-04-27 | **状态**: 详细设计文档
>
> **范围**: CDL 持久化、图数据库 Schema、关系数据库、向量数据库、版本控制、缓存、数据流

---

## 目录

1. [存储架构总览](#1-存储架构总览)
2. [CDL 持久化层](#2-cdl-持久化层)
3. [图数据库设计（Neo4j）](#3-图数据库设计neo4j)
4. [关系数据库设计（PostgreSQL）](#4-关系数据库设计postgresql)
5. [向量数据库（Pinecone）](#5-向量数据库pinecone)
6. [版本控制系统（DVC + Git-like）](#6-版本控制系统dvc--git-like)
7. [缓存层（Redis）](#7-缓存层redis)
8. [对象存储（S3-compatible）](#8-对象存储s3-compatible)
9. [数据流与一致性](#9-数据流与一致性)
10. [多租户数据隔离](#10-多租户数据隔离)

---

## 1. 存储架构总览

### 1.1 数据分类

```
Udify 数据分类
    │
    ├──→ 结构化数据 (PostgreSQL)
    │       ├──→ 用户账户、项目元数据
    │       ├──→ 交易、订阅、支付
    │       ├──→ 社区互动（评论、点赞）
    │       └──→ 治理数据（审核、举报）
    │
    ├──→ 图数据 (Neo4j)
    │       ├──→ CDL 内容图（节点、边、关系）
    │       ├──→ 依赖图（Mod 依赖关系）
    │       ├──→ 知识图谱（游戏机制、实体关系）
    │       └──→ 社交图（用户关系、协作网络）
    │
    ├──→ 向量数据 (Pinecone)
    │       ├──→ 用户偏好嵌入
    │       ├──→ 内容语义嵌入
    │       ├──→ 模板检索索引
    │       └──→ 意图分类向量
    │
    ├──→ 时序数据 (TimescaleDB / PostgreSQL)
    │       ├──→ 执行日志
    │       ├──→ 性能指标
    │       ├──→ 用户行为事件
    │       └──→ 系统监控数据
    │
    ├──→ 对象存储 (S3 / MinIO)
    │       ├──→ 原始游戏文件（只读镜像）
    │       ├──→ 生成的资源（纹理、模型、音频）
    │       ├──→ Patch 文件
    │       ├──→ 沙箱输出
    │       └──→ 备份/快照
    │
    ├──→ 缓存 (Redis)
    │       ├──→ 会话状态
    │       ├──→ 热点数据
    │       ├──→ 速率限制
    │       ├──→ 分布式锁
    │       └──→ 实时排行榜
    │
    └──→ 版本控制 (DVC + Git)
            ├──→ CDL 文本表示（Git）
            ├──→ 大文件（DVC 追踪）
            ├──→ 模板历史
            └──→ 分支/合并记录
```

### 1.2 技术选型理由

| 存储类型 | 技术 | 理由 |
|---------|------|------|
| **关系数据库** | PostgreSQL 16 | ACID、JSONB 支持、成熟生态、TimescaleDB 扩展 |
| **图数据库** | Neo4j 5.x | 原生图存储、Cypher 查询、APOC/GDS 插件、与 LLM 集成好 |
| **向量数据库** | Pinecone | 托管服务、低延迟、混合搜索、与 LangChain 集成 |
| **对象存储** | MinIO (本地) / S3 (云) | S3 API 标准、DVC 兼容、成本效益 |
| **缓存** | Redis 7 + Valkey (备选) | 高性能、数据结构丰富、分布式锁、Stream 支持 |
| **版本控制** | Git + DVC | 文本 diff、大文件追踪、分支合并、与 GitHub 集成 |
| **时序数据库** | TimescaleDB (PostgreSQL 扩展) | SQL 接口、自动分区、连续聚合、与 PG 生态统一 |

---

## 2. CDL 持久化层

### 2.1 CDL 文本格式（Git-friendly）

CDL 必须能被 Git 有效 diff，因此采用**结构化文本格式**（YAML/JSON 的混合优化版）。

```yaml
# content.cdl
# CDL 文件使用自定义格式，优化 Git diff 友好性

format_version: "2.0"
cdl_id: "uuid-v4"
media_type: "game"
engine_type: "unity"
source_path: "/games/slay-the-spire/"
created_at: "2026-04-27T10:00:00Z"
modified_at: "2026-04-27T10:00:00Z"

# 节点按类型分组，便于 diff
nodes:
  # 每种类型单独一个 section，减少无关 diff
  entities:
    - node_id: "entity-001"
      type: "Enemy"
      name: "Cultist"
      properties:
        health: 50
        damage: 6
        intent_pattern: ["attack", "buff"]
      metadata:
        source_file: "Cultist.cs"
        line_range: [45, 120]
    
    - node_id: "entity-002"
      type: "Player"
      name: "Ironclad"
      properties:
        max_health: 80
        starting_deck: ["Strike", "Strike", "Defend", "Defend", "Bash"]
    
    - node_id: "entity-003"
      type: "Card"
      name: "Bash"
      properties:
        cost: 2
        damage: 8
        effect: "apply_vulnerable"
        effect_duration: 2
  
  mechanics:
    - node_id: "mech-001"
      type: "CombatSystem"
      name: "Standard Combat"
      properties:
        turn_based: true
        energy_per_turn: 3
        card_draw_per_turn: 5
  
  resources:
    - node_id: "res-001"
      type: "Texture"
      name: "Cultist_Sprite"
      properties:
        format: "PNG"
        resolution: [256, 256]
        path: "Assets/Textures/Enemies/Cultist.png"
      # 大文件引用使用 DVC 追踪
      content_ref: "dvc://textures/cultist.png@v1"

# 边表示关系
edges:
  - edge_id: "edge-001"
    type: "HAS_COMPONENT"
    source: "entity-001"
    target: "res-001"
    properties:
      component_type: "sprite"
  
  - edge_id: "edge-002"
    type: "USES_MECHANIC"
    source: "entity-001"
    target: "mech-001"
  
  - edge_id: "edge-003"
    type: "HAS_CARD"
    source: "entity-002"
    target: "entity-003"
    properties:
      quantity: 1
      starting: true

# 语义层：人类可读的高层次描述
semantic_layer:
  summary: "Slay the Spire base game content"
  themes: ["roguelike", "deckbuilding", "dark_fantasy"]
  difficulty_curve: "linear_with_spikes"
  
  # 机制图谱
  mechanics_graph:
    - id: "combat_loop"
      description: "Player draws cards → plays cards → enemy acts → repeat"
      participants: ["mech-001", "entity-002", "entity-001"]
    
    - id: "card_interaction"
      description: "Cards consume energy, deal damage, apply effects"
      participants: ["entity-003", "mech-001"]

# 校验和，用于完整性验证
checksum:
  algorithm: "sha256"
  value: "abc123..."
```

### 2.2 CDL Patch 格式

```yaml
# patch.cdl
# 机器可读的改造指令

patch_version: "1.0"
parent_cdl: "uuid-of-original"
patch_id: "uuid-v4"
author: "user-uuid"
created_at: "2026-04-27T10:30:00Z"

# 意图声明（人类可读，用于审计）
intent:
  natural_language: "Make the game feel like Dark Souls"
  structured:
    target_aspect: "difficulty"
    reference_style: "Dark Souls"
    emphasis: ["punishing_combat", "risk_reward", "pattern_learning"]

# 操作序列（DAG）
operations:
  - op_id: "op-001"
    type: "modify_node"
    target: "entity-001"
    property_changes:
      health:
        old: 50
        new: 120
      damage:
        old: 6
        new: 15
    reason: "Increase enemy baseline stats for Dark Souls feel"
    
  - op_id: "op-002"
    type: "modify_node"
    target: "entity-003"
    property_changes:
      cost:
        old: 2
        new: 3
    reason: "Make powerful cards more expensive"
    
  - op_id: "op-003"
    type: "add_node"
    node_id: "entity-new-001"
    node_type: "Mechanic"
    properties:
      name: "DeathDrop"
      description: "On player death, lose all gold and half of unlocked cards"
      trigger: "player_health <= 0"
      effects:
        - "remove_currency:all"
        - "remove_random_cards:50%"
    depends_on: []  # 无依赖
    
  - op_id: "op-004"
    type: "add_edge"
    edge_id: "edge-new-001"
    edge_type: "MODIFIES"
    source: "op-003"
    target: "mech-001"
    reason: "New death mechanic modifies combat system"
    depends_on: ["op-003"]
    
  - op_id: "op-005"
    type: "replace_asset"
    target: "res-001"
    new_asset_ref: "dvc://textures/cultist_dark_souls.png@v2"
    reason: "Resprite enemy to match Dark Souls aesthetic"
    
  - op_id: "op-006"
    type: "modify_script"
    target: "CombatManager.cs"
    modifications:
      - line_range: [200, 220]
        old_code: "player.energy = 3;"
        new_code: "player.energy = 2;  // Dark Souls: reduced energy"
      - line_range: [350, 360]
        insertion: |
          // Dark Souls addition: healing items are rare
          if (player.potions > 0) {
              player.potion_effectiveness *= 0.5;
          }
    reason: "Reduce resource generosity"
    # 脚本修改需要特别小心，标记为高风险
    risk_level: "high"
    requires_human_approval: true

# 依赖图（自动从 operations 推导，但可显式声明）
dependency_graph:
  - op_id: "op-004"
    prerequisites: ["op-003"]
  - op_id: "op-006"
    prerequisites: ["op-001", "op-002"]

# 验证规则
validation:
  preconditions:
    - "entity-001 exists"
    - "entity-003 exists"
    - "mech-001 exists"
  
  postconditions:
    - "entity-001.health > entity-001.health_original"
    - "All edges reference existing nodes"
  
  invariants:
    - "No circular dependencies in edges"
    - "All node IDs are unique"
    - "All asset refs are resolvable"

# 回滚信息
rollback:
  reversible: true
  rollback_operations:
    - type: "restore_node"
      target: "entity-001"
      backup_ref: "snapshot://entity-001@pre-op-001"
    - type: "restore_node"
      target: "entity-003"
      backup_ref: "snapshot://entity-003@pre-op-002"
    - type: "remove_node"
      target: "entity-new-001"
    - type: "restore_asset"
      target: "res-001"
      backup_ref: "dvc://textures/cultist.png@v1"
```

### 2.3 CDL 合并语义（解决冲突）

```python
class CDLMerger:
    """CDL Patch 合并引擎"""
    
    def three_way_merge(
        self,
        base: CDLDocument,
        patch_a: CDLPatch,
        patch_b: CDLPatch
    ) -> MergeResult:
        """
        三路合并算法
        
        场景：用户 A 和用户 B 基于同一 base 分别做了修改
        """
        conflicts = []
        merged_ops = []
        
        # 1. 检查操作冲突
        for op_a in patch_a.operations:
            for op_b in patch_b.operations:
                conflict = self._check_conflict(op_a, op_b)
                if conflict:
                    conflicts.append(conflict)
        
        # 2. 自动合并非冲突操作
        non_conflicting_a = [
            op for op in patch_a.operations
            if not any(c.op_a == op for c in conflicts)
        ]
        non_conflicting_b = [
            op for op in patch_b.operations
            if not any(c.op_b == op for c in conflicts)
        ]
        
        merged_ops.extend(non_conflicting_a)
        merged_ops.extend(non_conflicting_b)
        
        # 3. 尝试自动解决冲突
        for conflict in conflicts:
            resolution = self._auto_resolve(conflict)
            if resolution:
                merged_ops.append(resolution)
            else:
                # 需要人工解决
                conflicts.append(conflict)
        
        return MergeResult(
            operations=merged_ops,
            conflicts=conflicts,
            auto_resolved=len(merged_ops) - len(non_conflicting_a) - len(non_conflicting_b),
        )
    
    def _check_conflict(self, op_a: Operation, op_b: Operation) -> Optional[Conflict]:
        """检查两个操作是否冲突"""
        # 规则 1: 修改同一节点的同一属性
        if (op_a.type == "modify_node" and op_b.type == "modify_node" and
            op_a.target == op_b.target):
            common_props = set(op_a.property_changes.keys()) & set(op_b.property_changes.keys())
            if common_props:
                return Conflict(
                    type="property_conflict",
                    op_a=op_a,
                    op_b=op_b,
                    description=f"Both patches modify properties {common_props} of node {op_a.target}",
                )
        
        # 规则 2: 删除被依赖的节点
        if (op_a.type == "remove_node" and 
            op_b.type in ["add_edge", "modify_node"] and
            op_b.target == op_a.target):
            return Conflict(
                type="dependency_conflict",
                op_a=op_a,
                op_b=op_b,
                description=f"Patch A removes node {op_a.target} which Patch B depends on",
            )
        
        # 规则 3: 修改同一脚本的重叠行范围
        if (op_a.type == "modify_script" and op_b.type == "modify_script" and
            op_a.target == op_b.target):
            overlap = self._line_range_overlap(
                op_a.modifications[0].line_range,
                op_b.modifications[0].line_range
            )
            if overlap:
                return Conflict(
                    type="script_overlap",
                    op_a=op_a,
                    op_b=op_b,
                    description=f"Script modifications overlap at lines {overlap}",
                )
        
        return None
    
    def _auto_resolve(self, conflict: Conflict) -> Optional[Operation]:
        """尝试自动解决冲突"""
        if conflict.type == "property_conflict":
            # 策略：如果修改的是不同子属性，可以合并
            # 例如 A 修改 health，B 修改 damage → 不冲突
            # 但如果都修改 health → 无法自动解决
            return None  # 需要人工决策
        
        if conflict.type == "script_overlap":
            # 脚本重叠几乎不可能自动解决
            return None
        
        return None
```

---

## 3. 图数据库设计（Neo4j）

### 3.1 节点标签与属性

```cypher
// 创建约束和索引
CREATE CONSTRAINT content_node_id IF NOT EXISTS
FOR (n:ContentNode) REQUIRE n.node_id IS UNIQUE;

CREATE CONSTRAINT project_id IF NOT EXISTS
FOR (p:Project) REQUIRE p.project_id IS UNIQUE;

CREATE CONSTRAINT user_id IF NOT EXISTS
FOR (u:User) REQUIRE u.user_id IS UNIQUE;

CREATE INDEX content_node_type IF NOT EXISTS
FOR (n:ContentNode) ON (n.node_type);

CREATE INDEX content_node_engine IF NOT EXISTS
FOR (n:ContentNode) ON (n.engine_type);

CREATE INDEX edge_type IF NOT EXISTS
FOR ()-[r:RELATES_TO]-() ON (r.edge_type);
```

### 3.2 核心图谱 Schema

```cypher
// ===== 内容图谱（Content Graph）=====

// 内容节点
(:ContentNode {
  node_id: string,           // UUID
  cdl_id: string,            // 所属 CDL 文档
  node_type: string,         // "Entity" | "Mechanic" | "Resource" | "Level" | "Dialogue" | ...
  media_type: string,        // "game" | "music" | "video" | "novel"
  engine_type: string,       // "unity" | "unreal" | "godot" | "rpgmaker" | ...
  name: string,
  properties: map,           // 灵活属性
  semantic_tags: [string],   // 语义标签
  created_at: datetime,
  modified_at: datetime
})

// 关系边
(:ContentNode)-[:RELATES_TO {
  edge_id: string,
  edge_type: string,         // "HAS_COMPONENT" | "USES_MECHANIC" | "DEPENDS_ON" | "TRIGGERS" | ...
  properties: map,
  weight: float              // 关系强度（用于图算法）
}]->(:ContentNode)

// ===== 项目图谱（Project Graph）=====

(:Project {
  project_id: string,
  name: string,
  description: string,
  media_type: string,
  target_game: string,
  target_engine: string,
  license: string,
  visibility: string,        // "public" | "private" | "unlisted"
  status: string,            // "draft" | "published" | "archived"
  version: string,
  created_at: datetime,
  updated_at: datetime,
  // 统计
  view_count: int,
  download_count: int,
  endorsement_count: int,
  fork_count: int
})

(:Project)-[:HAS_CDL {
  version: string,
  is_current: boolean
}]->(:CDLDocument)

(:Project)-[:APPLIES_PATCH {
  patch_version: string,
  applied_at: datetime,
  status: string             // "applied" | "rolled_back" | "failed"
}]->(:CDLPatch)

(:Project)-[:FORKED_FROM]->(:Project)

// ===== 用户图谱（Social Graph）=====

(:User {
  user_id: string,
  username: string,
  display_name: string,
  email_hash: string,        // 隐私保护
  reputation: map,           // { creator: 850, curator: 420, ... }
  badges: [string],
  created_at: datetime,
  last_active: datetime
})

(:User)-[:AUTHORED {
  role: string               // "primary" | "contributor" | "reviewer"
}]->(:Project)

(:User)-[:ENDORSED {
  timestamp: datetime,
  rating: int                // 1-5
}]->(:Project)

(:User)-[:FOLLOWS]->(:User)

(:User)-[:COLLABORATES_ON {
  role: string,              // "editor" | "reviewer" | "tester"
  joined_at: datetime
}]->(:Project)

// ===== 知识图谱（Knowledge Graph）=====

(:GameConcept {
  concept_id: string,
  name: string,
  concept_type: string,      // "mechanic" | "genre" | "trope" | "difficulty_pattern"
  description: string,
  embedding: vector          // 768-dim，用于语义搜索
})

(:ContentNode)-[:INSTANCE_OF]->(:GameConcept)

(:GameConcept)-[:RELATED_TO {
  relation_type: string,     // "similar_to" | "opposite_of" | "prerequisite_for"
  strength: float
}]->(:GameConcept)

// ===== 模板图谱（Template Graph）=====

(:Template {
  template_id: string,
  name: string,
  description: string,
  media_type: string,
  engine_type: string,
  tags: [string],
  usage_count: int,
  rating: float,
  price: float,              // 0 = free
  license: string,
  embedding: vector
})

(:Template)-[:COMPATIBLE_WITH]->(:Engine)

(:Template)-[:DEPENDS_ON]->(:Template)

(:Template)-[:APPLIES_TO]->(:GameConcept)
```

### 3.3 关键 Cypher 查询

```cypher
// ===== 查询 1: 获取项目的完整 CDL 图 =====
MATCH (p:Project {project_id: $project_id})-[:HAS_CDL {is_current: true}]->(cdl:CDLDocument)
MATCH (n:ContentNode {cdl_id: cdl.cdl_id})
OPTIONAL MATCH (n)-[r:RELATES_TO]->(m:ContentNode {cdl_id: cdl.cdl_id})
RETURN n, r, m;

// ===== 查询 2: 查找兼容性冲突 =====
// 给定一个 Patch，检查它是否与已安装的 Patch 冲突
MATCH (patch:CDLPatch {patch_id: $patch_id})-[:MODIFIES]->(target:ContentNode)
MATCH (other_patch:CDLPatch)-[:MODIFIES]->(target)
WHERE other_patch.patch_id <> patch.patch_id
AND other_patch.status = "applied"
RETURN target.node_id AS conflicting_node,
       patch.patch_id AS new_patch,
       other_patch.patch_id AS existing_patch;

// ===== 查询 3: 语义相似模板检索 =====
// 使用向量索引 + 图过滤
CALL db.index.vector.queryNodes('template-embedding', 10, $query_vector)
YIELD node AS template, score
MATCH (template)-[:COMPATIBLE_WITH]->(e:Engine {name: $target_engine})
WHERE template.price <= $max_price
RETURN template, score
ORDER BY score DESC;

// ===== 查询 4: 影响力分析（PageRank）=====
// 找出最受欢迎/最具影响力的 Mod
CALL gds.graph.project('project-influence', 'Project', 'FORKED_FROM')
YIELD graphName;

CALL gds.pageRank.stream('project-influence')
YIELD nodeId, score
RETURN gds.util.asNode(nodeId).project_id AS project_id,
       gds.util.asNode(nodeId).name AS name,
       score AS influence_score
ORDER BY score DESC
LIMIT 20;

// ===== 查询 5: 社区发现（Louvain）=====
// 发现用户社区/创作者圈子
CALL gds.graph.project('user-social', 'User', {
  FOLLOWS: { orientation: 'UNDIRECTED' },
  COLLABORATES_ON: { orientation: 'UNDIRECTED' }
})
YIELD graphName;

CALL gds.louvain.stream('user-social')
YIELD nodeId, communityId
RETURN communityId,
       count(*) AS community_size,
       collect(gds.util.asNode(nodeId).username)[0..5] AS sample_members
ORDER BY community_size DESC
LIMIT 10;

// ===== 查询 6: 最短路径（机制依赖链）=====
// 找出两个机制之间的依赖路径
MATCH path = shortestPath(
  (a:ContentNode {node_id: $node_a})-[:RELATES_TO*]-(b:ContentNode {node_id: $node_b})
)
RETURN [node IN nodes(path) | node.name] AS dependency_chain,
       length(path) AS hop_count;

// ===== 查询 7: 时间旅行（历史版本）=====
// 获取某个节点在特定时间点的状态
MATCH (n:ContentNode {node_id: $node_id})
MATCH (patch:CDLPatch)-[:MODIFIES]->(n)
WHERE patch.applied_at <= $timestamp
WITH n, patch
ORDER BY patch.applied_at DESC
LIMIT 1
RETURN n {
  .*,
  applied_patch: patch.patch_id,
  patch_state: patch.result_state
} AS node_at_time;
```

---

## 4. 关系数据库设计（PostgreSQL）

### 4.1 表结构

```sql
-- ===== 用户系统 =====

CREATE TABLE users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email_hash VARCHAR(64) NOT NULL,  -- SHA-256，隐私保护
    display_name VARCHAR(100),
    avatar_url TEXT,
    
    -- 声誉分数（冗余存储，便于快速查询）
    reputation_creator INT DEFAULT 0,
    reputation_curator INT DEFAULT 0,
    reputation_technical INT DEFAULT 0,
    reputation_governance INT DEFAULT 0,
    
    -- 账户状态
    account_status VARCHAR(20) DEFAULT 'active' CHECK (account_status IN ('active', 'suspended', 'banned', 'deactivated')),
    email_verified BOOLEAN DEFAULT FALSE,
    two_factor_enabled BOOLEAN DEFAULT FALSE,
    
    -- 订阅信息
    subscription_tier VARCHAR(20) DEFAULT 'free' CHECK (subscription_tier IN ('free', 'pro', 'team', 'enterprise')),
    subscription_expires_at TIMESTAMPTZ,
    
    -- 元数据
    created_at TIMESTAMPTZ DEFAULT NOW(),
    last_active_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- 搜索优化
    search_vector TSVECTOR
);

CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_reputation ON users(reputation_creator DESC);
CREATE INDEX idx_users_search ON users USING GIN(search_vector);

-- 触发器：自动更新 search_vector
CREATE OR REPLACE FUNCTION update_user_search_vector()
RETURNS TRIGGER AS $$
BEGIN
    NEW.search_vector := 
        setweight(to_tsvector('english', COALESCE(NEW.username, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.display_name, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_user_search_update
BEFORE INSERT OR UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION update_user_search_vector();

-- ===== 项目表 =====

CREATE TABLE projects (
    project_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(200) UNIQUE NOT NULL,
    description TEXT,
    
    -- 目标内容
    media_type VARCHAR(20) NOT NULL CHECK (media_type IN ('game', 'music', 'video', 'novel')),
    target_game VARCHAR(100),
    target_engine VARCHAR(50),
    target_game_version VARCHAR(50),
    
    -- 当前 CDL 引用
    current_cdl_id UUID REFERENCES cdl_documents(cdl_id),
    
    -- 可见性和状态
    visibility VARCHAR(20) DEFAULT 'public' CHECK (visibility IN ('public', 'private', 'unlisted')),
    status VARCHAR(20) DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'archived', 'under_review')),
    
    -- AI 使用声明
    ai_automation_level VARCHAR(20) CHECK (ai_automation_level IN ('none', 'assisted', 'hybrid', 'fully_automated')),
    ai_disclosure JSONB,
    
    -- 许可
    license VARCHAR(50) DEFAULT 'CC-BY-SA-4.0',
    
    -- 统计（反规范化，便于快速查询）
    view_count BIGINT DEFAULT 0,
    download_count BIGINT DEFAULT 0,
    endorsement_count INT DEFAULT 0,
    fork_count INT DEFAULT 0,
    comment_count INT DEFAULT 0,
    
    -- 评分
    rating_average DECIMAL(2,1) DEFAULT 0 CHECK (rating_average >= 0 AND rating_average <= 5),
    rating_count INT DEFAULT 0,
    
    -- 元数据
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    
    -- 全文搜索
    search_vector TSVECTOR,
    
    -- 向量嵌入（用于推荐）
    embedding VECTOR(768)
);

CREATE INDEX idx_projects_media_type ON projects(media_type);
CREATE INDEX idx_projects_engine ON projects(target_engine);
CREATE INDEX idx_projects_status ON projects(status, visibility);
CREATE INDEX idx_projects_search ON projects USING GIN(search_vector);
CREATE INDEX idx_projects_embedding ON projects USING ivfflat (embedding vector_cosine_ops);

-- ===== CDL 文档表 =====

CREATE TABLE cdl_documents (
    cdl_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id),
    version VARCHAR(50) NOT NULL,
    format_version VARCHAR(10) DEFAULT '2.0',
    
    -- 存储引用
    content_path TEXT NOT NULL,  -- S3 路径或文件路径
    size_bytes BIGINT,
    checksum VARCHAR(64),
    
    -- 统计
    node_count INT,
    edge_count INT,
    
    -- 元数据
    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    commit_message TEXT,
    
    -- 父版本（用于版本链）
    parent_cdl_id UUID REFERENCES cdl_documents(cdl_id),
    
    UNIQUE(project_id, version)
);

CREATE INDEX idx_cdl_project ON cdl_documents(project_id);
CREATE INDEX idx_cdl_parent ON cdl_documents(parent_cdl_id);

-- ===== Patch 表 =====

CREATE TABLE patches (
    patch_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(project_id),
    parent_cdl_id UUID NOT NULL REFERENCES cdl_documents(cdl_id),
    
    -- 意图
    intent_natural_language TEXT,
    intent_structured JSONB,
    
    -- 存储
    patch_path TEXT NOT NULL,
    size_bytes BIGINT,
    checksum VARCHAR(64),
    
    -- 状态
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected', 'applied', 'rolled_back', 'failed')),
    
    -- 评估结果
    evaluation_score JSONB,  -- { quality: 4.5, innovation: 3.2, ... }
    evaluation_report_path TEXT,
    
    -- 执行结果
    execution_status VARCHAR(20),
    execution_log_path TEXT,
    execution_duration_ms INT,
    
    -- 审批
    requires_human_approval BOOLEAN DEFAULT FALSE,
    approved_by UUID REFERENCES users(user_id),
    approved_at TIMESTAMPTZ,
    
    -- 风险
    risk_level VARCHAR(10) CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    
    created_by UUID REFERENCES users(user_id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    applied_at TIMESTAMPTZ,
    rolled_back_at TIMESTAMPTZ
);

CREATE INDEX idx_patches_project ON patches(project_id);
CREATE INDEX idx_patches_status ON patches(status);
CREATE INDEX idx_patches_risk ON patches(risk_level);

-- ===== 交易/支付表 =====

CREATE TABLE transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_type VARCHAR(30) NOT NULL CHECK (transaction_type IN ('subscription', 'tip', 'bounty', 'marketplace_purchase', 'payout')),
    
    -- 金额
    amount_usd DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    
    -- 参与者
    payer_id UUID REFERENCES users(user_id),
    payee_id UUID REFERENCES users(user_id),
    platform_fee DECIMAL(10,2),
    
    -- 关联对象
    project_id UUID REFERENCES projects(project_id),
    bounty_id UUID,
    
    -- 支付处理器
    processor VARCHAR(20) CHECK (processor IN ('stripe', 'paypal', 'crypto')),
    processor_transaction_id VARCHAR(255),
    
    -- 状态
    status VARCHAR(20) DEFAULT 'pending' CHECK (status IN ('pending', 'completed', 'failed', 'refunded', 'disputed')),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX idx_transactions_payer ON transactions(payer_id);
CREATE INDEX idx_transactions_payee ON transactions(payee_id);
CREATE INDEX idx_transactions_project ON transactions(project_id);
CREATE INDEX idx_transactions_created ON transactions(created_at);

-- ===== 时序事件表（TimescaleDB）=====

CREATE TABLE events (
    event_id BIGSERIAL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    
    -- 参与者
    user_id UUID REFERENCES users(user_id),
    session_id VARCHAR(100),
    
    -- 目标对象
    project_id UUID REFERENCES projects(project_id),
    patch_id UUID REFERENCES patches(patch_id),
    
    -- 事件详情
    payload JSONB,
    
    -- 客户端信息
    ip_hash VARCHAR(64),  -- 哈希化 IP
    user_agent_hash VARCHAR(64),
    
    PRIMARY KEY (event_id, event_time)
);

-- 转换为 hypertable（TimescaleDB）
SELECT create_hypertable('events', 'event_time', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX idx_events_user ON events(user_id, event_time DESC);
CREATE INDEX idx_events_project ON events(project_id, event_time DESC);
CREATE INDEX idx_events_type ON events(event_type, event_time DESC);
```

### 4.2 视图与物化视图

```sql
-- 项目统计视图（实时）
CREATE VIEW project_stats AS
SELECT 
    p.project_id,
    p.name,
    p.view_count,
    p.download_count,
    p.endorsement_count,
    p.rating_average,
    p.rating_count,
    COUNT(DISTINCT f.fork_from_id) AS fork_count,
    COUNT(DISTINCT c.comment_id) AS comment_count
FROM projects p
LEFT JOIN project_forks f ON p.project_id = f.fork_to_id
LEFT JOIN comments c ON p.project_id = c.project_id
GROUP BY p.project_id;

-- 创作者收入物化视图（每日刷新）
CREATE MATERIALIZED VIEW creator_revenue_summary AS
SELECT 
    payee_id,
    DATE_TRUNC('month', created_at) AS month,
    SUM(CASE WHEN transaction_type = 'tip' THEN amount_usd ELSE 0 END) AS tip_revenue,
    SUM(CASE WHEN transaction_type = 'subscription' THEN amount_usd ELSE 0 END) AS sub_revenue,
    SUM(CASE WHEN transaction_type = 'marketplace_purchase' THEN amount_usd ELSE 0 END) AS sales_revenue,
    SUM(amount_usd - platform_fee) AS net_revenue
FROM transactions
WHERE status = 'completed'
GROUP BY payee_id, DATE_TRUNC('month', created_at);

CREATE INDEX idx_creator_revenue ON creator_revenue_summary(payee_id, month);

-- 刷新策略（使用 pg_cron）
SELECT cron.schedule('refresh-creator-revenue', '0 2 * * *', 
    'REFRESH MATERIALIZED VIEW CONCURRENTLY creator_revenue_summary');
```

---

## 5. 向量数据库（Pinecone）

### 5.1 Index 设计

```python
# Pinecone 索引配置
from pinecone import Pinecone, ServerlessSpec

pc = Pinecone(api_key="YOUR_API_KEY")

# Index 1: 内容语义搜索
pc.create_index(
    name="udify-content-embeddings",
    dimension=768,  # text-embedding-3-large
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    metadata_config={
        "indexed": [
            "project_id",
            "media_type",
            "engine_type",
            "status",
            "license",
            "created_at"
        ]
    }
)

# Index 2: 用户偏好
pc.create_index(
    name="udify-user-preferences",
    dimension=768,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    metadata_config={
        "indexed": ["user_id", "preference_type"]
    }
)

# Index 3: 模板检索
pc.create_index(
    name="udify-template-embeddings",
    dimension=768,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    metadata_config={
        "indexed": [
            "template_id",
            "media_type",
            "engine_type",
            "tags",
            "price",
            "rating"
        ]
    }
)

# Index 4: 意图分类
pc.create_index(
    name="udify-intent-embeddings",
    dimension=768,
    metric="cosine",
    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    metadata_config={
        "indexed": ["intent_type", "media_type", "confidence"]
    }
)
```

### 5.2 混合搜索策略

```python
class HybridSearchEngine:
    """结合向量搜索 + 关键词搜索 + 图过滤"""
    
    def __init__(self):
        self.pinecone = PineconeClient()
        self.neo4j = Neo4jClient()
        self.postgres = PostgresClient()
    
    async def search_projects(
        self,
        query: str,
        filters: SearchFilters,
        user_id: Optional[str] = None,
        top_k: int = 20
    ) -> List[SearchResult]:
        """
        混合搜索算法：
        1. 向量搜索（语义相似度）
        2. 关键词搜索（PostgreSQL FTS）
        3. 图过滤（Neo4j 兼容性检查）
        4. 个性化重排（用户偏好向量）
        """
        
        # 1. 获取查询向量
        query_embedding = await self.embed(query)
        
        # 2. 向量搜索（Pinecone）
        vector_results = self.pinecone.query(
            index="udify-content-embeddings",
            vector=query_embedding,
            top_k=top_k * 3,  # 多取一些用于过滤
            filter={
                "status": {"$eq": "published"},
                "visibility": {"$eq": "public"},
                "media_type": {"$eq": filters.media_type} if filters.media_type else None,
            }
        )
        
        # 3. 关键词搜索（PostgreSQL）
        keyword_results = await self.postgres.fetch(
            """
            SELECT project_id, 
                   ts_rank_cd(search_vector, plainto_tsquery('english', $1)) AS rank
            FROM projects
            WHERE search_vector @@ plainto_tsquery('english', $1)
            AND status = 'published'
            AND visibility = 'public'
            ORDER BY rank DESC
            LIMIT $2
            """,
            query, top_k * 3
        )
        
        # 4. 合并结果（RRF - Reciprocal Rank Fusion）
        combined = self._reciprocal_rank_fusion(
            vector_results, keyword_results, k=60
        )
        
        # 5. 图过滤（Neo4j）
        # 检查兼容性、依赖关系等
        project_ids = [r.id for r in combined[:top_k * 2]]
        compatible_ids = await self.neo4j.check_compatibility(
            project_ids,
            target_game=filters.target_game,
            target_engine=filters.target_engine
        )
        
        # 6. 个性化重排（如果有用户 ID）
        if user_id:
            user_pref = await self.get_user_preference_vector(user_id)
            for result in combined:
                if result.id in compatible_ids:
                    # 计算与用户偏好的相似度
                    result.personalized_score = (
                        result.base_score * 0.7 +
                        cosine_similarity(result.embedding, user_pref) * 0.3
                    )
            combined.sort(key=lambda r: r.personalized_score, reverse=True)
        
        return combined[:top_k]
    
    def _reciprocal_rank_fusion(
        self,
        vector_results: List[VectorResult],
        keyword_results: List[KeywordResult],
        k: int = 60
    ) -> List[FusedResult]:
        """RRF 融合算法"""
        scores = {}
        
        for rank, result in enumerate(vector_results):
            doc_id = result.id
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        
        for rank, result in enumerate(keyword_results):
            doc_id = result.project_id
            scores[doc_id] = scores.get(doc_id, 0) + 1 / (k + rank + 1)
        
        # 排序
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [FusedResult(id=doc_id, base_score=score) for doc_id, score in sorted_results]
```

---

## 6. 版本控制系统（DVC + Git-like）

### 6.1 架构

```
版本控制架构
    │
    ├──→ Git（文本层）
    │       ├──→ CDL YAML 文件
    │       ├──→ Patch YAML 文件
    │       ├──→ 配置文件
    │       ├──→ 元数据文件
    │       └──→ 提交历史、分支、标签
    │
    ├──→ DVC（大文件层）
    │       ├──→ 原始游戏文件（只读）
    │       ├──→ 生成的纹理/模型（PNG, FBX）
    │       ├──→ 音频文件（WAV, OGG）
    │       ├──→ 视频文件（MP4）
    │       ├──→ 沙箱输出
    │       └──→ 快照/备份
    │
    └──→ 自定义版本协议（CDL-specific）
            ├──→ Patch 链（Patch Chain）
            ├──→ 分支策略（Branching Strategy）
            ├──→ 合并语义（Merge Semantics）
            └──→ 冲突解决（Conflict Resolution）
```

### 6.2 DVC Pipeline 定义

```yaml
# dvc.yaml
# DVC Pipeline 定义，用于追踪 CDL 生成流程

stages:
  extract:
    cmd: python -m udify perception extract --game-path ${game.path} --output cdl/raw.cdl
    deps:
      - ${game.path}
      - udify/core/perception/
    outs:
      - cdl/raw.cdl:
          cache: true
          remote: s3-cdl-storage
  
  analyze:
    cmd: python -m udify perception analyze --input cdl/raw.cdl --output cdl/analyzed.cdl
    deps:
      - cdl/raw.cdl
      - udify/core/perception/
    outs:
      - cdl/analyzed.cdl
  
  generate_patch:
    cmd: python -m udify planning generate --intent "${intent}" --input cdl/analyzed.cdl --output patches/${patch.id}.cdl.patch
    deps:
      - cdl/analyzed.cdl
      - udify/core/planning/
    params:
      - planning.strategy
      - planning.mcts.iterations
    outs:
      - patches/${patch.id}.cdl.patch
  
  evaluate:
    cmd: python -m udify evaluation run --patch patches/${patch.id}.cdl.patch --input cdl/analyzed.cdl --output evaluation/${patch.id}.json
    deps:
      - patches/${patch.id}.cdl.patch
      - cdl/analyzed.cdl
      - udify/core/evaluation/
    metrics:
      - evaluation/${patch.id}.json:
          cache: false
  
  execute:
    cmd: python -m udify execution run --patch patches/${patch.id}.cdl.patch --input cdl/analyzed.cdl --output output/
    deps:
      - patches/${patch.id}.cdl.patch
      - cdl/analyzed.cdl
      - evaluation/${patch.id}.json
    outs:
      - output/:
          cache: true
          remote: s3-execution-output
```

### 6.3 CDL 分支策略

```python
class CDLBranchManager:
    """CDL 分支管理器，类似 Git 但针对 CDL 语义优化"""
    
    def create_branch(self, project_id: str, branch_name: str, from_cdl_id: str) -> Branch:
        """创建新分支"""
        branch = Branch(
            project_id=project_id,
            name=branch_name,
            head_cdl_id=from_cdl_id,
            created_at=datetime.now()
        )
        self.db.save(branch)
        return branch
    
    def merge_branches(
        self,
        target_branch: str,
        source_branch: str,
        strategy: MergeStrategy = MergeStrategy.THREE_WAY
    ) -> MergeResult:
        """合并两个分支"""
        # 找到共同祖先
        base_cdl = self.find_common_ancestor(target_branch, source_branch)
        
        target_cdl = self.get_branch_head(target_branch)
        source_cdl = self.get_branch_head(source_branch)
        
        if strategy == MergeStrategy.THREE_WAY:
            merger = CDLMerger()
            return merger.three_way_merge(base_cdl, target_cdl, source_cdl)
        
        elif strategy == MergeStrategy.REBASE:
            # 将 source 的 patch 逐个 rebase 到 target
            patches = self.get_patches_between(base_cdl, source_cdl)
            for patch in patches:
                self.apply_patch(target_branch, patch)
            return MergeResult(success=True)
    
    def find_common_ancestor(self, branch_a: str, branch_b: str) -> CDLDocument:
        """找到两个分支的最近共同祖先"""
        # 使用 Neo4j 图遍历
        query = """
        MATCH path_a = (b_a:Branch {name: $branch_a})-[:HAS_CDL*]->(cdl:CDLDocument)
        MATCH path_b = (b_b:Branch {name: $branch_b})-[:HAS_CDL*]->(cdl)
        RETURN cdl
        ORDER BY length(path_a) + length(path_b) ASC
        LIMIT 1
        """
        return self.neo4j.run(query, branch_a=branch_a, branch_b=branch_b)
```

---

## 7. 缓存层（Redis）

### 7.1 缓存策略

| 数据类型 | TTL | 序列化 | 失效策略 |
|---------|-----|--------|---------|
| **用户会话** | 24h | JSON | 主动删除（logout） |
| **项目元数据** | 5min | JSON | 写时失效 |
| **CDL 小文件** | 1h | 二进制 | LRU |
| **搜索结果** | 10min | JSON | 时间过期 |
| **排行榜** | 1h | JSON | 定时刷新 |
| **速率限制** | 1min | String | 时间过期 |
| **分布式锁** | 30s | String | 自动过期 |
| **实时计数器** | 无 | String | 定时持久化 |

### 7.2 关键模式

```python
import redis.asyncio as redis
import json
from typing import Optional

class CacheManager:
    """Redis 缓存管理器"""
    
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url, decode_responses=True)
        self.prefix = "udify:"
    
    # ===== 项目缓存 =====
    
    async def get_project(self, project_id: str) -> Optional[dict]:
        """获取项目缓存"""
        key = f"{self.prefix}project:{project_id}"
        data = await self.redis.get(key)
        return json.loads(data) if data else None
    
    async def set_project(self, project_id: str, project: dict, ttl: int = 300):
        """缓存项目（5分钟 TTL）"""
        key = f"{self.prefix}project:{project_id}"
        await self.redis.setex(key, ttl, json.dumps(project))
    
    async def invalidate_project(self, project_id: str):
        """失效项目缓存"""
        key = f"{self.prefix}project:{project_id}"
        await self.redis.delete(key)
        # 同时失效列表缓存
        await self.redis.delete(f"{self.prefix}projects:trending")
        await self.redis.delete(f"{self.prefix}projects:recent")
    
    # ===== 速率限制 =====
    
    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window: int
    ) -> tuple[bool, int]:
        """
        滑动窗口速率限制
        
        Returns:
            (allowed, remaining)
        """
        redis_key = f"{self.prefix}ratelimit:{key}"
        pipe = self.redis.pipeline()
        
        now = time.time()
        window_start = now - window
        
        # 清理过期请求
        pipe.zremrangebyscore(redis_key, 0, window_start)
        # 获取当前窗口内请求数
        pipe.zcard(redis_key)
        # 添加当前请求
        pipe.zadd(redis_key, {str(now): now})
        # 设置 key 过期时间
        pipe.expire(redis_key, window + 1)
        
        results = await pipe.execute()
        current_count = results[1]
        
        if current_count >= limit:
            # 超限，移除刚刚添加的请求
            await self.redis.zrem(redis_key, str(now))
            return False, 0
        
        return True, limit - current_count - 1
    
    # ===== 分布式锁 =====
    
    async def acquire_lock(self, lock_name: str, timeout: int = 30) -> bool:
        """获取分布式锁（基于 Redlock 算法简化版）"""
        lock_key = f"{self.prefix}lock:{lock_name}"
        lock_value = str(uuid.uuid4())
        
        acquired = await self.redis.set(
            lock_key, lock_value, nx=True, ex=timeout
        )
        
        if acquired:
            # 存储锁值用于释放时验证
            self._lock_values[lock_name] = lock_value
        
        return acquired
    
    async def release_lock(self, lock_name: str) -> bool:
        """释放分布式锁（使用 Lua 脚本保证原子性）"""
        lock_key = f"{self.prefix}lock:{lock_name}"
        lock_value = self._lock_values.get(lock_name)
        
        if not lock_value:
            return False
        
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        result = await self.redis.eval(lua_script, 1, lock_key, lock_value)
        del self._lock_values[lock_name]
        return result == 1
    
    # ===== 实时排行榜 =====
    
    async def update_leaderboard(self, board: str, member: str, score: float):
        """更新排行榜"""
        key = f"{self.prefix}leaderboard:{board}"
        await self.redis.zadd(key, {member: score})
    
    async def get_leaderboard(self, board: str, top_k: int = 100) -> list:
        """获取排行榜"""
        key = f"{self.prefix}leaderboard:{board}"
        results = await self.redis.zrevrange(key, 0, top_k - 1, withscores=True)
        return [{"member": m, "score": s} for m, s in results]
    
    # ===== 缓存预热 =====
    
    async def warm_cache(self):
        """缓存预热：系统启动时加载热点数据"""
        # 加载 trending projects
        trending = await self.postgres.fetch(
            "SELECT * FROM projects WHERE status = 'published' ORDER BY view_count DESC LIMIT 100"
        )
        for project in trending:
            await self.set_project(project["project_id"], project, ttl=3600)
        
        # 加载热门模板
        # ...
```

---

## 8. 对象存储（S3-compatible）

### 8.1 Bucket 设计

```yaml
# S3 Bucket 结构

buckets:
  udify-raw-games:
    description: "原始游戏文件（只读镜像）"
    lifecycle:
      - rule: "delete_after_90_days"
        condition: "object older than 90 days AND not accessed"
    cors: false
    public: false
    
  udify-cdl-documents:
    description: "CDL 文档（YAML 文件）"
    lifecycle:
      - rule: "transition_to_glacier"
        condition: "object older than 1 year"
    versioning: enabled
    
  udify-assets:
    description: "生成的资源文件（纹理、模型、音频）"
    structure:
      - "{project_id}/{version}/textures/{filename}"
      - "{project_id}/{version}/models/{filename}"
      - "{project_id}/{version}/audio/{filename}"
    cdn: true
    cache_control: "max-age=86400"
    
  udify-patches:
    description: "Patch 文件"
    structure:
      - "{project_id}/{patch_id}.cdl.patch"
    versioning: enabled
    
  udify-execution-outputs:
    description: "沙箱执行输出"
    lifecycle:
      - rule: "delete_after_30_days"
        condition: "all objects"
    
  udify-snapshots:
    description: "游戏状态快照（用于回滚）"
    structure:
      - "{project_id}/snapshots/{snapshot_id}.zip"
    lifecycle:
      - rule: "delete_after_7_days"
        condition: "snapshot older than 7 days AND not referenced by active patch"
    
  udify-user-uploads:
    description: "用户上传的文件"
    structure:
      - "{user_id}/uploads/{filename}"
    quota: "1GB per user"
    
  udify-public-templates:
    description: "公开模板资源"
    public: true
    cdn: true
```

### 8.2 访问控制

```python
class ObjectStorageACL:
    """对象存储访问控制"""
    
    def __init__(self):
        self.policies = {
            # 公开读取（模板、已发布项目资源）
            "public-read": {
                "Effect": "Allow",
                "Principal": "*",
                "Action": ["s3:GetObject"],
                "Resource": "arn:aws:s3:::udify-public-templates/*"
            },
            
            # 项目成员读写
            "project-member": {
                "Effect": "Allow",
                "Principal": {"AWS": "arn:aws:iam::${account}:user/${user_id}"},
                "Action": ["s3:GetObject", "s3:PutObject"],
                "Resource": "arn:aws:s3:::udify-assets/${project_id}/*",
                "Condition": {
                    "StringEquals": {
                        "s3:x-amz-acl": "project-member"
                    }
                }
            },
            
            # 系统内部服务
            "system-service": {
                "Effect": "Allow",
                "Principal": {"AWS": "arn:aws:iam::${account}:role/udify-execution-service"},
                "Action": ["s3:*"],
                "Resource": [
                    "arn:aws:s3:::udify-execution-outputs/*",
                    "arn:aws:s3:::udify-snapshots/*",
                    "arn:aws:s3:::udify-raw-games/*"
                ]
            }
        }
```

---

## 9. 数据流与一致性

### 9.1 端到端数据流

```
用户请求: "让游戏像魂系那样"
    │
    ▼
[API Gateway]
    │
    ├──→ 写入: Redis Session（TTL: 24h）
    │
    ▼
[Intent Service]
    │
    ├──→ 读取: Pinecone 意图向量索引
    ├──→ 写入: PostgreSQL events 表
    └──→ 写入: Redis 缓存（intent_result, TTL: 5min）
    │
    ▼
[Perception Service]
    │
    ├──→ 读取: S3 原始游戏文件
    ├──→ 写入: Neo4j 内容图
    ├──→ 写入: S3 CDL 文档
    ├──→ 写入: PostgreSQL cdl_documents 表
    └──→ 写入: PostgreSQL events 表
    │
    ▼
[Planning Service]
    │
    ├──→ 读取: Neo4j 内容图
    ├──→ 读取: Pinecone 模板索引
    ├──→ 写入: S3 Patch 文件
    ├──→ 写入: PostgreSQL patches 表
    └──→ 写入: PostgreSQL events 表
    │
    ▼
[Evaluation Service]
    │
    ├──→ 读取: S3 Patch 文件
    ├──→ 读取: S3 CDL 文档
    ├──→ 写入: PostgreSQL patches.evaluation_score
    └──→ 写入: PostgreSQL events 表
    │
    ▼
[Execution Service]
    │
    ├──→ 读取: S3 Patch 文件
    ├──→ 读取: S3 CDL 文档
    ├──→ 写入: S3 执行输出
    ├──→ 写入: PostgreSQL patches.execution_status
    ├──→ 写入: Neo4j 新内容节点/边
    └──→ 写入: PostgreSQL events 表
    │
    ▼
[Platform Service]
    │
    ├──→ 读取: PostgreSQL projects 表
    ├──→ 写入: PostgreSQL projects（更新统计）
    ├──→ 写入: Redis 缓存（失效旧缓存）
    ├──→ 写入: Pinecone 内容向量索引
    └──→ 发布: Event Bus（通知其他服务）
```

### 9.2 一致性模型

| 数据类型 | 一致性要求 | 策略 |
|---------|-----------|------|
| **用户账户** | 强一致 | PostgreSQL ACID |
| **交易/支付** | 强一致 | PostgreSQL + 分布式事务（Saga） |
| **项目元数据** | 最终一致 | PostgreSQL + Redis 缓存（写时失效） |
| **CDL 内容** | 强一致 | Git + DVC（不可变） |
| **Patch 状态** | 强一致 | PostgreSQL + 状态机 |
| **图关系** | 最终一致 | Neo4j + 异步同步 |
| **搜索索引** | 最终一致 | Pinecone + 异步更新 |
| **排行榜** | 弱一致 | Redis + 定时批量更新 |
| **事件日志** | 最终一致 | TimescaleDB + 异步写入 |

### 9.3 Saga 模式（分布式事务）

```python
class CreateProjectSaga:
    """创建项目的 Saga 分布式事务"""
    
    def __init__(self):
        self.steps = [
            self.create_postgres_record,
            self.create_neo4j_nodes,
            self.init_git_repo,
            self.init_dvc_repo,
            self.create_s3_folder,
            self.send_welcome_notification,
        ]
        self.compensations = [
            self.delete_postgres_record,
            self.delete_neo4j_nodes,
            self.delete_git_repo,
            self.delete_dvc_repo,
            self.delete_s3_folder,
            None,  # 通知不需要补偿
        ]
    
    async def execute(self, project_data: dict) -> SagaResult:
        completed = []
        
        try:
            for i, step in enumerate(self.steps):
                result = await step(project_data)
                completed.append(i)
                
                if not result.success:
                    raise SagaStepFailed(step.__name__, result.error)
            
            return SagaResult(success=True, project_id=project_data["project_id"])
            
        except SagaStepFailed as e:
            # 执行补偿
            for i in reversed(completed):
                if self.compensations[i]:
                    try:
                        await self.compensations[i](project_data)
                    except Exception as comp_error:
                        # 补偿失败，需要人工介入
                        await self.alert_ops(
                            f"Saga compensation failed for project {project_data['project_id']}",
                            comp_error
                        )
            
            return SagaResult(success=False, error=e.error)
```

---

## 10. 多租户数据隔离

### 10.1 隔离策略

```
多租户架构
    │
    ├──→ 方案 A: 数据库级隔离（最高安全性，最高成本）
    │       ├──→ 每个租户独立 PostgreSQL 数据库
    │       ├──→ 每个租户独立 Neo4j 数据库
    │       ├──→ 每个租户独立 S3 Bucket
    │       └──→ 适用: Enterprise 客户
    │
    ├──→ 方案 B: Schema 级隔离（平衡）
    │       ├──→ 共享数据库，独立 Schema
    │       ├──→ 共享 Neo4j，租户标签过滤
    │       ├──→ 共享 S3 Bucket，租户前缀隔离
    │       └──→ 适用: Team 客户
    │
    └──→ 方案 C: 行级隔离（最高效率，最低成本）
            ├──→ 共享表，tenant_id 列过滤
            ├──→ 共享 Neo4j，节点属性过滤
            ├──→ 共享 S3 Bucket，前缀隔离
            └──→ 适用: Free / Pro 用户
```

### 10.2 实现

```python
class TenantContext:
    """租户上下文管理器"""
    
    def __init__(self, tenant_id: str, tier: str):
        self.tenant_id = tenant_id
        self.tier = tier
        self.isolation = self._get_isolation_level(tier)
    
    def _get_isolation_level(self, tier: str) -> IsolationLevel:
        if tier == "enterprise":
            return IsolationLevel.DATABASE
        elif tier == "team":
            return IsolationLevel.SCHEMA
        else:
            return IsolationLevel.ROW

class TenantAwareQueryBuilder:
    """租户感知的查询构建器"""
    
    def __init__(self, tenant: TenantContext):
        self.tenant = tenant
    
    def apply_tenant_filter(self, query: str, params: dict) -> tuple[str, dict]:
        """自动添加租户过滤条件"""
        if self.tenant.isolation == IsolationLevel.ROW:
            # PostgreSQL: 添加 tenant_id 过滤
            if "WHERE" in query:
                query = query.replace("WHERE", f"WHERE tenant_id = '{self.tenant.tenant_id}' AND")
            else:
                query += f" WHERE tenant_id = '{self.tenant.tenant_id}'"
            
            # Neo4j: 添加租户属性过滤
            if query.startswith("MATCH"):
                query = query.replace(
                    "(n:",
                    f"(n:{{tenant_id: '{self.tenant.tenant_id}'}}"
                )
        
        elif self.tenant.isolation == IsolationLevel.SCHEMA:
            # 替换 schema 名
            query = query.replace("public.", f"{self.tenant.tenant_id}.")
        
        elif self.tenant.isolation == IsolationLevel.DATABASE:
            # 使用连接路由
            pass  # 在连接层处理
        
        return query, params

# 中间件自动注入租户上下文
class TenantMiddleware:
    async def process_request(self, request):
        tenant_id = request.headers.get("X-Tenant-ID")
        user = request.state.user
        
        # 验证用户是否属于该租户
        if user.tenant_id != tenant_id:
            raise Forbidden("User does not belong to this tenant")
        
        request.state.tenant = TenantContext(
            tenant_id=tenant_id,
            tier=user.subscription_tier
        )
```

### 10.3 资源配额

```yaml
# 租户资源配额
tenant_quotas:
  free:
    max_projects: 3
    max_storage_gb: 1
    max_compute_minutes_per_month: 60
    max_team_members: 1
    max_api_calls_per_day: 100
    
  pro:
    max_projects: 20
    max_storage_gb: 10
    max_compute_minutes_per_month: 600
    max_team_members: 1
    max_api_calls_per_day: 10000
    
  team:
    max_projects: 100
    max_storage_gb: 100
    max_compute_minutes_per_month: 5000
    max_team_members: 10
    max_api_calls_per_day: 100000
    
  enterprise:
    max_projects: unlimited
    max_storage_gb: unlimited
    max_compute_minutes_per_month: unlimited
    max_team_members: unlimited
    max_api_calls_per_day: unlimited
    dedicated_resources: true
    sla: "99.99%"
```

---

> **"数据架构是系统的骨骼。CDL 作为统一语言贯穿所有存储层，图数据库捕捉关系，关系数据库保障事务，向量数据库赋能语义，对象存储承载内容，缓存加速热点，版本控制保证可追溯。多租户设计让 Udify 从个人工具成长为平台。"**
>
> —— Udify 数据架构原则
