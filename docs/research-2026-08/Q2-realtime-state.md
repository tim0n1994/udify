# Q2：实时通信与状态同步深度研究

## 项目背景

Udify 的 ModJob 状态机通过 SQLite (WAL) 持久化，前端通过 1s 轮询 GET /jobs/{id} 获取状态更新。当前架构是 FastAPI + uvicorn (127.0.0.1:8765) 后端，Next.js 15 前端，TanStack Query v5 管理服务端状态。

Job 状态流转：created → perceiving → planning → awaiting_review → applying → validating → packaging → completed。某些阶段（如感知大游戏目录、运行时探针）可能耗时数分钟。当前 1s 轮询在这些场景下既浪费带宽又有感知延迟。

迭代计划 ADR-v3-008 写的是"轮询先行，SSE 推迟到轮询被证明不够"。现在是评估升级时机的时刻。

## 需要深度研究的问题

1. **轮询 vs SSE vs WebSocket 选型决策框架**：针对"本地单用户、单后端、Job 长任务进度推送"场景，系统对比三种方案的：
   - 延迟、资源消耗、实现复杂度
   - FastAPI 对 SSE/WebSocket 的原生支持成熟度
   - 前端 TanStack Query 与 SSE 的集成模式（现有 queryCache 与流式更新的协调）
   - 断线重连与状态恢复语义

2. **成熟开源方案调研**：
   - 后端：FastAPI StreamingResponse (SSE) vs WebSocket、sse-starlette、asyncio patterns
   - 前端：EventSource API vs WebSocket 客户端、TanStack Query 的 streaming integration
   - 事件溯源与状态恢复：如何让 SSE 断线后从 last-event-id 恢复而不丢状态
   - 已有 job_events 表（append-only 事件流）如何直接映射为 SSE 事件流

3. **乐观更新与状态一致性**：
   - 用户批准/拒绝操作后，前端如何做乐观更新同时等待后端确认
   - Job 状态机迁移失败时的回滚通知与 UI 状态修正
   - 多个面板（时间线、diff、风险）共享同一 Job 状态时的同步策略

4. **本地开发体验**：
   - SSE 在 Next.js 15 App Router 下的 Dev 体验（HMR 不断连）
   - uvicorn 单 worker 下 asyncio SSE 的并发模型（多 job 并行时的事件分发）
   - 与现有 healthz/轮询 fallback 的共存策略（渐进迁移而非一刀切）

## 交付物

- 三方案对比决策矩阵（加权评分，针对 Udify 场景量化）
- 推荐 SSE 实现方案（FastAPI 后端 + Next.js 前端的完整代码骨架）
- 从现有轮询迁移的渐进策略（兼容期设计）
- job_events 表 → SSE 事件流的具体映射方案
- 性能基准：轮询 vs SSE 在模拟 100 个 Job 并行时的 CPU/内存/带宽对比

## 约束

- 本地单用户，127.0.0.1 绑定，不做云部署
- 后端是 FastAPI + uvicorn + SQLite WAL，不换框架
- 前端是 Next.js 15 + TanStack Query v5，不换状态库
- 现有 1s 轮询必须保留为 fallback（无 SSE 支持时不崩溃）
