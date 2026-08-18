# Q4：基础设施与可观测性深度研究

## 项目背景

Udify 的 ModJob 编排使用 stdlib sqlite3 (WAL) + 文件工件，JobStore 通过单连接 RLock 保证并发安全。后端是 FastAPI + uvicorn (127.0.0.1:8765)，单用户免认证。结构化日志是 stdlib logging + JSON formatter。可观测层只有 job_events 表（append-only 事件流）和 JSON 日志。

迭代计划明确不做 Temporal、OTel、Prometheus、Grafana（红线 P2）。但随着 Job 复杂度增长（真实游戏目录、运行时探针、多 Mod 组合），需要更扎实的基础设施。

## 需要深度研究的问题

1. **Job 执行引擎选型**：
   - 当前是自研步进 JobRunner + SQLite checkpoint。调研何时该升级到成熟工作流引擎
   - 成熟开源对比：Temporal、Prefect、Celery、Dramatiq、RQ、arq、taskiq、Liteflow
   - 针对本地单用户场景的轻量级方案（不依赖外部 broker/数据库）
   - 崩溃恢复与幂等性的工业级实现模式（checkpoint + replay 的最佳实践）
   - 现有 SQLite job_events 表能否复用为事件溯源的 event store

2. **持久化与状态恢复**：
   - SQLite WAL 在高频写入下的性能特性与调优（page_size、cache_size、wal_autocheckpoint）
   - 工件文件（graph.json/patch.json/vfs 快照/package.zip）的存储组织与垃圾回收
   - 数据迁移策略（schema_version 表 + 手管迁移 vs Alembic）
   - 审计链（tool_gateway audit chain 链式哈希 + audit_log）的收敛与统一

3. **可观测性栈选型**：
   - 结构化日志：stdlib logging + structlog vs loguru vs picologging
   - 分布式追踪：OpenTelemetry SDK 的最小接入（不部署 Collector，只生成 trace）
   - Metrics：Prometheus client 的 exposition（本地 :9090 /metrics，不需要 Prometheus server）
   - 事件流可视化：job_events 表如何生成可读的执行时间线

4. **进程管理与健康检查**：
   - uvicorn 单 worker vs 多 worker 在本地模式下的取舍
   - 后台线程驱动的 Job 状态机：如何优雅关闭（等待 in-flight job、flush checkpoint）
   - healthz → readinessz → livez 的分层健康检查
   - 端口冲突检测与自动避让

5. **沙箱执行安全**：
   - 当前 SandboxExecutor.validate_script_safety 的能力边界
   - gVisor/Firecracker 在 macOS 本地模式的可行性（或替代方案）
   - Tool Gateway 的路径 allowlist 与 OPA 策略引擎集成的成熟度

## 交付物

- 工作流引擎选型决策矩阵（本地单用户场景加权评分）
- 持久化层调优指南（SQLite WAL 配置、索引策略、工件 GC 方案）
- 最小可观测性栈推荐（日志+追踪+metrics 的具体库与配置）
- 优雅关闭与崩溃恢复的完整状态机设计
- 沙箱安全评估报告（macOS 本地可行方案）

## 约束

- 本地单用户，127.0.0.1 绑定，不做云部署或多用户
- 红线：本轮不引入 Temporal、Neo4j、Redis（但需评估何时该引入）
- 优先 stdlib + 成熟轻量开源，不引入重量级依赖
- Python 3.12+ / FastAPI / mypy strict 兼容
- 现有 399 测试不可回归
