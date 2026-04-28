# Udify 性能架构与容量规划

> **版本**: v1.0 | **日期**: 2026-04-27
>
> **范围**: 负载模型、水平扩展、CQRS、读写分离、缓存策略、CDN、容量规划、成本优化

---

## 目录

1. [性能架构总览](#1-性能架构总览)
2. [负载模型与流量预测](#2-负载模型与流量预测)
3. [水平扩展架构](#3-水平扩展架构)
4. [CQRS 与读写分离](#4-cqrs-与读写分离)
5. [缓存策略矩阵](#5-缓存策略矩阵)
6. [CDN 与边缘计算](#6-cdn-与边缘计算)
7. [数据库性能优化](#7-数据库性能优化)
8. [容量规划模型](#8-容量规划模型)
9. [成本优化策略](#9-成本优化策略)

---

## 1. 性能架构总览

### 1.1 性能目标（SLO）

| 指标 | 目标 | 测量方式 |
|------|------|---------|
| **API 延迟 P99** | < 500ms | 从网关到响应 |
| **意图处理 P95** | < 30s | 从提交到计划生成 |
| **Patch 执行 P95** | < 60s | 从批准到完成 |
| **LLM 调用 P99** | < 10s | 从请求到响应 |
| **前端首屏** | < 2s | LCP (Largest Contentful Paint) |
| **前端交互响应** | < 100ms | 点击到视觉反馈 |
| **并发用户** | 10,000+ | 同时在线 |
| **每日请求** | 1,000,000+ | 总量 |
| **可用性** | 99.9% | 年度停机 < 8.76h |

### 1.2 性能分层

```
性能优化层次
    │
    ├──→ 客户端层（Browser）
    │       ├──→ 代码分割 / 懒加载
    │       ├──→ Service Worker 缓存
    │       ├──→ 图片优化（WebP/AVIF）
    │       ├──→ 虚拟列表
    │       └──→ WASM 本地计算
    │
    ├──→ Edge 层（CDN / Edge Functions）
    │       ├──→ 静态资源缓存
    │       ├──→ API 响应缓存
    │       ├──→ 边缘渲染（SSR）
    │       └──→ DDoS 防护
    │
    ├──→ 网关层（API Gateway）
    │       ├──→ 请求合并
    │       ├──→ 速率限制
    │       ├──→ 负载均衡
    │       └──→ 连接池
    │
    ├──→ 服务层（Microservices）
    │       ├──→ 水平自动扩展（HPA）
    │       ├──→ 异步处理（消息队列）
    │       ├──→ 数据库连接池
    │       └──→ 缓存（Redis）
    │
    ├──→ 数据层（Storage）
    │       ├──→ 读写分离
    │       ├──→ 分片 / 分区
    │       ├──→ 索引优化
    │       └──→ 物化视图
    │
    └──→ AI 层（LLM / Compute）
            ├──→ 请求批处理
            ├──→ 模型缓存
            ├──→ 并发控制
            └──→ 降级策略
```

---

## 2. 负载模型与流量预测

### 2.1 流量模式分析

```
Udify 流量特征
    │
    ├──→ 用户行为模式
    │       ├──→ 浏览/发现: 80% 读操作，高频，可缓存
    │       ├──→ 创建项目: 5% 写操作，低频，计算密集
    │       ├──→ 执行改造: 10% 混合操作，异步，长耗时
    │       └──→ 社区互动: 5% 写操作，中频，实时性要求低
    │
    ├──→ 时间分布
    │       ├──→ 日峰值: 20:00-23:00（用户下班后）
    │       ├──→ 周末峰值: 周六下午
    │       ├──→ 节假日: 2-3x 流量（游戏时间增加）
    │       └──→ 大版本发布: 5-10x 突发流量
    │
    └──→ 请求大小分布
            ├──→ API 请求: 平均 2KB，P99 50KB
            ├──→ 资源上传: 平均 5MB，P99 100MB
            └──→ 下载: 平均 20MB，P99 500MB
```

### 2.2 容量模型

```python
# 容量规划计算器

class CapacityModel:
    """Udify 容量规划模型"""
    
    def __init__(self):
        # 基础参数
        self.dau = 10_000           # 日活跃用户
        self.avg_session_min = 30   # 平均会话时长
        self.requests_per_session = 50  # 每会话请求数
        
        # 峰值系数
        self.peak_multiplier = 3    # 峰值是平均的 3 倍
        self.headroom = 1.5         # 50% 冗余
    
    def calculate_qps(self) -> dict:
        """计算所需 QPS"""
        daily_requests = self.dau * self.requests_per_session
        avg_qps = daily_requests / (24 * 3600)
        peak_qps = avg_qps * self.peak_multiplier * self.headroom
        
        return {
            "daily_requests": daily_requests,
            "avg_qps": round(avg_qps, 2),
            "peak_qps": round(peak_qps, 2),
        }
    
    def calculate_compute(self) -> dict:
        """计算所需计算资源"""
        
        # 假设每请求需要 100ms CPU 时间
        qps = self.calculate_qps()["peak_qps"]
        cpu_cores_needed = qps * 0.1  # 100ms = 0.1 core-seconds per request
        
        # 沙箱执行：峰值 100 并发沙箱，每个 2 CPU
        sandbox_cpu = 100 * 2
        
        # LLM 调用：峰值 50 并发，不占用本地 CPU（调用外部 API）
        
        return {
            "api_service_cores": round(cpu_cores_needed * 2),  # 2x for redundancy
            "sandbox_cores": sandbox_cpu,
            "total_cores": round(cpu_cores_needed * 2 + sandbox_cpu),
        }
    
    def calculate_storage(self) -> dict:
        """计算存储需求"""
        
        # 项目数据
        projects_per_user = 3
        avg_project_size_mb = 50  # 包含 CDL + 资源引用
        total_project_storage_gb = (self.dau * projects_per_user * avg_project_size_mb) / 1024
        
        # 用户上传
        avg_upload_per_user_mb = 100
        total_upload_storage_gb = (self.dau * avg_upload_per_user_mb) / 1024
        
        # 沙箱输出（临时）
        sandbox_output_gb = 500  # 定期清理
        
        # 增长预留（年增长 300%）
        growth_factor = 3
        
        return {
            "project_storage_gb": round(total_project_storage_gb * growth_factor),
            "user_uploads_gb": round(total_upload_storage_gb * growth_factor),
            "sandbox_temp_gb": sandbox_output_gb,
            "total_storage_gb": round((total_project_storage_gb + total_upload_storage_gb) * growth_factor + sandbox_output_gb),
        }
    
    def calculate_llm_cost(self) -> dict:
        """计算 LLM API 成本"""
        
        # 假设每个活跃用户每天生成 2 个 Patch
        patches_per_user = 2
        total_patches = self.dau * patches_per_user
        
        # 每个 Patch 平均消耗 50K tokens（输入+输出）
        tokens_per_patch = 50_000
        total_tokens = total_patches * tokens_per_patch
        
        # 混合模型使用：70% GPT-4o, 30% Claude 3.5 Sonnet
        gpt4o_tokens = total_tokens * 0.7
        claude_tokens = total_tokens * 0.3
        
        # 价格（每 1M tokens）
        gpt4o_price_per_1m = 5.0  # 平均输入+输出
        claude_price_per_1m = 3.0
        
        daily_cost = (gpt4o_tokens / 1_000_000 * gpt4o_price_per_1m +
                      claude_tokens / 1_000_000 * claude_price_per_1m)
        
        return {
            "daily_patches": total_patches,
            "daily_tokens": total_tokens,
            "daily_cost_usd": round(daily_cost, 2),
            "monthly_cost_usd": round(daily_cost * 30, 2),
            "annual_cost_usd": round(daily_cost * 365, 2),
        }
```

### 2.3 峰值容量估算

| 指标 | Year 1 (10K DAU) | Year 2 (100K DAU) | Year 3 (1M DAU) |
|------|------------------|-------------------|-----------------|
| **峰值 QPS** | 30 | 300 | 3,000 |
| **API Pod 数** | 6 | 20 | 100 |
| **沙箱并发** | 20 | 100 | 500 |
| **数据库连接** | 50 | 200 | 1,000 |
| **存储 (TB)** | 1 | 10 | 100 |
| **LLM 日消费** | $500 | $5,000 | $50,000 |
| **CDN 带宽** | 100 Mbps | 1 Gbps | 10 Gbps |

---

## 3. 水平扩展架构

### 3.1 Kubernetes 自动扩展

```yaml
# k8s/hpa.yml

# API 服务 HPA
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: udify-api-hpa
  namespace: udify
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: udify-api
  minReplicas: 3
  maxReplicas: 100
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 70
    - type: Pods
      pods:
        metric:
          name: http_requests_per_second
        target:
          type: AverageValue
          averageValue: "50"
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Percent
          value: 100
          periodSeconds: 30
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Percent
          value: 10
          periodSeconds: 60

---

# 沙箱执行器 HPA（基于队列深度）
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: udify-sandbox-hpa
  namespace: udify
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: udify-sandbox-executor
  minReplicas: 5
  maxReplicas: 500
  metrics:
    - type: External
      external:
        metric:
          name: redis_queue_depth
          selector:
            matchLabels:
              queue: execution
        target:
          type: AverageValue
          averageValue: "10"  # 每 Pod 处理 10 个排队任务

---

# LLM 代理 HPA（基于并发请求）
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: udify-llm-agent-hpa
  namespace: udify
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: udify-llm-agent
  minReplicas: 3
  maxReplicas: 50
  metrics:
    - type: Pods
      pods:
        metric:
          name: llm_active_requests
        target:
          type: AverageValue
          averageValue: "5"  # 每 Pod 5 个并发 LLM 请求
```

### 3.2 消息队列（Redis Streams / Kafka）

```python
# udify/infrastructure/queue.py

from redis.asyncio import Redis
import json

class TaskQueue:
    """基于 Redis Streams 的任务队列"""
    
    def __init__(self, redis: Redis, stream_name: str):
        self.redis = redis
        self.stream_name = stream_name
        self.consumer_group = f"{stream_name}-workers"
    
    async def enqueue(self, task: Task) -> str:
        """入队"""
        task_id = f"{self.stream_name}:{uuid.uuid4()}"
        
        await self.redis.xadd(
            self.stream_name,
            {
                "task_id": task_id,
                "type": task.type,
                "payload": json.dumps(task.payload),
                "priority": task.priority,
                "created_at": datetime.utcnow().isoformat(),
            },
            maxlen=100_000,  # 限制流长度
        )
        
        return task_id
    
    async def dequeue(self, worker_id: str, block_ms: int = 5000) -> Optional[Task]:
        """出队（阻塞）"""
        
        # 创建消费者组（如果不存在）
        try:
            await self.redis.xgroup_create(self.stream_name, self.consumer_group, id="0", mkstream=True)
        except ResponseError:
            pass  # 已存在
        
        # 读取消息
        messages = await self.redis.xreadgroup(
            groupname=self.consumer_group,
            consumername=worker_id,
            streams={self.stream_name: ">"},
            count=1,
            block=block_ms,
        )
        
        if not messages:
            return None
        
        stream_name, entries = messages[0]
        message_id, fields = entries[0]
        
        return Task(
            id=fields[b"task_id"].decode(),
            type=fields[b"type"].decode(),
            payload=json.loads(fields[b"payload"]),
            message_id=message_id,
        )
    
    async def ack(self, message_id: str):
        """确认完成"""
        await self.redis.xack(self.stream_name, self.consumer_group, message_id)
    
    async def get_queue_depth(self) -> int:
        """获取队列深度"""
        info = await self.redis.xinfo_stream(self.stream_name)
        return info.get("length", 0)
    
    async def get_pending_count(self) -> int:
        """获取处理中任务数"""
        pending = await self.redis.xpending(
            self.stream_name, self.consumer_group
        )
        return pending["pending"]
```

### 3.3 背压控制

```python
class BackpressureController:
    """背压控制器"""
    
    def __init__(self):
        self.thresholds = {
            "green": 0.5,   # 正常，正常速率处理
            "yellow": 0.7,  # 警告，降低 LLM 并发
            "red": 0.9,     # 危险，暂停新请求，只处理队列
        }
    
    async def check_and_apply(self, queue_depth: int, max_queue: int):
        """检查负载并应用背压"""
        
        ratio = queue_depth / max_queue
        
        if ratio < self.thresholds["green"]:
            # 绿色：正常处理
            await self.set_rate_limit("api", requests_per_second=1000)
            await self.set_llm_concurrency(max_concurrent=50)
            
        elif ratio < self.thresholds["yellow"]:
            # 黄色：降低 LLM 并发，减少新请求
            await self.set_rate_limit("api", requests_per_second=500)
            await self.set_llm_concurrency(max_concurrent=20)
            logger.warning(f"Backpressure YELLOW: queue at {ratio:.0%}")
            
        elif ratio < self.thresholds["red"]:
            # 红色：暂停新请求
            await self.set_rate_limit("api", requests_per_second=100)
            await self.set_llm_concurrency(max_concurrent=5)
            await self.enable_queue_only_mode()
            logger.error(f"Backpressure RED: queue at {ratio:.0%}")
            
        else:
            # 超过红色：拒绝服务
            await self.set_rate_limit("api", requests_per_second=0)
            await self.enable_maintenance_mode()
            logger.critical(f"Backpressure CRITICAL: queue full!")
```

---

## 4. CQRS 与读写分离

### 4.1 架构设计

```
CQRS 架构
    │
    ├──→ 写路径（Command Side）
    │       ├──→ API Gateway
    │       ├──→ Command Handlers
    │       ├──→ PostgreSQL（主库）
    │       ├──→ Neo4j（主图）
    │       └──→ Event Bus（发布变更事件）
    │
    └──→ 读路径（Query Side）
            ├──→ API Gateway
            ├──→ Query Handlers
            ├──→ Read Replicas（PostgreSQL）
            ├───> Materialized Views
            ├──→ Redis Cache
            ├──→ Pinecone（向量搜索）
            └──→ CDN（静态内容）
    
    数据流:
    写操作 → 主库 → 变更事件 → 消费者 → 读副本/缓存/索引更新
```

### 4.2 事件驱动的数据同步

```python
# udify/infrastructure/event_sync.py

class ChangeDataCapture:
    """变更数据捕获（CDC）"""
    
    def __init__(self):
        self.pg_listener = PostgreSQLListener()
        self.event_bus = EventBus()
    
    async def start_listening(self):
        """监听 PostgreSQL 变更"""
        
        # 使用 PostgreSQL NOTIFY / LISTEN
        await self.pg_listener.listen("project_changes")
        
        async for notification in self.pg_listener:
            event = json.loads(notification.payload)
            
            # 发布到事件总线
            await self.event_bus.publish(event["type"], event["data"])
    
    async def handle_project_created(self, event: dict):
        """处理项目创建事件"""
        project_id = event["project_id"]
        
        # 1. 更新读副本
        await self.update_read_replica(project_id)
        
        # 2. 更新搜索索引
        await self.index_for_search(project_id)
        
        # 3. 更新缓存
        await self.invalidate_cache(f"project:{project_id}")
        
        # 4. 更新向量索引（用于推荐）
        await self.update_vector_index(project_id)
    
    async def handle_project_updated(self, event: dict):
        """处理项目更新事件"""
        project_id = event["project_id"]
        changes = event["changes"]
        
        # 增量更新
        if "endorsement_count" in changes or "rating" in changes:
            # 只更新排行榜缓存
            await self.update_leaderboard_cache()
        
        if "status" in changes and changes["status"]["new"] == "published":
            # 首次发布：全量索引
            await self.index_for_search(project_id)
            await self.update_vector_index(project_id)
```

### 4.3 读模型优化

```sql
-- 物化视图：项目统计（实时性要求低）
CREATE MATERIALIZED VIEW mv_project_stats AS
SELECT 
    p.project_id,
    p.name,
    p.view_count,
    p.download_count,
    p.endorsement_count,
    p.rating_average,
    COUNT(DISTINCT f.fork_from_id) AS fork_count,
    COUNT(DISTINCT c.comment_id) AS comment_count,
    COUNT(DISTINCT t.tag_id) AS tag_count
FROM projects p
LEFT JOIN project_forks f ON p.project_id = f.fork_to_id
LEFT JOIN comments c ON p.project_id = c.project_id
LEFT JOIN project_tags t ON p.project_id = t.project_id
GROUP BY p.project_id;

CREATE UNIQUE INDEX idx_mv_project_stats_id ON mv_project_stats(project_id);

-- 5 分钟刷新一次
SELECT cron.schedule('refresh-project-stats', '*/5 * * * *', 
    'REFRESH MATERIALIZED VIEW CONCURRENTLY mv_project_stats');

-- 预计算搜索表（全文搜索优化）
CREATE TABLE project_search_index AS
SELECT 
    project_id,
    name,
    description,
    setweight(to_tsvector('english', COALESCE(name, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(description, '')), 'B') ||
    setweight(to_tsvector('english', COALESCE(array_to_string(tags, ' '), '')), 'C')
    AS search_vector
FROM projects
WHERE status = 'published';

CREATE INDEX idx_project_search ON project_search_index USING GIN(search_vector);
```

---

## 5. 缓存策略矩阵

| 数据 | 缓存层 | TTL | 失效策略 | 命中率目标 |
|------|--------|-----|---------|-----------|
| **用户会话** | Redis | 24h | 主动删除（登出） | 99% |
| **项目元数据** | Redis | 5min | 写时失效 + 定时 | 90% |
| **项目列表（Trending）** | Redis | 1h | 定时刷新 | 95% |
| **搜索结果** | Redis | 10min | 时间过期 | 80% |
| **用户偏好向量** | Redis | 1h | 更新时失效 | 95% |
| **模板列表** | Redis + CDN | 1h | 版本变更时 | 98% |
| **静态资源（JS/CSS）** | CDN | 1y | 文件名哈希变更 | 99% |
| **生成的纹理预览** | CDN | 24h | 重新生成时 | 95% |
| **CDL 文档** | Redis | 10min | 版本更新时 | 85% |
| **图查询结果** | Redis | 5min | 图变更时 | 70% |

### 5.1 缓存穿透/击穿/雪崩防护

```python
class CacheProtection:
    """缓存问题防护"""
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def get_with_bloom_filter(
        self,
        key: str,
        fetch_func: callable,
        ttl: int = 300
    ):
        """
        使用布隆过滤器防止缓存穿透
        
        流程：
        1. 检查布隆过滤器（如果肯定不存在，直接返回 None）
        2. 检查缓存
        3. 如果缓存未命中，加分布式锁
        4. 只有一个请求去数据库查询
        5. 结果写入缓存
        """
        
        # 1. 布隆过滤器检查
        if not await self.bloom_filter.might_exist(key):
            return None
        
        # 2. 检查缓存
        cached = await self.redis.get(key)
        if cached:
            return json.loads(cached)
        
        # 3. 获取分布式锁（防止缓存击穿）
        lock_key = f"lock:{key}"
        lock_acquired = await self.redis.set(
            lock_key, "1", nx=True, ex=10
        )
        
        if not lock_acquired:
            # 其他请求正在加载，等待后重试
            await asyncio.sleep(0.1)
            return await self.get_with_bloom_filter(key, fetch_func, ttl)
        
        try:
            # 4. 双重检查（获取锁后再次检查缓存）
            cached = await self.redis.get(key)
            if cached:
                return json.loads(cached)
            
            # 5. 查询数据源
            data = await fetch_func()
            
            # 6. 写入缓存（即使 data 为 None，也缓存空值防止穿透）
            if data is not None:
                await self.redis.setex(key, ttl, json.dumps(data))
            else:
                # 缓存空值，短 TTL
                await self.redis.setex(key, 60, "__NULL__")
            
            return data
            
        finally:
            await self.redis.delete(lock_key)
    
    async def staggered_ttl(self, key_prefix: str, base_ttl: int, jitter_percent: float = 0.2):
        """
        随机 TTL，防止缓存雪崩
        
        例如：base_ttl=300s, jitter=20%
        实际 TTL 会在 240s-360s 之间随机分布
        """
        jitter = base_ttl * jitter_percent
        actual_ttl = base_ttl + random.uniform(-jitter, jitter)
        return int(actual_ttl)
```

---

## 6. CDN 与边缘计算

### 6.1 CDN 架构

```
全球 CDN 分布
    │
    ├──→ 北美
    │       ├──→ 美国西部（洛杉矶）
    │       ├──→ 美国东部（纽约）
    │       └──→ 加拿大（多伦多）
    │
    ├──→ 欧洲
    │       ├──→ 西欧（法兰克福）
    │       ├──→ 英国（伦敦）
    │       └──→ 北欧（斯德哥尔摩）
    │
    ├──→ 亚太
    │       ├──→ 东亚（东京）
    │       ├──→ 东南亚（新加坡）
    │       ├──→ 大洋洲（悉尼）
    │       └──→ 中国（香港/通过合作伙伴）
    │
    └──→ 边缘功能
            ├──→ 静态资源缓存（JS/CSS/图片）
            ├──→ 视频流分发
            ├──→ API 响应缓存（Edge Cache）
            └──→ 边缘渲染（Edge SSR）
```

### 6.2 Edge 函数

```typescript
// edge-functions/api-cache.ts

export default async function handler(request: Request) {
  const url = new URL(request.url);
  const cacheKey = `api:${url.pathname}:${url.search}`;
  
  // 1. 检查 Edge Cache
  const cached = await caches.default.match(request);
  if (cached) {
    return cached;
  }
  
  // 2. 调用源站
  const response = await fetch(request);
  
  // 3. 判断是否可以缓存
  if (shouldCache(response)) {
    // 克隆响应（因为 Response 只能读取一次）
    const cloned = response.clone();
    
    // 设置缓存头
    const headers = new Headers(cloned.headers);
    headers.set('Cache-Control', 'public, max-age=300');
    headers.set('CDN-Cache-Control', 'max-age=600');
    
    // 写入 Edge Cache
    const cacheableResponse = new Response(cloned.body, {
      status: cloned.status,
      statusText: cloned.statusText,
      headers,
    });
    
    await caches.default.put(request, cacheableResponse);
  }
  
  return response;
}

function shouldCache(response: Response): boolean {
  // 只缓存成功的 GET 请求
  if (request.method !== 'GET') return false;
  if (response.status !== 200) return false;
  
  // 不缓存包含用户特定数据的响应
  const vary = response.headers.get('Vary');
  if (vary?.includes('Cookie')) return false;
  
  return true;
}
```

---

## 7. 数据库性能优化

### 7.1 PostgreSQL 优化

```sql
-- 连接池配置（PgBouncer）
-- pgbouncer.ini
[databases]
udify = host=postgres-primary port=5432 dbname=udify

[pgbouncer]
pool_mode = transaction       -- 事务级连接池
max_client_conn = 10000
default_pool_size = 50
min_pool_size = 10
reserve_pool_size = 10
reserve_pool_timeout = 3
max_db_connections = 100
server_idle_timeout = 600
server_lifetime = 3600

-- PostgreSQL 配置优化
-- postgresql.conf
shared_buffers = 4GB                    -- 25% of RAM
effective_cache_size = 12GB             -- 75% of RAM
work_mem = 256MB                        -- 用于排序和哈希
maintenance_work_mem = 1GB              -- 用于 VACUUM/索引构建
wal_buffers = 64MB
random_page_cost = 1.1                  -- SSD 优化
effective_io_concurrency = 200          -- SSD 优化
max_connections = 500                   -- 连接池前不需要太高

-- 分区表：事件日志（按月分区）
CREATE TABLE events (
    event_id BIGSERIAL,
    event_time TIMESTAMPTZ NOT NULL,
    event_type VARCHAR(50) NOT NULL,
    user_id UUID,
    payload JSONB,
    PRIMARY KEY (event_id, event_time)
) PARTITION BY RANGE (event_time);

-- 创建未来 12 个月的分区
SELECT create_monthly_partitions('events', 12);

-- 自动分区管理函数
CREATE OR REPLACE FUNCTION create_monthly_partitions(
    table_name TEXT,
    months_ahead INT
) RETURNS VOID AS $$
DECLARE
    start_date DATE;
    end_date DATE;
    partition_name TEXT;
BEGIN
    FOR i IN 0..months_ahead LOOP
        start_date := DATE_TRUNC('month', CURRENT_DATE + (i || ' months')::INTERVAL);
        end_date := start_date + INTERVAL '1 month';
        partition_name := table_name || '_' || TO_CHAR(start_date, 'YYYY_MM');
        
        EXECUTE format(
            'CREATE TABLE IF NOT EXISTS %I PARTITION OF %I FOR VALUES FROM (%L) TO (%L)',
            partition_name, table_name, start_date, end_date
        );
    END LOOP;
END;
$$ LANGUAGE plpgsql;
```

### 7.2 Neo4j 优化

```cypher
// 索引优化
CREATE CONSTRAINT content_node_id IF NOT EXISTS
FOR (n:ContentNode) REQUIRE n.node_id IS UNIQUE;

CREATE INDEX content_node_type_engine IF NOT EXISTS
FOR (n:ContentNode) ON (n.node_type, n.engine_type);

CREATE INDEX project_rating IF NOT EXISTS
FOR (p:Project) ON (p.rating_average);

// 查询优化示例
// BAD: 全图扫描
MATCH (n) WHERE n.name = 'Cultist' RETURN n;

// GOOD: 使用标签 + 属性索引
MATCH (n:ContentNode {name: 'Cultist'}) RETURN n;

// BAD: 笛卡尔积
MATCH (a:ContentNode), (b:ContentNode) WHERE a.name = b.name RETURN a, b;

// GOOD: 使用关系避免笛卡尔积
MATCH (a:ContentNode)-[:RELATES_TO]->(b:ContentNode)
WHERE a.name = 'Cultist'
RETURN b;

// 批量导入优化（使用 apoc.periodic.iterate）
CALL apoc.periodic.iterate(
    'UNWIND $nodes AS node RETURN node',
    'CREATE (n:ContentNode) SET n = node',
    {batchSize: 10000, parallel: true, params: {nodes: $nodeList}}
);
```

---

## 8. 容量规划模型

### 8.1 自动容量规划

```python
class AutoCapacityPlanner:
    """自动容量规划器"""
    
    def __init__(self):
        self.metrics = MetricsClient()
        self.k8s = KubernetesClient()
        self.cost = CostClient()
    
    async def run_weekly_planning(self):
        """每周运行容量规划"""
        
        # 1. 获取过去 30 天的指标
        metrics = await self.metrics.query_range(
            queries=[
                "avg_cpu_utilization",
                "avg_memory_utilization",
                "p99_latency",
                "queue_depth",
                "error_rate",
            ],
            duration="30d",
        )
        
        # 2. 趋势预测
        forecast = await self.forecast_metrics(metrics, horizon="14d")
        
        # 3. 识别瓶颈
        bottlenecks = self.identify_bottlenecks(forecast)
        
        # 4. 生成建议
        recommendations = []
        
        for bottleneck in bottlenecks:
            if bottleneck.resource == "cpu" and bottleneck.forecast_utilization > 0.8:
                recommendations.append({
                    "service": bottleneck.service,
                    "action": "scale_up",
                    "current_replicas": bottleneck.current_replicas,
                    "recommended_replicas": int(bottleneck.current_replicas * 1.5),
                    "estimated_cost_increase": self.estimate_cost(
                        bottleneck.service,
                        bottleneck.current_replicas,
                        int(bottleneck.current_replicas * 1.5),
                    ),
                })
            
            elif bottleneck.resource == "memory" and bottleneck.forecast_utilization > 0.85:
                recommendations.append({
                    "service": bottleneck.service,
                    "action": "increase_memory_limit",
                    "current_limit": bottleneck.current_limit,
                    "recommended_limit": bottleneck.current_limit * 1.5,
                })
        
        # 5. 发送报告
        await self.send_capacity_report(recommendations)
        
        # 6. 自动执行（如果启用）
        if self.auto_scaling_enabled:
            for rec in recommendations:
                if rec["action"] == "scale_up" and rec["estimated_cost_increase"] < self.max_auto_cost:
                    await self.k8s.scale_deployment(
                        rec["service"],
                        rec["recommended_replicas"],
                    )
    
    async def forecast_metrics(self, metrics: dict, horizon: str) -> dict:
        """使用简单线性回归预测"""
        
        forecasts = {}
        
        for metric_name, values in metrics.items():
            # 简单趋势：计算过去 7 天的增长率
            recent = values[-7:]
            older = values[-14:-7]
            
            recent_avg = sum(recent) / len(recent)
            older_avg = sum(older) / len(older)
            
            growth_rate = (recent_avg - older_avg) / older_avg if older_avg > 0 else 0
            
            # 预测未来
            forecast_values = []
            for day in range(14):
                forecast_values.append(recent_avg * (1 + growth_rate) ** (day / 7))
            
            forecasts[metric_name] = forecast_values
        
        return forecasts
```

---

## 9. 成本优化策略

### 9.1 分层成本结构

| 成本类别 | 占比（估算） | 优化策略 |
|---------|-------------|---------|
| **LLM API** | 50-60% | 批处理、缓存、模型降级、本地模型 |
| **计算（K8s）** | 15-20% | Spot 实例、自动缩容、调度优化 |
| **存储（S3）** | 10-15% | 生命周期策略、压缩、归档 |
| **数据库** | 5-10% | 读写分离、归档、连接池 |
| **CDN/带宽** | 5-8% | 压缩、边缘缓存、P2P |
| **向量数据库** | 3-5% | 维度降维、批量更新 |
| **监控/日志** | 2-3% | 采样、聚合、保留期管理 |

### 9.2 成本优化措施

```yaml
# 成本优化配置

cost_optimization:
  # 1. 计算优化
  compute:
    spot_instances:
      enabled: true
      services:
        - "udify-sandbox-executor"      # 沙箱可容忍中断
        - "udify-perception-worker"      # 感知任务可重试
      max_interruption_rate: 0.1         # 最多 10% 中断率
    
    auto_shutdown:
      enabled: true
      non_prod_shutdown_time: "20:00"    # 非生产环境 20:00 关机
      non_prod_startup_time: "08:00"     # 次日 08:00 启动
    
    right_sizing:
      enabled: true
      check_interval: "7d"               # 每周检查资源使用
      threshold: 0.3                     # 平均利用率 < 30% 则降配
  
  # 2. LLM 成本优化
  llm:
    caching:
      enabled: true
      cache_similarity_threshold: 0.95   # 语义相似度 > 95% 复用缓存
      ttl: "24h"
    
    model_tiering:
      default: "gpt-4o-mini"             # 默认使用便宜模型
      upgrade_conditions:
        - "intent_complexity > 0.8"
        - "user_tier in ['pro', 'team', 'enterprise']"
      
    batch_processing:
      enabled: true
      max_batch_size: 10
      max_wait_time: "5s"
    
    local_fallback:
      enabled: true
      model: "llama-3.1-8b"
      conditions:
        - "request_type == 'simple_intent_classification'"
        - "local_model_confidence > 0.8"
  
  # 3. 存储优化
  storage:
    lifecycle:
      - bucket: "udify-execution-outputs"
        rules:
          - age: 7
            action: "delete"
      
      - bucket: "udify-user-uploads"
        rules:
          - age: 90
            action: "transition"
            storage_class: "GLACIER"
      
      - bucket: "udify-cdl-documents"
        rules:
          - age: 365
            action: "transition"
            storage_class: "DEEP_ARCHIVE"
    
    compression:
      enabled: true
      algorithms:
        - "gzip"      # 文本
        - "zstd"      # 结构化数据
        - "brotli"    # 静态资源
  
  # 4. 数据库优化
  database:
    archiving:
      enabled: true
      tables:
        - name: "events"
          archive_after: "90d"
          archive_to: "s3://udify-archive/events/"
        
        - name: "sandbox_logs"
          archive_after: "30d"
          archive_to: "s3://udify-archive/sandbox-logs/"
    
    index_cleanup:
      enabled: true
      interval: "30d"
      min_usage: 10  # 删除 30 天内使用 < 10 次的索引
```

### 9.3 成本告警

```python
# 成本告警规则

cost_alerts = [
    {
        "name": "Daily LLM Budget",
        "condition": "daily_llm_cost > $2000",
        "severity": "warning",
        "action": "notify_platform_team",
    },
    {
        "name": "LLM Budget Critical",
        "condition": "daily_llm_cost > $5000",
        "severity": "critical",
        "action": "page_oncall + enable_emergency_throttling",
    },
    {
        "name": "Compute Overrun",
        "condition": "daily_compute_cost > 150% of monthly_average",
        "severity": "warning",
        "action": "investigate_and_optimize",
    },
    {
        "name": "Storage Growth",
        "condition": "weekly_storage_growth > 50%",
        "severity": "warning",
        "action": "review_retention_policies",
    },
]
```

---

> **"性能不是功能完成后的优化，而是架构设计的第一天就要考虑的核心属性。Udify 的用户不会等待——一个意图处理超过 30 秒，创意冲动就会消失。每一毫秒的优化，都是对创作者耐心的尊重。"**
>
> —— Udify 性能架构原则
