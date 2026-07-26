<!--
status: frozen
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 被 v3 取代的历史架构。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# Udify 事件驱动架构

> **版本**: v1.0 | **日期**: 2026-04-27
>
> **范围**: 事件总线、Saga 分布式事务、事件溯源、CDC、消息队列、幂等性、最终一致性

---

## 目录

1. [事件驱动架构总览](#1-事件驱动架构总览)
2. [事件总线设计](#2-事件总线设计)
3. [事件 Schema 与版本控制](#3-事件-schema-与版本控制)
4. [Saga 分布式事务](#4-saga-分布式事务)
5. [事件溯源（Event Sourcing）](#5-事件溯源event-sourcing)
6. [变更数据捕获（CDC）](#6-变更数据捕获cdc)
7. [消费者模式](#7-消费者模式)
8. [幂等性与有序性](#8-幂等性与有序性)
9. [死信队列与重试](#9-死信队列与重试)

---

## 1. 事件驱动架构总览

### 1.1 为什么事件驱动

```yaml
事件驱动的优势:
  1_loose_coupling:
    description: "服务之间通过事件间接通信，无需知道对方存在"
    example: "ProjectService 发布 ProjectCreated，SearchService 监听并索引"
  
  2_scalability:
    description: "消费者可以独立扩展"
    example: "高峰期增加 SearchIndexer 实例"
  
  3_resilience:
    description: "服务暂时不可用不会丢失事件"
    example: "EmailService 宕机，事件在队列中等待恢复"
  
  4_auditability:
    description: "所有状态变更都有不可变的事件记录"
    example: "完整的项目修改历史"
  
  5_real_time:
    description: "近实时的数据同步"
    example: "协作编辑的光标同步"
```

### 1.2 架构全景

```
事件驱动架构
    │
    ├──→ 事件生产者
    │       ├──→ API Gateway（HTTP 请求 → 事件）
    │       ├──→ CDC（数据库变更 → 事件）
    │       ├──→ 定时任务（Cron → 事件）
    │       └──→ 外部 Webhook（第三方 → 事件）
    │
    ├──→ 事件总线（Redis Streams / Kafka）
    │       ├──→ Topic: udify.events.projects
    │       ├──→ Topic: udify.events.patches
    │       ├──→ Topic: udify.events.executions
    │       ├──→ Topic: udify.events.users
    │       ├──→ Topic: udify.events.transactions
    │       └──→ Topic: udify.events.notifications
    │
    ├──→ 事件消费者
    │       ├──→ 实时: 协作同步、通知推送
    │       ├──→ 近实时: 搜索索引、缓存更新
    │       ├──→ 异步: 邮件发送、分析统计
    │       └──→ 批处理: 日终报表、数据归档
    │
    └──→ 事件存储
            ├──→ 热存储: Redis Streams（7天）
            ├──→ 温存储: Kafka（30天）
            └──→ 冷存储: S3 Parquet（永久）
```

---

## 2. 事件总线设计

### 2.1 技术选型

| 维度 | Redis Streams | Kafka | 选择 |
|------|--------------|-------|------|
| **延迟** | < 1ms | ~10ms | Redis（实时需求） |
| **吞吐量** | 100K/s | 1M+/s | Kafka（高吞吐） |
| **持久化** | 可选（AOF） | 强持久化 | Kafka（关键事件） |
| **消费者组** | 支持 | 强大 | 两者都支持 |
| **运维复杂度** | 低 | 高 | Redis（初期） |
| **replay** | 有限 | 完整 | Kafka（审计需求） |

**Udify 策略**:
- **实时事件**（协作、通知）: Redis Streams
- **业务事件**（项目、交易）: Kafka
- **CDC 事件**: Kafka + Kafka Connect

### 2.2 事件总线实现

```python
# udify/infrastructure/event_bus.py

from abc import ABC, abstractmethod
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json
import asyncio

from kafka import KafkaProducer, KafkaConsumer
from kafka.admin import KafkaAdminClient, NewTopic
import redis.asyncio as redis


@dataclass
class DomainEvent:
    """领域事件基类"""
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    version: int
    timestamp: datetime
    payload: Dict[str, Any]
    metadata: Dict[str, Any]
    
    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "version": self.version,
            "timestamp": self.timestamp.isoformat(),
            "payload": self.payload,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DomainEvent":
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            aggregate_type=data["aggregate_type"],
            aggregate_id=data["aggregate_id"],
            version=data["version"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            payload=data["payload"],
            metadata=data["metadata"],
        )


class EventBus(ABC):
    """事件总线抽象"""
    
    @abstractmethod
    async def publish(self, topic: str, event: DomainEvent) -> bool:
        """发布事件"""
        pass
    
    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        consumer_group: str,
        handler: Callable[[DomainEvent], None],
    ) -> None:
        """订阅事件"""
        pass
    
    @abstractmethod
    async def create_topic(self, topic: str, partitions: int = 3, replication: int = 2) -> None:
        """创建主题"""
        pass


class KafkaEventBus(EventBus):
    """Kafka 事件总线实现"""
    
    def __init__(self, bootstrap_servers: str):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',           # 等待所有副本确认
            retries=3,
            max_in_flight_requests_per_connection=5,
            enable_idempotence=True,  # 幂等生产者
        )
        self.admin_client = KafkaAdminClient(bootstrap_servers=bootstrap_servers)
    
    async def publish(self, topic: str, event: DomainEvent) -> bool:
        """发布事件到 Kafka"""
        future = self.producer.send(
            topic=topic,
            key=event.aggregate_id,
            value=event.to_dict(),
            headers={
                "event_type": event.event_type,
                "aggregate_type": event.aggregate_type,
                "version": str(event.version),
            },
        )
        
        # 异步等待确认
        record_metadata = await asyncio.get_event_loop().run_in_executor(None, future.get)
        
        logger.info(
            f"Published event {event.event_id} to {topic} "
            f"partition={record_metadata.partition} offset={record_metadata.offset}"
        )
        
        return True
    
    async def subscribe(
        self,
        topic: str,
        consumer_group: str,
        handler: Callable[[DomainEvent], None],
    ) -> None:
        """订阅事件"""
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=self.producer.config['bootstrap_servers'],
            group_id=consumer_group,
            auto_offset_reset='earliest',
            enable_auto_commit=False,  # 手动提交，确保处理完成
            value_deserializer=lambda v: json.loads(v.decode('utf-8')),
            max_poll_records=100,
            max_poll_interval_ms=300000,
        )
        
        try:
            async for message in self._async_consumer(consumer):
                try:
                    event = DomainEvent.from_dict(message.value)
                    await handler(event)
                    
                    # 手动提交偏移量
                    consumer.commit()
                    
                except Exception as e:
                    logger.error(f"Error processing event {message.value.get('event_id')}: {e}")
                    # 发送到死信队列
                    await self._send_to_dlq(message, str(e))
                    consumer.commit()  # 仍然提交，避免阻塞
                    
        finally:
            consumer.close()
    
    async def _async_consumer(self, consumer):
        """将同步 KafkaConsumer 包装为异步生成器"""
        loop = asyncio.get_event_loop()
        while True:
            messages = await loop.run_in_executor(None, consumer.poll, timeout_ms=1000)
            for tp, msgs in messages.items():
                for msg in msgs:
                    yield msg
    
    async def create_topic(self, topic: str, partitions: int = 3, replication: int = 2) -> None:
        """创建 Kafka 主题"""
        try:
            new_topic = NewTopic(
                name=topic,
                num_partitions=partitions,
                replication_factor=replication,
                config={
                    'retention.ms': '604800000',      # 7 天保留
                    'cleanup.policy': 'delete',
                    'compression.type': 'lz4',
                },
            )
            self.admin_client.create_topics([new_topic])
            logger.info(f"Created Kafka topic: {topic}")
        except TopicAlreadyExistsError:
            logger.info(f"Topic {topic} already exists")
    
    async def _send_to_dlq(self, message, error_reason: str):
        """发送到死信队列"""
        dlq_topic = f"{message.topic}.dlq"
        dlq_message = {
            "original_message": message.value,
            "error": error_reason,
            "failed_at": datetime.utcnow().isoformat(),
            "retry_count": message.headers.get("retry_count", 0) if message.headers else 0,
        }
        
        self.producer.send(dlq_topic, value=dlq_message)


class RedisEventBus(EventBus):
    """Redis Streams 事件总线（用于实时场景）"""
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
    
    async def publish(self, topic: str, event: DomainEvent) -> bool:
        """发布到 Redis Stream"""
        await self.redis.xadd(
            topic,
            {
                "event": json.dumps(event.to_dict()),
                "type": event.event_type,
            },
            maxlen=100000,  # 限制流长度
            approximate=True,
        )
        return True
    
    async def subscribe(
        self,
        topic: str,
        consumer_group: str,
        handler: Callable[[DomainEvent], None],
    ) -> None:
        """订阅 Redis Stream"""
        # 创建消费者组
        try:
            await self.redis.xgroup_create(topic, consumer_group, id="0", mkstream=True)
        except redis.ResponseError:
            pass  # 已存在
        
        while True:
            try:
                messages = await self.redis.xreadgroup(
                    groupname=consumer_group,
                    consumername=f"worker-{os.getpid()}",
                    streams={topic: ">"},
                    count=100,
                    block=5000,
                )
                
                for stream, entries in messages:
                    for message_id, fields in entries:
                        try:
                            event_data = json.loads(fields[b"event"])
                            event = DomainEvent.from_dict(event_data)
                            await handler(event)
                            
                            # 确认处理
                            await self.redis.xack(topic, consumer_group, message_id)
                            
                        except Exception as e:
                            logger.error(f"Error processing message {message_id}: {e}")
                            # 不确认，消息会保留在 Pending 列表中
                            
            except Exception as e:
                logger.error(f"Stream read error: {e}")
                await asyncio.sleep(1)
```

---

## 3. 事件 Schema 与版本控制

### 3.1 事件 Schema Registry

```python
# udify/events/schema.py

from dataclasses import dataclass
from typing import Dict, Any, Optional
import jsonschema

class EventSchemaRegistry:
    """事件 Schema 注册中心"""
    
    def __init__(self):
        self.schemas: Dict[str, Dict[str, Any]] = {}
    
    def register(self, event_type: str, version: int, schema: dict):
        """注册事件 Schema"""
        key = f"{event_type}@v{version}"
        self.schemas[key] = schema
    
    def validate(self, event: DomainEvent) -> bool:
        """验证事件是否符合 Schema"""
        key = f"{event.event_type}@v{event.version}"
        schema = self.schemas.get(key)
        
        if not schema:
            logger.warning(f"No schema found for {key}")
            return True  # 无 Schema 时允许通过
        
        try:
            jsonschema.validate(instance=event.payload, schema=schema)
            return True
        except jsonschema.ValidationError as e:
            logger.error(f"Event validation failed for {key}: {e}")
            return False
    
    def get_latest_version(self, event_type: str) -> int:
        """获取最新版本号"""
        versions = [
            int(k.split("@v")[1])
            for k in self.schemas.keys()
            if k.startswith(f"{event_type}@v")
        ]
        return max(versions) if versions else 1


# Schema 定义示例
PROJECT_CREATED_SCHEMA = {
    "type": "object",
    "required": ["project_id", "name", "owner_id", "media_type"],
    "properties": {
        "project_id": {"type": "string", "format": "uuid"},
        "name": {"type": "string", "minLength": 1, "maxLength": 200},
        "slug": {"type": "string", "pattern": "^[a-z0-9-]+$"},
        "description": {"type": ["string", "null"], "maxLength": 5000},
        "owner_id": {"type": "string", "format": "uuid"},
        "media_type": {"enum": ["game", "music", "video", "novel"]},
        "target_game": {"type": ["string", "null"]},
        "target_engine": {"type": ["string", "null"]},
        "visibility": {"enum": ["public", "private", "unlisted"]},
    },
}

PATCH_EXECUTED_SCHEMA = {
    "type": "object",
    "required": ["patch_id", "project_id", "status"],
    "properties": {
        "patch_id": {"type": "string", "format": "uuid"},
        "project_id": {"type": "string", "format": "uuid"},
        "status": {"enum": ["success", "failed", "timeout"]},
        "execution_time_ms": {"type": "integer", "minimum": 0},
        "operations_count": {"type": "integer", "minimum": 0},
        "evaluation_score": {"type": ["number", "null"]},
    },
}

# 注册
registry = EventSchemaRegistry()
registry.register("ProjectCreated", 1, PROJECT_CREATED_SCHEMA)
registry.register("PatchExecuted", 1, PATCH_EXECUTED_SCHEMA)
```

### 3.2 事件版本升级策略

```python
# udify/events/versioning.py

class EventUpgrader:
    """事件版本升级器"""
    
    UPGRADERS = {
        ("ProjectCreated", 1, 2): lambda payload: {
            **payload,
            "ai_automation_level": "none",  # v2 新增字段
        },
        ("PatchExecuted", 1, 2): lambda payload: {
            **payload,
            "sandbox_id": None,  # v2 新增字段
            "resource_usage": {
                "cpu_ms": 0,
                "memory_mb": 0,
            },
        },
    }
    
    @classmethod
    def upgrade(cls, event: DomainEvent, target_version: int) -> DomainEvent:
        """升级事件到目标版本"""
        current_version = event.version
        
        while current_version < target_version:
            upgrader_key = (event.event_type, current_version, current_version + 1)
            upgrader = cls.UPGRADERS.get(upgrader_key)
            
            if not upgrader:
                raise ValueError(f"No upgrader for {upgrader_key}")
            
            event.payload = upgrader(event.payload)
            current_version += 1
        
        event.version = target_version
        return event
```

---

## 4. Saga 分布式事务

### 4.1 Saga 协调器

```python
# udify/saga/coordinator.py

from dataclasses import dataclass, field
from typing import List, Callable, Dict, Any, Optional
from enum import Enum, auto
import asyncio
import uuid

class SagaStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    COMPENSATING = auto()
    COMPENSATED = auto()
    FAILED = auto()

@dataclass
class SagaStep:
    """Saga 步骤"""
    name: str
    action: Callable[[], Any]
    compensation: Callable[[], Any]
    status: SagaStatus = SagaStatus.PENDING
    result: Any = None
    error: Optional[str] = None

@dataclass
class Saga:
    """Saga 定义"""
    saga_id: str
    saga_type: str
    steps: List[SagaStep]
    status: SagaStatus = SagaStatus.PENDING
    current_step: int = 0
    context: Dict[str, Any] = field(default_factory=dict)


class SagaCoordinator:
    """Saga 协调器"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.active_sagas: Dict[str, Saga] = {}
    
    async def execute(self, saga: Saga) -> SagaResult:
        """执行 Saga"""
        saga.status = SagaStatus.RUNNING
        self.active_sagas[saga.saga_id] = saga
        
        try:
            for i, step in enumerate(saga.steps):
                saga.current_step = i
                step.status = SagaStatus.RUNNING
                
                try:
                    # 执行步骤
                    result = await step.action()
                    step.result = result
                    step.status = SagaStatus.COMPLETED
                    
                    # 更新上下文
                    saga.context[step.name] = result
                    
                except Exception as e:
                    step.error = str(e)
                    step.status = SagaStatus.FAILED
                    
                    # 开始补偿
                    logger.error(f"Saga {saga.saga_id} step {step.name} failed: {e}")
                    await self._compensate(saga, i)
                    
                    return SagaResult(
                        success=False,
                        saga_id=saga.saga_id,
                        failed_step=step.name,
                        error=str(e),
                    )
            
            saga.status = SagaStatus.COMPLETED
            
            return SagaResult(
                success=True,
                saga_id=saga.saga_id,
                context=saga.context,
            )
            
        finally:
            del self.active_sagas[saga.saga_id]
    
    async def _compensate(self, saga: Saga, failed_step_index: int):
        """执行补偿"""
        saga.status = SagaStatus.COMPENSATING
        
        # 逆序补偿已完成的步骤
        for i in range(failed_step_index - 1, -1, -1):
            step = saga.steps[i]
            if step.status == SagaStatus.COMPLETED:
                try:
                    await step.compensation()
                    step.status = SagaStatus.COMPENSATED
                except Exception as e:
                    logger.critical(
                        f"Saga {saga.saga_id} compensation failed for step {step.name}: {e}"
                    )
                    # 补偿失败需要人工介入
                    await self._alert_manual_intervention(saga, step, e)
        
        saga.status = SagaStatus.COMPENSATED
    
    async def _alert_manual_intervention(self, saga: Saga, step: SagaStep, error: Exception):
        """告警需要人工介入"""
        await self.event_bus.publish(
            topic="udify.events.saga.manual_intervention",
            event=DomainEvent(
                event_id=str(uuid.uuid4()),
                event_type="SagaCompensationFailed",
                aggregate_type="saga",
                aggregate_id=saga.saga_id,
                version=1,
                timestamp=datetime.utcnow(),
                payload={
                    "saga_id": saga.saga_id,
                    "saga_type": saga.saga_type,
                    "failed_step": step.name,
                    "error": str(error),
                    "context": saga.context,
                },
                metadata={},
            ),
        )


# ===== 创建项目 Saga 示例 =====

async def create_project_saga(
    coordinator: SagaCoordinator,
    project_data: dict,
    user_id: str,
) -> SagaResult:
    """创建项目的 Saga 流程"""
    
    saga = Saga(
        saga_id=str(uuid.uuid4()),
        saga_type="CreateProject",
        steps=[
            SagaStep(
                name="create_postgres_record",
                action=lambda: create_project_in_postgres(project_data),
                compensation=lambda: delete_project_from_postgres(project_data["project_id"]),
            ),
            SagaStep(
                name="create_neo4j_node",
                action=lambda: create_project_node_in_neo4j(project_data),
                compensation=lambda: delete_project_node_from_neo4j(project_data["project_id"]),
            ),
            SagaStep(
                name="init_git_repo",
                action=lambda: initialize_git_repository(project_data["project_id"]),
                compensation=lambda: delete_git_repository(project_data["project_id"]),
            ),
            SagaStep(
                name="init_s3_folder",
                action=lambda: create_s3_project_folder(project_data["project_id"]),
                compensation=lambda: delete_s3_project_folder(project_data["project_id"]),
            ),
            SagaStep(
                name="index_for_search",
                action=lambda: index_project_for_search(project_data),
                compensation=lambda: remove_project_from_search_index(project_data["project_id"]),
            ),
        ],
        context={"user_id": user_id},
    )
    
    return await coordinator.execute(saga)
```

### 4.2 Saga 事件流

```
创建项目 Saga 事件流

1. SagaStarted
   ├──→ 创建 PostgreSQL 记录
   │       ├──→ PostgresRecordCreated ✅
   │       └──→ 失败 → PostgresRecordCreationFailed → 补偿：无
   │
   ├──→ 创建 Neo4j 节点
   │       ├──→ Neo4jNodeCreated ✅
   │       └──→ 失败 → Neo4jNodeCreationFailed → 补偿：删除 PG 记录
   │
   ├──→ 初始化 Git 仓库
   │       ├──→ GitRepoInitialized ✅
   │       └──→ 失败 → GitRepoInitFailed → 补偿：删除 Neo4j 节点 + PG 记录
   │
   ├──→ 创建 S3 文件夹
   │       ├──→ S3FolderCreated ✅
   │       └──→ 失败 → S3FolderCreationFailed → 补偿：删除 Git 仓库 + Neo4j + PG
   │
   ├──→ 索引搜索
   │       ├──→ SearchIndexed ✅
   │       └──→ 失败 → SearchIndexFailed → 补偿：删除 S3 + Git + Neo4j + PG
   │
   └──→ SagaCompleted ✅
```

---

## 5. 事件溯源（Event Sourcing）

### 5.1 实现

```python
# udify/eventsourcing/store.py

from typing import List, Callable
from dataclasses import dataclass

@dataclass
class EventStream:
    """事件流"""
    aggregate_id: str
    aggregate_type: str
    events: List[DomainEvent]
    version: int


class EventStore:
    """事件存储"""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def append(self, event: DomainEvent) -> bool:
        """追加事件"""
        # 乐观并发控制：检查版本
        latest_version = await self.get_latest_version(
            event.aggregate_type,
            event.aggregate_id,
        )
        
        if event.version != latest_version + 1:
            raise ConcurrencyException(
                f"Expected version {latest_version + 1}, got {event.version}"
            )
        
        # 存储事件
        await self.db.execute(
            insert(EventRecord).values(
                event_id=event.event_id,
                event_type=event.event_type,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                version=event.version,
                payload=event.payload,
                metadata=event.metadata,
                timestamp=event.timestamp,
            )
        )
        
        return True
    
    async def get_stream(
        self,
        aggregate_type: str,
        aggregate_id: str,
        from_version: int = 0,
    ) -> EventStream:
        """获取事件流"""
        result = await self.db.execute(
            select(EventRecord)
            .where(EventRecord.aggregate_type == aggregate_type)
            .where(EventRecord.aggregate_id == aggregate_id)
            .where(EventRecord.version >= from_version)
            .order_by(EventRecord.version)
        )
        
        records = result.scalars().all()
        
        events = [
            DomainEvent(
                event_id=r.event_id,
                event_type=r.event_type,
                aggregate_type=r.aggregate_type,
                aggregate_id=r.aggregate_id,
                version=r.version,
                timestamp=r.timestamp,
                payload=r.payload,
                metadata=r.metadata,
            )
            for r in records
        ]
        
        return EventStream(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            events=events,
            version=events[-1].version if events else 0,
        )
    
    async def get_latest_version(self, aggregate_type: str, aggregate_id: str) -> int:
        """获取最新版本号"""
        result = await self.db.execute(
            select(func.max(EventRecord.version))
            .where(EventRecord.aggregate_type == aggregate_type)
            .where(EventRecord.aggregate_id == aggregate_id)
        )
        return result.scalar() or 0


class AggregateRoot:
    """聚合根基类"""
    
    def __init__(self, aggregate_id: str):
        self.aggregate_id = aggregate_id
        self.version = 0
        self.uncommitted_events: List[DomainEvent] = []
    
    def apply_event(self, event: DomainEvent):
        """应用事件到聚合状态"""
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event.payload)
        self.version = event.version
    
    def create_event(self, event_type: str, payload: dict) -> DomainEvent:
        """创建新事件"""
        self.version += 1
        
        event = DomainEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            aggregate_type=self.__class__.__name__,
            aggregate_id=self.aggregate_id,
            version=self.version,
            timestamp=datetime.utcnow(),
            payload=payload,
            metadata={},
        )
        
        self.uncommitted_events.append(event)
        self.apply_event(event)
        
        return event


# 项目聚合示例
class ProjectAggregate(AggregateRoot):
    """项目聚合根"""
    
    def __init__(self, aggregate_id: str):
        super().__init__(aggregate_id)
        self.name = None
        self.status = None
        self.owner_id = None
        self.patches: List[str] = []
    
    @classmethod
    async def load(cls, event_store: EventStore, project_id: str) -> "ProjectAggregate":
        """从事件存储加载聚合"""
        stream = await event_store.get_stream("Project", project_id)
        
        aggregate = cls(project_id)
        for event in stream.events:
            aggregate.apply_event(event)
        
        aggregate.uncommitted_events = []  # 清除未提交事件
        return aggregate
    
    def create(self, name: str, owner_id: str, media_type: str):
        """创建项目"""
        self.create_event("ProjectCreated", {
            "name": name,
            "slug": slugify(name),
            "owner_id": owner_id,
            "media_type": media_type,
            "status": "draft",
            "visibility": "public",
        })
    
    def apply_patch(self, patch_id: str, evaluation_score: float):
        """应用 Patch"""
        self.create_event("PatchApplied", {
            "patch_id": patch_id,
            "evaluation_score": evaluation_score,
            "applied_at": datetime.utcnow().isoformat(),
        })
    
    def publish(self):
        """发布项目"""
        if self.status != "draft":
            raise InvalidStateException("Only draft projects can be published")
        
        self.create_event("ProjectPublished", {
            "published_at": datetime.utcnow().isoformat(),
        })
    
    # 事件处理器
    def _on_ProjectCreated(self, payload):
        self.name = payload["name"]
        self.status = payload["status"]
        self.owner_id = payload["owner_id"]
    
    def _on_PatchApplied(self, payload):
        self.patches.append(payload["patch_id"])
    
    def _on_ProjectPublished(self, payload):
        self.status = "published"
```

---

## 6. 变更数据捕获（CDC）

### 6.1 Debezium + Kafka Connect

```yaml
# infrastructure/debezium/connector.yml

apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaConnector
metadata:
  name: udify-postgres-connector
  labels:
    strimzi.io/cluster: udify-kafka
spec:
  class: io.debezium.connector.postgresql.PostgresConnector
  tasksMax: 1
  config:
    # 数据库连接
    database.hostname: udify-postgres.udify.svc.cluster.local
    database.port: 5432
    database.user: ${secrets:udify/debezium:username}
    database.password: ${secrets:udify/debezium:password}
    database.dbname: udify
    database.server.name: udify-postgres
    
    # 插件
    plugin.name: pgoutput
    slot.name: debezium
    publication.name: dbz_publication
    
    # 事件格式
    table.include.list: public.projects,public.patches,public.users,public.transactions
    
    # 转换
    transforms: unwrap
    transforms.unwrap.type: io.debezium.transforms.ExtractNewRecordState
    transforms.unwrap.drop.tombstones: false
    transforms.unwrap.delete.handling.mode: rewrite
    
    # 发送到 Kafka
    topic.prefix: udify.cdc
```

### 6.2 CDC 事件消费

```python
# udify/cdc/consumers.py

class CDCConsumer:
    """CDC 事件消费者"""
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
    
    async def handle_project_change(self, cdc_event: dict):
        """处理项目表变更"""
        
        operation = cdc_event["op"]  # c=create, u=update, d=delete
        before = cdc_event.get("before")
        after = cdc_event.get("after")
        
        if operation == "c":
            # 新项目创建
            await self.event_bus.publish(
                topic="udify.events.projects",
                event=DomainEvent(
                    event_id=str(uuid.uuid4()),
                    event_type="ProjectCreated",
                    aggregate_type="project",
                    aggregate_id=after["project_id"],
                    version=1,
                    timestamp=datetime.utcnow(),
                    payload={
                        "project_id": after["project_id"],
                        "name": after["name"],
                        "owner_id": after["owner_id"],
                        "status": after["status"],
                    },
                    metadata={"source": "cdc"},
                ),
            )
        
        elif operation == "u":
            # 项目更新
            changes = self._detect_changes(before, after)
            
            if "status" in changes:
                if after["status"] == "published" and before["status"] == "draft":
                    await self.event_bus.publish(
                        topic="udify.events.projects",
                        event=DomainEvent(
                            event_id=str(uuid.uuid4()),
                            event_type="ProjectPublished",
                            aggregate_type="project",
                            aggregate_id=after["project_id"],
                            version=1,
                            timestamp=datetime.utcnow(),
                            payload={
                                "project_id": after["project_id"],
                                "published_at": after["published_at"],
                            },
                            metadata={"source": "cdc"},
                        ),
                    )
            
            if "endorsement_count" in changes or "rating_average" in changes:
                await self.event_bus.publish(
                    topic="udify.events.projects",
                    event=DomainEvent(
                        event_id=str(uuid.uuid4()),
                        event_type="ProjectStatsUpdated",
                        aggregate_type="project",
                        aggregate_id=after["project_id"],
                        version=1,
                        timestamp=datetime.utcnow(),
                        payload={
                            "project_id": after["project_id"],
                            "endorsement_count": after["endorsement_count"],
                            "rating_average": after["rating_average"],
                        },
                        metadata={"source": "cdc"},
                    ),
                )
        
        elif operation == "d":
            # 项目删除
            await self.event_bus.publish(
                topic="udify.events.projects",
                event=DomainEvent(
                    event_id=str(uuid.uuid4()),
                    event_type="ProjectDeleted",
                    aggregate_type="project",
                    aggregate_id=before["project_id"],
                    version=1,
                    timestamp=datetime.utcnow(),
                    payload={"project_id": before["project_id"]},
                    metadata={"source": "cdc"},
                ),
            )
    
    def _detect_changes(self, before: dict, after: dict) -> dict:
        """检测变更字段"""
        changes = {}
        for key in after:
            if before.get(key) != after.get(key):
                changes[key] = {"old": before.get(key), "new": after.get(key)}
        return changes
```

---

## 7. 消费者模式

### 7.1 消费者类型

```python
# udify/consumers/registry.py

class ConsumerRegistry:
    """消费者注册中心"""
    
    def __init__(self):
        self.consumers: Dict[str, EventConsumer] = {}
    
    def register(self, consumer: EventConsumer):
        self.consumers[consumer.name] = consumer
    
    async def start_all(self):
        tasks = [
            consumer.start()
            for consumer in self.consumers.values()
        ]
        await asyncio.gather(*tasks)


# 消费者基类
class EventConsumer:
    """事件消费者基类"""
    
    def __init__(self, name: str, topics: List[str], event_bus: EventBus):
        self.name = name
        self.topics = topics
        self.event_bus = event_bus
        self.running = False
    
    async def start(self):
        self.running = True
        for topic in self.topics:
            await self.event_bus.subscribe(
                topic=topic,
                consumer_group=self.name,
                handler=self.handle,
            )
    
    async def handle(self, event: DomainEvent):
        raise NotImplementedError
    
    async def stop(self):
        self.running = False


# 具体消费者实现

class SearchIndexConsumer(EventConsumer):
    """搜索索引消费者（近实时）"""
    
    def __init__(self, event_bus: EventBus, search_client: SearchClient):
        super().__init__("search-indexer", ["udify.events.projects"], event_bus)
        self.search_client = search_client
    
    async def handle(self, event: DomainEvent):
        if event.event_type == "ProjectCreated":
            await self.search_client.index_project(event.payload)
        
        elif event.event_type == "ProjectPublished":
            await self.search_client.update_project_status(
                event.payload["project_id"],
                "published",
            )
        
        elif event.event_type == "ProjectDeleted":
            await self.search_client.delete_project(event.payload["project_id"])


class NotificationConsumer(EventConsumer):
    """通知消费者（实时）"""
    
    def __init__(self, event_bus: EventBus, notification_service: NotificationService):
        super().__init__("notification-sender", ["udify.events.projects", "udify.events.transactions"], event_bus)
        self.notification_service = notification_service
    
    async def handle(self, event: DomainEvent):
        if event.event_type == "ProjectEndorsed":
            await self.notification_service.send(
                user_id=event.payload["owner_id"],
                type="endorsement",
                content=f"Your project received a new endorsement!",
                link=f"/project/{event.payload['project_id']}",
            )
        
        elif event.event_type == "TransactionCompleted":
            await self.notification_service.send(
                user_id=event.payload["payee_id"],
                type="payment",
                content=f"You received ${event.payload['amount']}!",
            )


class AnalyticsConsumer(EventConsumer):
    """分析消费者（批处理容忍延迟）"""
    
    def __init__(self, event_bus: EventBus, analytics_db: AnalyticsDB):
        super().__init__("analytics-aggregator", ["udify.events.#"], event_bus)
        self.analytics_db = analytics_db
        self.batch: List[DomainEvent] = []
        self.batch_size = 100
        self.flush_interval = 30  # 秒
    
    async def start(self):
        # 启动批量刷新定时器
        asyncio.create_task(self._periodic_flush())
        await super().start()
    
    async def handle(self, event: DomainEvent):
        self.batch.append(event)
        
        if len(self.batch) >= self.batch_size:
            await self._flush()
    
    async def _periodic_flush(self):
        while self.running:
            await asyncio.sleep(self.flush_interval)
            if self.batch:
                await self._flush()
    
    async def _flush(self):
        if not self.batch:
            return
        
        events = self.batch
        self.batch = []
        
        # 批量写入分析数据库
        await self.analytics_db.insert_events(events)
```

---

## 8. 幂等性与有序性

### 8.1 幂等性保证

```python
# udify/events/idempotency.py

class IdempotencyChecker:
    """幂等性检查器"""
    
    def __init__(self, redis: redis.Redis):
        self.redis = redis
        self.ttl = 86400 * 7  # 7 天
    
    async def is_processed(self, event_id: str) -> bool:
        """检查事件是否已处理"""
        key = f"idempotency:{event_id}"
        return await self.redis.exists(key) > 0
    
    async def mark_processed(self, event_id: str, result: dict = None):
        """标记事件已处理"""
        key = f"idempotency:{event_id}"
        value = json.dumps({"processed_at": datetime.utcnow().isoformat(), "result": result})
        await self.redis.setex(key, self.ttl, value)
    
    async def get_processed_result(self, event_id: str) -> Optional[dict]:
        """获取已处理事件的结果"""
        key = f"idempotency:{event_id}"
        value = await self.redis.get(key)
        if value:
            return json.loads(value)
        return None


# 幂等消费者装饰器
def idempotent(handler):
    """幂等性装饰器"""
    async def wrapper(self, event: DomainEvent):
        checker = self.idempotency_checker
        
        # 检查是否已处理
        if await checker.is_processed(event.event_id):
            logger.info(f"Event {event.event_id} already processed, skipping")
            cached_result = await checker.get_processed_result(event.event_id)
            return cached_result
        
        # 处理事件
        result = await handler(self, event)
        
        # 标记已处理
        await checker.mark_processed(event.event_id, result)
        
        return result
    
    return wrapper


# 使用示例
class PaymentConsumer(EventConsumer):
    @idempotent
    async def handle(self, event: DomainEvent):
        if event.event_type == "TransactionRequested":
            return await self.process_payment(event.payload)
```

### 8.2 有序性保证

```python
# udify/events/ordering.py

class OrderedConsumer(EventConsumer):
    """有序消费者（按聚合 ID 分区）"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.processing_locks: Dict[str, asyncio.Lock] = {}
    
    async def handle(self, event: DomainEvent):
        """按聚合 ID 顺序处理"""
        aggregate_id = event.aggregate_id
        
        # 获取或创建该聚合的锁
        if aggregate_id not in self.processing_locks:
            self.processing_locks[aggregate_id] = asyncio.Lock()
        
        lock = self.processing_locks[aggregate_id]
        
        async with lock:
            # 检查版本顺序
            expected_version = await self.get_last_processed_version(aggregate_id) + 1
            
            if event.version < expected_version:
                logger.warning(f"Out of order event: got v{event.version}, expected v{expected_version}")
                return  # 旧事件，忽略
            
            if event.version > expected_version:
                # 缺失事件，需要等待或查询
                logger.error(f"Missing events: got v{event.version}, expected v{expected_version}")
                await self._wait_for_missing_events(aggregate_id, expected_version, event.version)
            
            # 处理事件
            await self._process_event(event)
            
            # 更新最新版本
            await self.set_last_processed_version(aggregate_id, event.version)
    
    async def get_last_processed_version(self, aggregate_id: str) -> int:
        """获取最后处理的版本"""
        key = f"ordering:{aggregate_id}"
        version = await self.redis.get(key)
        return int(version) if version else 0
    
    async def set_last_processed_version(self, aggregate_id: str, version: int):
        """设置最后处理的版本"""
        key = f"ordering:{aggregate_id}"
        await self.redis.set(key, str(version))
```

---

## 9. 死信队列与重试

### 9.1 重试策略

```python
# udify/events/retry.py

from dataclasses import dataclass
from enum import Enum

class RetryPolicy(Enum):
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    LINEAR = "linear"

@dataclass
class RetryConfig:
    max_retries: int = 3
    policy: RetryPolicy = RetryPolicy.EXPONENTIAL
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0
    retryable_exceptions: tuple = (ConnectionError, TimeoutError)


class RetryableConsumer(EventConsumer):
    """支持重试的消费者"""
    
    def __init__(self, *args, retry_config: RetryConfig = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.retry_config = retry_config or RetryConfig()
    
    async def handle(self, event: DomainEvent):
        """带重试的处理"""
        last_exception = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                return await self._do_handle(event)
            except Exception as e:
                last_exception = e
                
                # 检查是否可重试
                if not isinstance(e, self.retry_config.retryable_exceptions):
                    raise  # 不可重试，直接失败
                
                if attempt < self.retry_config.max_retries:
                    delay = self._calculate_delay(attempt)
                    logger.warning(
                        f"Event {event.event_id} failed (attempt {attempt + 1}), "
                        f"retrying in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
        
        # 所有重试失败，发送到死信队列
        await self._send_to_dlq(event, last_exception)
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟"""
        if self.retry_config.policy == RetryPolicy.FIXED:
            return self.retry_config.base_delay_seconds
        
        elif self.retry_config.policy == RetryPolicy.EXPONENTIAL:
            delay = self.retry_config.base_delay_seconds * (2 ** attempt)
            return min(delay, self.retry_config.max_delay_seconds)
        
        elif self.retry_config.policy == RetryPolicy.LINEAR:
            delay = self.retry_config.base_delay_seconds * (attempt + 1)
            return min(delay, self.retry_config.max_delay_seconds)
    
    async def _send_to_dlq(self, event: DomainEvent, error: Exception):
        """发送到死信队列"""
        dlq_event = DomainEvent(
            event_id=str(uuid.uuid4()),
            event_type="DeadLetter",
            aggregate_type="dlq",
            aggregate_id=event.event_id,
            version=1,
            timestamp=datetime.utcnow(),
            payload={
                "original_event": event.to_dict(),
                "error": str(error),
                "error_type": type(error).__name__,
                "retry_count": self.retry_config.max_retries,
            },
            metadata={},
        )
        
        await self.event_bus.publish(
            topic=f"udify.dlq.{event.event_type}",
            event=dlq_event,
        )
        
        logger.error(f"Event {event.event_id} sent to DLQ after {self.retry_config.max_retries} retries")
```

### 9.2 DLQ 监控与重处理

```python
class DLQMonitor:
    """死信队列监控器"""
    
    def __init__(self, event_bus: EventBus, alert_service: AlertService):
        self.event_bus = event_bus
        self.alert_service = alert_service
    
    async def monitor(self):
        """监控 DLQ"""
        await self.event_bus.subscribe(
            topic="udify.dlq.#",
            consumer_group="dlq-monitor",
            handler=self._handle_dlq_event,
        )
    
    async def _handle_dlq_event(self, event: DomainEvent):
        """处理 DLQ 事件"""
        original_event = event.payload["original_event"]
        error = event.payload["error"]
        
        # 记录到数据库
        await self._record_dlq(event)
        
        # 根据错误类型决定告警级别
        if "timeout" in error.lower():
            await self.alert_service.send_alert(
                severity="warning",
                message=f"DLQ event (timeout): {original_event['event_type']} {original_event['event_id']}",
            )
        elif "connection" in error.lower():
            await self.alert_service.send_alert(
                severity="critical",
                message=f"DLQ event (connection): {original_event['event_type']} {original_event['event_id']}",
            )
        else:
            await self.alert_service.send_alert(
                severity="error",
                message=f"DLQ event ({event.payload['error_type']}): {original_event['event_type']} {original_event['event_id']}",
            )
    
    async def reprocess(self, event_id: str):
        """手动重处理 DLQ 事件"""
        # 从数据库获取原始事件
        dlq_record = await self._get_dlq_record(event_id)
        
        if not dlq_record:
            raise ValueError(f"DLQ record {event_id} not found")
        
        # 重新发布到原主题
        original_event = DomainEvent.from_dict(dlq_record["original_event"])
        
        await self.event_bus.publish(
            topic=f"udify.events.{original_event.aggregate_type}",
            event=original_event,
        )
        
        # 标记为已重处理
        await self._mark_reprocessed(event_id)
```

---

> **"事件是系统的脉搏。每一次状态变更都是一个事件，每一个事件都是一次承诺——承诺数据会传播、承诺副作用会执行、承诺最终一致性会达成。事件驱动不是异步的借口，而是可靠性的基石。"**
>
> —— Udify 事件驱动架构原则
