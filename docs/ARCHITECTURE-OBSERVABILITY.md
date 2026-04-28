# Udify 可观测性与 SRE 架构

> **版本**: v1.0 | **日期**: 2026-04-27
>
> **范围**: OpenTelemetry 全链路追踪、指标体系、日志聚合、告警策略、SLO/SLA 定义、混沌工程

---

## 目录

1. [可观测性架构总览](#1-可观测性架构总览)
2. [指标系统（Metrics）](#2-指标系统metrics)
3. [分布式追踪（Tracing）](#3-分布式追踪tracing)
4. [日志系统（Logging）](#4-日志系统logging)
5. [告警与事件管理](#5-告警与事件管理)
6. [SLO / SLA / SLI 定义](#6-slo--sla--sli-定义)
7. [混沌工程（Chaos Engineering）](#7-混沌工程chaos-engineering)
8. [性能剖析（Profiling）](#8-性能剖析profiling)
9. [成本可观测性](#9-成本可观测性)

---

## 1. 可观测性架构总览

### 1.1 三大支柱 + 第四支柱

```
Udify 可观测性架构
    │
    ├──→ Metrics（指标）—— "发生了什么"
    │       ├──→ Prometheus + Grafana
    │       ├──→ 业务指标（KPI）
    │       ├──→ 系统指标（CPU/内存/网络）
    │       └──→ AI 指标（Token 消耗、延迟、准确率）
    │
    ├──→ Logs（日志）—— "为什么发生"
    │       ├──→ Loki / Grafana
    │       ├──→ 结构化日志（JSON）
    │       ├──→ 日志聚合与搜索
    │       └──→ 审计日志（不可变）
    │
    ├──→ Traces（追踪）—— "在哪里发生"
    │       ├──→ Jaeger / Tempo
    │       ├──→ OpenTelemetry 自动埋点
    │       ├──→ 跨服务追踪
    │       └──→ AI 调用链追踪
    │
    └──→ Profiles（剖析）——第四支柱—— "为什么会慢"
            ├──→ Pyroscope（持续 Profiling）
            ├──→ 火焰图分析
            └──→ 内存泄漏检测
```

### 1.2 数据流

```
┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
│   Service   │   │   Service   │   │   Service   │   │   Service   │
│   (Python)  │   │   (Python)  │   │   (Node.js) │   │   (Go)      │
└──────┬──────┘   └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
       │                 │                 │                 │
       │  OpenTelemetry SDK（自动埋点）                     │
       │                 │                 │                 │
       └────────┬────────┴────────┬────────┴────────┬────────┘
                │                 │                 │
                ▼                 ▼                 ▼
       ┌──────────────────────────────────────────────────┐
       │           OpenTelemetry Collector                 │
       │  • 接收（OTLP / Prometheus / Jaeger）              │
       │  • 处理（过滤、采样、富化）                         │
       │  • 导出（并行发送多个后端）                         │
       └────────┬──────────────┬──────────────┬───────────┘
                │              │              │
                ▼              ▼              ▼
       ┌──────────────┐ ┌──────────┐ ┌──────────────┐
       │  Prometheus  │ │   Loki   │ │  Jaeger/     │
       │  (Metrics)   │ │  (Logs)  │ │  Tempo       │
       └──────┬───────┘ └────┬─────┘ └──────┬───────┘
              │              │              │
              ▼              ▼              ▼
       ┌──────────────────────────────────────────┐
       │              Grafana（统一可视化）          │
       │  • Dashboards                            │
       │  • Alerting                              │
       │  • Correlation（Metrics → Logs → Traces） │
       └──────────────────────────────────────────┘
```

---

## 2. 指标系统（Metrics）

### 2.1 指标分类

```python
# udify/observability/metrics.py

from prometheus_client import Counter, Histogram, Gauge, Summary, Info

class UdifyMetrics:
    """Udify 业务与系统指标定义"""
    
    # ===== 业务指标（KPI）=====
    
    # 意图处理
    INTENT_REQUESTS = Counter(
        'udify_intent_requests_total',
        'Total intent requests',
        ['media_type', 'engine_type', 'status']
    )
    
    INTENT_PROCESSING_DURATION = Histogram(
        'udify_intent_processing_seconds',
        'Intent processing duration',
        ['stage'],  # perception, planning, evaluation, execution
        buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
    )
    
    # Patch 生成
    PATCH_GENERATED = Counter(
        'udify_patches_generated_total',
        'Total patches generated',
        ['media_type', 'automation_level', 'risk_level']
    )
    
    PATCH_EVALUATION_SCORE = Histogram(
        'udify_patch_evaluation_score',
        'Patch evaluation score distribution',
        ['dimension'],  # quality, innovation, compatibility, safety, performance
        buckets=[1, 2, 3, 4, 5]
    )
    
    # 用户参与
    ACTIVE_USERS = Gauge(
        'udify_active_users',
        'Number of active users',
        ['tier']  # free, pro, team, enterprise
    )
    
    PROJECT_CREATED = Counter(
        'udify_projects_created_total',
        'Total projects created',
        ['media_type', 'visibility']
    )
    
    # 创作者经济
    TRANSACTION_VALUE = Counter(
        'udify_transaction_value_usd_total',
        'Total transaction value in USD',
        ['type']  # subscription, tip, bounty, marketplace
    )
    
    # ===== AI 指标 =====
    
    LLM_REQUESTS = Counter(
        'udify_llm_requests_total',
        'Total LLM API requests',
        ['provider', 'model', 'status']
    )
    
    LLM_LATENCY = Histogram(
        'udify_llm_latency_seconds',
        'LLM API latency',
        ['provider', 'model'],
        buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
    )
    
    LLM_TOKENS = Counter(
        'udify_llm_tokens_total',
        'Total LLM tokens consumed',
        ['provider', 'model', 'type']  # type: prompt, completion
    )
    
    LLM_COST_USD = Counter(
        'udify_llm_cost_usd_total',
        'Total LLM API cost in USD',
        ['provider', 'model']
    )
    
    # Prompt 注入检测
    PROMPT_INJECTION_BLOCKED = Counter(
        'udify_prompt_injection_blocked_total',
        'Total prompt injection attempts blocked',
        ['detection_method', 'risk_level']
    )
    
    # ===== 系统指标 =====
    
    SANDBOX_ACTIVE = Gauge(
        'udify_sandbox_active',
        'Number of active sandboxes',
        ['status']  # running, paused, terminated
    )
    
    SANDBOX_EXECUTION_DURATION = Histogram(
        'udify_sandbox_execution_seconds',
        'Sandbox execution duration',
        ['operation_type'],
        buckets=[1, 5, 10, 30, 60, 120, 300, 600]
    )
    
    QUEUE_DEPTH = Gauge(
        'udify_queue_depth',
        'Current queue depth',
        ['queue_name']  # perception, planning, execution
    )
    
    CACHE_HIT_RATIO = Gauge(
        'udify_cache_hit_ratio',
        'Cache hit ratio',
        ['cache_type']  # redis, cdn, query
    )
```

### 2.2 SLO 仪表盘（Grafana）

```yaml
# grafana/dashboards/slo-overview.json（简化 YAML 表示）

dashboard:
  title: "Udify SLO Overview"
  refresh: "30s"
  
  panels:
    # 可用性 SLO
    - title: "Availability SLO: 99.9%"
      type: stat
      targets:
        - expr: |
            sum(rate(udify_http_requests_total{status=~"2..|3.."}[5m]))
            /
            sum(rate(udify_http_requests_total[5m]))
      thresholds:
        - value: 0.999, color: green
        - value: 0.995, color: yellow
        - value: 0.990, color: red
    
    # 意图处理延迟 SLO
    - title: "Intent Processing P99 < 30s"
      type: graph
      targets:
        - expr: |
            histogram_quantile(0.99,
              sum(rate(udify_intent_processing_seconds_bucket[5m])) by (le)
            )
      alert:
        condition: "A > 30"
        for: "5m"
    
    # LLM 成本监控
    - title: "Daily LLM Cost (USD)"
      type: stat
      targets:
        - expr: |
            increase(udify_llm_cost_usd_total[1d])
      thresholds:
        - value: 1000, color: green
        - value: 3000, color: yellow
        - value: 5000, color: red
    
    # 错误率
    - title: "Error Rate < 0.1%"
      type: stat
      targets:
        - expr: |
            sum(rate(udify_http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(udify_http_requests_total[5m]))
    
    # 活跃用户
    - title: "Active Users (7d)"
      type: graph
      targets:
        - expr: |
            sum(udify_active_users) by (tier)
    
    # Patch 成功率
    - title: "Patch Success Rate > 95%"
      type: gauge
      targets:
        - expr: |
            sum(rate(udify_patches_generated_total{status="success"}[1h]))
            /
            sum(rate(udify_patches_generated_total[1h]))
      thresholds:
        - value: 0.95, color: green
        - value: 0.90, color: yellow
        - value: 0, color: red
```

---

## 3. 分布式追踪（Tracing）

### 3.1 OpenTelemetry 配置

```python
# udify/observability/tracing.py

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXInstrumentor

class TracingConfig:
    """OpenTelemetry 追踪配置"""
    
    @staticmethod
    def setup(service_name: str):
        """初始化分布式追踪"""
        
        # 1. 配置 Provider
        provider = TracerProvider(
            resource=Resource.create({
                "service.name": service_name,
                "service.version": "2.1.0",
                "deployment.environment": os.getenv("ENV", "development"),
                "host.name": socket.gethostname(),
            })
        )
        trace.set_tracer_provider(provider)
        
        # 2. OTLP Exporter（发送到 Collector）
        otlp_exporter = OTLPSpanExporter(
            endpoint="udify-otel-collector:4317",
            insecure=True,
        )
        
        # 3. Batch Span Processor（批量发送，低开销）
        span_processor = BatchSpanProcessor(
            otlp_exporter,
            max_queue_size=2048,
            max_export_batch_size=512,
            schedule_delay_millis=5000,
        )
        provider.add_span_processor(span_processor)
        
        # 4. 自动埋点
        FastAPIInstrumentor.instrument_app(app)
        SQLAlchemyInstrumentor().instrument()
        RedisInstrumentor().instrument()
        HTTPXInstrumentor().instrument()
        
        # 5. 自定义埋点（AI 调用链）
        TracingConfig._setup_ai_instrumentation()
    
    @staticmethod
    def _setup_ai_instrumentation():
        """设置 AI 调用链追踪"""
        
        # 包装 LLM 客户端，自动创建 Span
        original_chat = OpenAIClient.chat.completions.create
        
        @wraps(original_chat)
        def traced_chat_create(*args, **kwargs):
            tracer = trace.get_tracer("udify.llm")
            
            with tracer.start_as_current_span("llm.chat_completion") as span:
                # 记录请求参数（脱敏）
                span.set_attribute("llm.model", kwargs.get("model", "unknown"))
                span.set_attribute("llm.temperature", kwargs.get("temperature", 1.0))
                span.set_attribute("llm.max_tokens", kwargs.get("max_tokens", 0))
                
                # 记录消息数量（不记录内容）
                messages = kwargs.get("messages", [])
                span.set_attribute("llm.message_count", len(messages))
                
                start_time = time.time()
                try:
                    response = original_chat(*args, **kwargs)
                    
                    # 记录响应元数据
                    span.set_attribute("llm.response_tokens", response.usage.completion_tokens)
                    span.set_attribute("llm.prompt_tokens", response.usage.prompt_tokens)
                    span.set_attribute("llm.total_tokens", response.usage.total_tokens)
                    span.set_attribute("llm.latency_ms", (time.time() - start_time) * 1000)
                    span.set_attribute("llm.finish_reason", response.choices[0].finish_reason)
                    
                    span.set_status(Status(StatusCode.OK))
                    return response
                    
                except Exception as e:
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e))
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        
        OpenAIClient.chat.completions.create = traced_chat_create
```

### 3.2 追踪语义约定

```python
# 追踪属性命名规范

TRACE_ATTRIBUTES = {
    # 通用
    "service.name": "udify-{component}",
    "service.version": "semver",
    "deployment.environment": "production|staging|development",
    
    # HTTP
    "http.method": "GET|POST|PUT|DELETE",
    "http.url": "path",
    "http.status_code": 200,
    "http.response_size": 1024,
    
    # 数据库
    "db.system": "postgresql|neo4j|redis|pinecone",
    "db.statement": "SELECT ...",  # 脱敏
    "db.operation": "SELECT|INSERT|UPDATE|DELETE",
    "db.response.returned_rows": 10,
    
    # AI / LLM
    "llm.provider": "openai|anthropic|local",
    "llm.model": "gpt-4|claude-3-opus|llama-3",
    "llm.temperature": 0.7,
    "llm.max_tokens": 4096,
    "llm.prompt_tokens": 100,
    "llm.completion_tokens": 500,
    "llm.total_tokens": 600,
    "llm.latency_ms": 2500,
    "llm.finish_reason": "stop|length|content_filter",
    
    # 业务
    "udify.project_id": "uuid",
    "udify.user_id": "uuid",
    "udify.media_type": "game|music|video|novel",
    "udify.engine_type": "unity|unreal|godot",
    "udify.intent_category": "difficulty|content|mechanics|aesthetic",
    "udify.patch_id": "uuid",
    "udify.sandbox_id": "uuid",
    "udify.execution_status": "success|failed|timeout",
    
    # 安全
    "security.risk_level": "low|medium|high|critical",
    "security.detection_method": "pattern|ml|heuristic",
    "security.blocked": True,
}
```

---

## 4. 日志系统（Logging）

### 4.1 结构化日志标准

```python
# udify/observability/logging.py

import structlog
from pythonjsonlogger import jsonlogger

class UdifyLogger:
    """Udify 结构化日志配置"""
    
    @staticmethod
    def setup():
        """配置结构化日志"""
        
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
    
    @staticmethod
    def get_logger(name: str) -> structlog.stdlib.BoundLogger:
        """获取结构化日志记录器"""
        return structlog.get_logger(name)

# 使用示例
logger = UdifyLogger.get_logger("udify.perception")

# 业务日志
logger.info(
    "game_detected",
    game_path="/games/slay-the-spire",
    engine_type="unity",
    confidence=0.95,
    detection_time_ms=250,
)

# 错误日志
logger.error(
    "patch_execution_failed",
    patch_id="uuid",
    project_id="uuid",
    error_type="ScriptSyntaxError",
    error_message="Unexpected token at line 45",
    sandbox_id="uuid",
    retry_count=2,
)

# 安全日志（审计）
logger.warning(
    "prompt_injection_detected",
    user_id="uuid",
    detection_method="pattern_match",
    risk_level="high",
    blocked=True,
    pattern_matched="ignore_all_previous_instructions",
    request_id="uuid",
)
```

### 4.2 日志分级与保留

| 日志类型 | 级别 | 保留期 | 存储 | 访问控制 |
|---------|------|--------|------|---------|
| **应用日志** | INFO+ | 30 天 | Loki | 工程团队 |
| **错误日志** | ERROR+ | 90 天 | Loki + S3 | 工程团队 |
| **审计日志** | INFO | 7 年 | S3（WORM） | 安全 + 合规 |
| **安全日志** | WARNING+ | 2 年 | S3（WORM） | 安全团队 |
| **AI 调用日志** | INFO | 30 天 | Loki | 工程 + AI 团队 |
| **沙箱日志** | DEBUG+ | 7 天 | S3 | 工程团队 |

### 4.3 审计日志（不可变）

```python
class AuditLogger:
    """
    审计日志系统
    
    要求：
    - 不可篡改（WORM 存储）
    - 可追溯（包含完整上下文）
    - 合规（支持 GDPR/CCPA 审计）
    """
    
    def __init__(self):
        self.storage = ImmutableLogStorage()  # S3 with Object Lock
        self.crypto = LogCrypto()  # 链式哈希，防篡改
    
    async def log(self, event: AuditEvent):
        """记录审计事件"""
        
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "event_id": str(uuid.uuid4()),
            "event_type": event.type,
            "actor": {
                "user_id": event.user_id,
                "ip_hash": hashlib.sha256(event.ip.encode()).hexdigest(),
                "session_id": event.session_id,
            },
            "action": {
                "type": event.action,
                "target": event.target,
                "target_type": event.target_type,
            },
            "result": {
                "status": event.status,
                "changes": event.changes,
            },
            "context": {
                "request_id": event.request_id,
                "trace_id": event.trace_id,
            },
            # 链式哈希（防篡改）
            "previous_hash": self.crypto.last_hash,
            "hash": None,  # 将在下面计算
        }
        
        # 计算哈希
        entry["hash"] = self.crypto.hash_entry(entry)
        self.crypto.last_hash = entry["hash"]
        
        # 签名
        entry["signature"] = self.crypto.sign(entry)
        
        # 写入不可变存储
        await self.storage.append(entry)
    
    async def verify_integrity(self, start_time: datetime, end_time: datetime) -> bool:
        """验证审计日志完整性"""
        entries = await self.storage.read_range(start_time, end_time)
        
        for i, entry in enumerate(entries):
            # 1. 验证签名
            if not self.crypto.verify_signature(entry):
                logger.critical(f"Audit log signature invalid at entry {i}")
                return False
            
            # 2. 验证链式哈希
            if i > 0:
                if entry["previous_hash"] != entries[i-1]["hash"]:
                    logger.critical(f"Audit log chain broken at entry {i}")
                    return False
        
        return True
```

---

## 5. 告警与事件管理

### 5.1 告警分级

```yaml
# alerting/rules.yml

groups:
  - name: udify-critical
    interval: 30s
    rules:
      # P0: 服务完全不可用
      - alert: ServiceDown
        expr: up{job=~"udify-.*"} == 0
        for: 1m
        labels:
          severity: p0
          team: sre
        annotations:
          summary: "Service {{ $labels.job }} is down"
          runbook_url: "https://wiki.udify.dev/runbooks/service-down"
      
      # P0: 数据库连接失败
      - alert: DatabaseConnectionFailed
        expr: |
          rate(udify_db_connection_errors_total[1m]) > 0
        for: 2m
        labels:
          severity: p0
          team: sre
      
      # P0: 沙箱逃逸尝试
      - alert: SandboxEscapeAttempt
        expr: |
          rate(udify_security_sandbox_escape_attempts_total[1m]) > 0
        labels:
          severity: p0
          team: security
        annotations:
          summary: "Sandbox escape attempt detected"
  
  - name: udify-high
    interval: 1m
    rules:
      # P1: 错误率飙升
      - alert: HighErrorRate
        expr: |
          sum(rate(udify_http_requests_total{status=~"5.."}[5m]))
          /
          sum(rate(udify_http_requests_total[5m])) > 0.05
        for: 5m
        labels:
          severity: p1
          team: sre
      
      # P1: LLM 成本异常
      - alert: LLMCostSpike
        expr: |
          increase(udify_llm_cost_usd_total[1h]) > 1000
        labels:
          severity: p1
          team: platform
        annotations:
          summary: "LLM cost exceeded $1000 in 1 hour"
      
      # P1: 队列堆积
      - alert: QueueBacklog
        expr: |
          udify_queue_depth > 1000
        for: 10m
        labels:
          severity: p1
          team: platform
      
      # P1: Prompt 注入攻击
      - alert: PromptInjectionAttack
        expr: |
          rate(udify_prompt_injection_blocked_total[5m]) > 10
        labels:
          severity: p1
          team: security
  
  - name: udify-medium
    interval: 5m
    rules:
      # P2: 延迟升高
      - alert: HighLatency
        expr: |
          histogram_quantile(0.99,
            sum(rate(udify_intent_processing_seconds_bucket[5m])) by (le)
          ) > 60
        for: 10m
        labels:
          severity: p2
          team: sre
      
      # P2: 缓存命中率下降
      - alert: LowCacheHitRate
        expr: |
          udify_cache_hit_ratio < 0.5
        for: 15m
        labels:
          severity: p2
          team: platform
  
  - name: udify-low
    interval: 15m
    rules:
      # P3: 磁盘空间预警
      - alert: DiskSpaceLow
        expr: |
          (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.1
        labels:
          severity: p3
          team: sre
```

### 5.2 告警路由

```yaml
# alertmanager/config.yml

global:
  smtp_smarthost: 'smtp.udify.dev:587'
  smtp_from: 'alerts@udify.dev'

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'default'
  
  routes:
    # P0: 立即电话 + Slack + PagerDuty
    - match:
        severity: p0
      receiver: 'p0-critical'
      group_wait: 0s
      repeat_interval: 5m
    
    # P1: Slack + PagerDuty（非工作时间）
    - match:
        severity: p1
      receiver: 'p1-high'
    
    # P2: Slack 告警
    - match:
        severity: p2
      receiver: 'p2-medium'
    
    # P3: 仅邮件
    - match:
        severity: p3
      receiver: 'p3-low'
      repeat_interval: 24h
    
    # 安全事件：额外发送给安全团队
    - match:
        team: security
      receiver: 'security-team'
      continue: true  # 继续匹配其他路由

receivers:
  - name: 'default'
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#alerts'
  
  - name: 'p0-critical'
    pagerduty_configs:
      - service_key: '${PAGERDUTY_SERVICE_KEY}'
        severity: critical
    slack_configs:
      - api_url: '${SLACK_WEBHOOK_URL}'
        channel: '#incidents'
        send_resolved: true
    webhook_configs:
      - url: 'https://api.udify.dev/v1/alerts/phone'
        send_resolved: false
  
  - name: 'security-team'
    slack_configs:
      - api_url: '${SLACK_SECURITY_WEBHOOK}'
        channel: '#security-alerts'
    email_configs:
      - to: 'security@udify.dev'
```

---

## 6. SLO / SLA / SLI 定义

### 6.1 服务等级定义

```yaml
# SLO 定义

service_level_objectives:
  # ===== API 服务 =====
  api_availability:
    description: "API 可用性"
    slo: 99.9%  # 每年最多 8.76 小时停机
    measurement: |
      good_events: sum(rate(udify_http_requests_total{status!~"5.."}[window]))
      total_events: sum(rate(udify_http_requests_total[window]))
      SLI: good_events / total_events
    windows:
      - type: rolling
        duration: 30d
    alert:
      burn_rate: 2  # 2x 预算消耗速度时告警
      
  api_latency:
    description: "API 响应延迟"
    slo: "P99 < 500ms"
    measurement: |
      good_events: sum(rate(udify_http_request_duration_seconds_bucket{le="0.5"}[window]))
      total_events: sum(rate(udify_http_request_duration_seconds_count[window]))
      SLI: good_events / total_events
    windows:
      - type: rolling
        duration: 30d
  
  # ===== AI 服务 =====
  intent_processing_latency:
    description: "意图处理延迟（端到端）"
    slo: "P95 < 60s, P99 < 120s"
    measurement: |
      good_events: sum(rate(udify_intent_processing_seconds_bucket{le="120"}[window]))
      total_events: sum(rate(udify_intent_processing_seconds_count[window]))
      SLI: good_events / total_events
    windows:
      - type: rolling
        duration: 7d
  
  llm_success_rate:
    description: "LLM 调用成功率"
    slo: 99.5%
    measurement: |
      good_events: sum(rate(udify_llm_requests_total{status="success"}[window]))
      total_events: sum(rate(udify_llm_requests_total[window]))
      SLI: good_events / total_events
  
  # ===== 沙箱服务 =====
  sandbox_execution_success:
    description: "沙箱执行成功率"
    slo: 99.0%
    measurement: |
      good_events: sum(rate(udify_sandbox_execution_total{status="success"}[window]))
      total_events: sum(rate(udify_sandbox_execution_total[window]))
      SLI: good_events / total_events
  
  # ===== 业务 SLO =====
  patch_quality:
    description: "Patch 质量评分"
    slo: "平均分 > 3.5/5"
    measurement: |
      avg(udify_patch_evaluation_score)
  
  user_satisfaction:
    description: "用户满意度（NPS）"
    slo: "NPS > 40"
    measurement: |
      survey_nps_score
```

### 6.2 错误预算

```python
class ErrorBudget:
    """错误预算管理"""
    
    def __init__(self, slo: float, window_days: int):
        self.slo = slo
        self.window_days = window_days
        self.total_budget = (1 - slo) * 24 * window_days  # 小时
    
    def calculate_burn_rate(self, errors_in_window: float) -> float:
        """
        计算错误预算消耗速度
        
        Burn Rate = (实际错误率) / (1 - SLO)
        
        - 1x: 正常消耗，将在窗口期末刚好用完
        - 2x: 告警线，需要关注
        - 10x: 紧急，需要立即停发或回滚
        """
        actual_error_rate = errors_in_window / self.total_budget
        theoretical_error_rate = 1 - self.slo
        
        return actual_error_rate / theoretical_error_rate
    
    def should_halt_releases(self, burn_rate: float) -> bool:
        """如果 Burn Rate > 10x，停止发布"""
        return burn_rate > 10
    
    def get_status(self, remaining_budget_hours: float) -> BudgetStatus:
        """获取预算状态"""
        if remaining_budget_hours < self.total_budget * 0.1:
            return BudgetStatus.CRITICAL  # 剩余 < 10%
        elif remaining_budget_hours < self.total_budget * 0.5:
            return BudgetStatus.WARNING  # 剩余 < 50%
        else:
            return BudgetStatus.HEALTHY
```

---

## 7. 混沌工程（Chaos Engineering）

### 7.1 实验设计

```yaml
# chaos/experiments.yml

experiments:
  # 实验 1: LLM 服务降级
  - name: "llm-provider-failure"
    description: "模拟 LLM 提供商（OpenAI）不可用，验证降级到备用提供商"
    hypothesis: "当 OpenAI 不可用时，系统自动切换到 Anthropic，用户无感知"
    scope:
      services: ["llm-agent"]
      blast_radius: "5% of traffic"
    actions:
      - type: network_blackhole
        target: "outbound to api.openai.com"
        duration: "5m"
    abort_conditions:
      - metric: "udify_llm_success_rate"
        threshold: "< 95%"
        duration: "2m"
    expected_behavior:
      - "自动检测 OpenAI 失败"
      - "切换到 Anthropic 后端"
      - "错误率保持在 < 1%"
      - "延迟增加 < 2x"

  # 实验 2: 数据库主节点故障
  - name: "postgres-primary-failover"
    description: "模拟 PostgreSQL 主节点故障，验证自动故障转移"
    hypothesis: "主节点故障后，30 秒内自动切换到备节点，无数据丢失"
    actions:
      - type: pod_failure
        target: "postgres-primary-0"
        duration: "10m"
    abort_conditions:
      - metric: "udify_api_availability"
        threshold: "< 99%"
        duration: "1m"
    expected_behavior:
      - "检测主节点故障"
      - "提升备节点为主节点"
      - "连接池重新路由"
      - "RPO = 0, RTO < 30s"

  # 实验 3: 沙箱资源耗尽
  - name: "sandbox-resource-exhaustion"
    description: "模拟恶意用户耗尽沙箱资源"
    hypothesis: "资源限制和调度器防止单个用户影响其他用户"
    actions:
      - type: cpu_stress
        target: "sandbox-executor"
        load: "100%"
        duration: "5m"
    abort_conditions:
      - metric: "udify_sandbox_queue_wait_time"
        threshold: "> 300s"
        duration: "2m"
    expected_behavior:
      - "CPU 限制生效（cgroups）"
      - "新沙箱排队等待"
      - "其他用户沙箱不受影响"
      - "自动扩展沙箱池"

  # 实验 4: 缓存失效
  - name: "cache-cascade-failure"
    description: "模拟 Redis 集群故障，验证数据库承受能力"
    hypothesis: "缓存失效后，数据库能承受 10x 查询负载"
    actions:
      - type: pod_failure
        target: "redis-cluster"
        duration: "3m"
    abort_conditions:
      - metric: "udify_db_connection_pool_usage"
        threshold: "> 90%"
        duration: "1m"
    expected_behavior:
      - "查询直接落到数据库"
      - "数据库连接池管理得当"
      - "API 响应时间增加 < 3x"
      - "无请求失败"
```

### 7.2 混沌工程平台（Litmus）

```yaml
# chaos/litmus-workflow.yml

apiVersion: argoproj.io/v1alpha1
kind: Workflow
metadata:
  name: udify-chaos-llm-failure
  namespace: litmus
spec:
  entrypoint: chaos-sequence
  templates:
    - name: chaos-sequence
      steps:
        # 1. 预检查
        - - name: pre-check
            template: pre-check
        
        # 2. 注入故障
        - - name: inject-fault
            template: network-blackhole
        
        # 3. 监控（并行）
        - - name: monitor-metrics
            template: monitor
        
        # 4. 恢复
        - - name: rollback
            template: rollback-fault
        
        # 5. 后检查
        - - name: post-check
            template: post-check
    
    - name: network-blackhole
      inputs:
        parameters:
          - name: target_service
            value: "llm-agent"
          - name: destination
            value: "api.openai.com"
          - name: duration
            value: "300"
      container:
        image: litmuschaos/go-runner:latest
        args:
          - -c
          - |
            litmus run \
              --experiment network-blackhole \
              --target ${inputs.parameters.target_service} \
              --destination ${inputs.parameters.destination} \
              --duration ${inputs.parameters.duration}
    
    - name: monitor
      container:
        image: prom/prometheus
        args:
          - -c
          - |
            while true; do
              rate=$(curl -s 'http://prometheus:9090/api/v1/query?query=udify_llm_success_rate')
              echo "Current LLM success rate: $rate"
              if (( $(echo "$rate < 0.95" | bc -l) )); then
                echo "ABORT: Success rate below threshold"
                exit 1
              fi
              sleep 10
            done
```

---

## 8. 性能剖析（Profiling）

### 8.1 持续 Profiling（Pyroscope）

```python
# udify/observability/profiling.py

import pyroscope

class ProfilingConfig:
    """Pyroscope 持续性能剖析配置"""
    
    @staticmethod
    def setup(service_name: str):
        pyroscope.configure(
            application_name=service_name,
            server_address="http://udify-pyroscope:4040",
            
            # 采样率
            sample_rate=100,  # 每秒 100 个样本
            
            # 标签
            tags={
                "service": service_name,
                "version": "2.1.0",
            },
            
            # 剖析类型
            detect_subprocesses=True,
            oncpu=True,       # CPU 时间
            alloc=True,       # 内存分配
            lock=True,        # 锁竞争
        )

# 特定代码块的细粒度剖析
@pyroscope.wrap
async def generate_transformation_plan(intent: str, cdl: CDLDocument):
    """这个函数会被自动剖析"""
    # ...

# 或者在特定区域手动标记
async def evaluate_patch(patch: CDLPatch):
    with pyroscope.tag_wrapper({"operation": "evaluate"}):
        # 剖析这段代码
        result = await run_evaluator(patch)
        return result
```

### 8.2 火焰图分析场景

| 场景 | 查找模式 | 优化方向 |
|------|---------|---------|
| **LLM 调用慢** | 宽平的 `openai.chat.completions.create` | 并行化、缓存、降级 |
| **JSON 解析慢** | `json.loads` 占用大量 CPU | 使用 orjson、流式解析 |
| **数据库慢** | `psycopg2.execute` 宽平 | 加索引、查询优化、连接池 |
| **内存泄漏** | `alloc` 火焰图中持续增长 | 检查对象引用、使用弱引用 |
| **锁竞争** | `lock` 火焰图中 `acquire` 宽平 | 减少临界区、使用无锁结构 |

---

## 9. 成本可观测性

### 9.1 成本归因

```python
class CostAttribution:
    """成本归因系统"""
    
    def track_request_cost(self, request_id: str, components: List[CostComponent]):
        """
        追踪单次请求的成本
        
        成本维度：
        - LLM API 费用
        - 计算资源（CPU/内存/时间）
        - 存储（S3 读写）
        - 网络传输
        - 数据库查询
        """
        
        total_cost = 0.0
        breakdown = {}
        
        for component in components:
            if component.type == "llm":
                # LLM 成本 = 输入 token * 输入价格 + 输出 token * 输出价格
                cost = (
                    component.prompt_tokens * component.input_price_per_1k / 1000 +
                    component.completion_tokens * component.output_price_per_1k / 1000
                )
            
            elif component.type == "compute":
                # 计算成本 = CPU 核心 * 小时 * 单价 + 内存 GB * 小时 * 单价
                cost = (
                    component.cpu_cores * component.duration_hours * 0.05 +
                    component.memory_gb * component.duration_hours * 0.01
                )
            
            elif component.type == "storage":
                # 存储成本 = GB * 单价
                cost = component.size_gb * 0.023  # S3 标准存储
            
            total_cost += cost
            breakdown[component.name] = round(cost, 6)
        
        # 记录到成本数据库
        self.record_cost(request_id, total_cost, breakdown)
        
        return CostBreakdown(total=total_cost, breakdown=breakdown)
    
    def get_daily_cost_report(self, date: datetime) -> CostReport:
        """生成每日成本报告"""
        
        return CostReport(
            date=date,
            total_cost=self.query_total(date),
            by_service=self.query_by_service(date),
            by_user_tier=self.query_by_tier(date),
            by_media_type=self.query_by_media_type(date),
            llm_cost_breakdown=self.query_llm_breakdown(date),
            anomaly=self.detect_cost_anomaly(date),
        )
```

### 9.2 成本告警

```yaml
# 成本告警规则

cost_alerts:
  - name: "Daily LLM Cost Spike"
    condition: "daily_llm_cost > $2000"
    action: "notify_platform_team"
    escalation: "if > $5000, page oncall"
  
  - name: "Per-User Cost Anomaly"
    condition: "single_user_daily_cost > $100"
    action: "flag_for_review"
    reason: "Possible abuse or infinite loop"
  
  - name: "Sandbox Compute Overrun"
    condition: "sandbox_compute_cost > $5000/day"
    action: "investigate_efficiency"
  
  - name: "Storage Growth"
    condition: "storage_cost_growth_rate > 20% MoM"
    action: "review_retention_policy"
```

---

> **"你无法优化无法测量的东西。可观测性不是监控的升级，而是对系统理解的升级——从'它坏了吗？'到'为什么这样工作？'。"**
>
> —— Udify SRE 原则
