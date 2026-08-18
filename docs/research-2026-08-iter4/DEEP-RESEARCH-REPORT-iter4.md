# Udify iter4 深度研究综合报告

日期: 2026-08-06 | 模式: orchestrate-sol-browser（5×Sol 标签页 × 3 轮循环研究 → Codex 综合）
基线: iter3 交付（452 passed, 2 skipped）
研究产物: .ai-bridge/sol/{T1-ENGINE-AUTO,T2-LLM-OBS-COST,T3-MODSTACK-REAL,T4-STREAMING-UX,T5-EVAL-CI-LOOP}.md + 3 个 ckpt（合计 ~2.5M 字符）
源码包: udify-src-iter4.zip（40 文件，154KB）
研究设计: docs/research-2026-08-iter4/RESEARCH-DESIGN-iter4.md

## 0. 综合判断

iter2 补了引擎骨架，iter3 补了边界真接通。iter4 不再补骨架，而是把五个已存在的能力推进到产品级健壮性，并补齐两轮里反复出现但从未落地的横切能力。三轮循环研究（R1 建立 → R2 深挖失败模式与威胁模型 → R3 落地代码）收敛到五条主线，每条都产出了完整的文件级代码交付物（共 34 个 === FILE: === 块）。

**核心收敛**：iter4 的五条主线不是五个独立功能，而是一个闭环——真实目录 ingestion（T1）是入口，LLM 可观测性（T2）是意图层的信任地基，多 Mod 冲突解决（T3）是 Mod 叠加场景的产品护城河，流式进度（T4）是长任务的用户体验，评测 CI（T5）是回归闭环。它们共同把 Udify 从「合成样例能跑」推进到「真实用户五分钟闭环 + 能力不退化」。

## 1. 逐主题核心结论

### T1 — 真实游戏目录 ingestion 与引擎自适应（ENGINE-AUTO）
研究产物 ~280k 字符，7 个文件级交付物。

**核心架构**：候选项目根发现（Safe FS Index）→ 字段级引擎指纹（不靠单一文件）→ 版本化 Detector V2 → ContentGraph 物化（24 类失败模式矩阵）→ 事务化 Patch → 显式不完整性诊断。

**关键技术决策**：
- 引擎识别用「确凿指纹文件 + 关键字段」而非单一文件。RPG Maker MV 的 package.json（chgamename/companyName）+ www/data/Actors.json/Enemies.json 真实 JSON 结构；Godot 的 project.godot 真实 section（application/config/name）；Unity 的 .meta + SerializedFile。
- 独立 IngestionGuard 安全层：路径穿越、symlink loop、超大文件 OOM、二进制误解析、zip bomb、恶意脚本注入——每个威胁带缓解。
- ContentGraph 物化 24 类失败模式（引擎 × 文件类型 × 失败 × 处理矩阵），区分 syntactically_writable 与 semantically_verified。
- 诚实约束：源项目支持 ≠ 商业游戏 Mod 支持；ContentGraph 节点允许引用 adapter 私有 lossless document model，不强制图承载全部格式细节。

**交付文件**：udify/models/detection.py、udify/models/graph_build.py、udify/core/ingestion/{security,fs_view,root_discovery,__init__}.py、udify/core/perception/engine_detector.py（增强）。

### T2 — LLM 意图路径的成本护栏与可观测性（LLM-OBS-COST）
研究产物 ~250k 字符，5 个文件级交付物。

**核心架构**：token 计量（真实 Anthropic usage 字段）→ 成本估算（真实模型定价）→ IntentDecisionTrace（可解释降级信封）→ 三级预算护栏（全局/日/job，并发安全）→ 与 audit chain 收敛。

**关键技术决策**：
- token 计量用 response.usage 真实字段（input_tokens/output_tokens/cache_creation_input_tokens/cache_read_input_tokens），tool use 的 tool input 计入 input_tokens。成本按真实模型定价换算（标注来源日期），无 vendor 私有字段依赖时回退 tiktoken 估算。
- IntentDecisionTrace（frozen dataclass + to_dict + JSON schema）：决策路径、置信度、降级原因码（NO_KEY/BUDGET_EXHAUSTED/TIMEOUT/VALIDATION_FAILED/MALFORMED_RESPONSE/NETWORK_ERROR/RATE_LIMIT，每个带 retryable + suggested_action）。进 sqlite job_events 表 + 进 audit chain 链式哈希。
- 预算护栏并发安全：sqlite 事务原子检查（单用户但 JobRunner 多 job 后台线程）。runaway 场景（单 job 疯狂重试）硬停。
- 威胁模型：恶意/失控 LLM 输出（超长响应、infinite loop、tool abuse）被护栏拦截。

**交付文件**：udify/core/cognition/{intent_trace,llm_pricing,llm_budget,llm_intent_observed}.py、udify/core/tool_gateway/audit.py（增强）。

### T3 — 多 Mod 叠加的真实冲突解决（MODSTACK-REAL）
研究产物 ~230k 字符，8 个文件级交付物。

**核心架构**：语义操作 → 三路合并（按格式分派）→ 冲突分类（auto/manual/semantic）→ ConflictReport → ModStack suffix replay（中间层移除重算）。

**关键技术决策**：
- 按格式分派合并：ini 用行级 diff3（difflib.SequenceMatcher），json 用字段级递归 structured merge（保留键序），lua 用受限 AST 合并。每种给接近可运行的算法。
- semantic 合并规则集：数值语义可自动合并（加法叠加、乘法取大、min/max）有白名单；类型冲突、语义不明进黑名单（必须 manual）。明确安全边界。
- ModStack suffix replay：栈 [base, A, B, C]，移除 B 后 C 的 patch 基于重算的 A' 重新生成。处理 base 已变（用户手动改原文件）的本地漂移。
- ConflictReport（Python dataclass + JSON + 前端 TS 一一对应）：文件级/字段级/语义级冲突，每方内容、SourceSpan、建议解决、是否 auto-resolvable。恶意 Mod 检测与拒绝边界。

**交付文件**：udify/core/mod_manager/real_merge/{__init__,compat,conflict_report,text_merge,json_merge,lua_merge,semantic_merge}.py。

### T4 — 流式任务进度与前端实时性（STREAMING-UX）
研究产物 ~190k 字符，13 个文件级交付物（前后端全栈）。

**核心架构**：ProgressEvent（从 JobRunner 步进产生）→ SQLite 进度账本 → FastAPI SSE 端点 → TanStack Query 5 流式 hook → React 19 长任务 UI。

**关键技术决策**：
- ProgressEvent 基于 Miu2dClosedLoop/JobRunner 真实步进边界（perceive/plan/validate），JobRunner 注入 progress callback。SQLite progress_store 持久化（崩溃可恢复）。
- SSE 用 FastAPI StreamingResponse（async generator + 心跳 + 断线检测），回退轮询。单 worker uvicorn 下 SSE 的真实限制明确。
- 取消端到端：threading.Event（JobRunner 是后台线程现状）→ 状态机迁移 → VFS 补偿回滚 → 恢复点记录。不承诺强制 kill 无法合作的线程，明确需要子进程边界。
- 前端 useJobProgress hook（EventSource + TanStack Query 5），与 useJobs 轮询共存（SSE 主、轮询兜底）。React 19 并发渲染对流式更新的适配。
- 威胁模型：失控 SSE 连接（不关闭、占资源、半开）治理。

**交付文件**：udify/core/orchestration/{progress,cancellation,progress_store,job_runtime}.py、udify/api/{job_events,install_streaming,demo_streaming_app}.py、web/lib/api/job-progress.ts、web/hooks/use-job-progress.ts、web/components/jobs/job-progress-panel.tsx、tests/core/orchestration/test_progress_runtime.py、tests/api/test_job_events.py。

### T5 — 评测驱动 CI 与回归闭环（EVAL-CI-LOOP）
研究产物 ~150k 字符，CI 参考实现 + fixture 方案。

**核心架构**：确定性离线 fixture → 基线冻结（git-tracked JSON）→ 逐 case 退化检测 → CI gating（hard gate + informational）→ PRD 反馈。

**关键技术决策**：
- CI gating 分层：pytest marker 分 default（必须绿）、bench-gate（hard gate，target_precision 等不得低于基线）、bench-info（informational，延迟）。覆盖率门禁 70% 与 bench 门禁并存于同一 GitHub Actions workflow。
- mock LLM 确定性：录制真实响应成 cassette（VCR 风格）replay，或手写 fixture，避免 flaky。在线 LLM 评测与离线 mock 用环境变量 + marker 隔离不互染。
- 退化检测：基线 JSON git-tracked（case_id/metric/value/timestamp/commit），对比算法指标 delta + 阈值 + 小样本显著性，退化即 block PR（exit code + PR comment）。
- flaky 治理：同一 case 多跑结果差异检测；基线漂移（模型升级）识别与更新流程。
- 评测报告 schema：case 级结果 + 聚合统计 + PRD 反馈映射字段。

## 2. 跨主题收敛

A. **产品闭环而非新功能**：T1（真实目录入口）、T2（意图信任地基）、T3（Mod 叠加护城河）、T4（长任务体验）、T5（回归闭环）共同把五分钟北极星坐实。
B. **诚实契约持续**：T1 不臆造引擎契约（用字段级指纹 + 显式不完整性），T3 不臆造合并语义（白名单/黑名单明确），与 iter2/3 纪律一致。
C. **安全 fail-closed 分层**：T1 ingestion 安全（IngestionGuard）、T2 成本护栏（runaway 硬停）、T3 恶意 Mod 拒绝——能力降级 OK，安全降级不 OK。
D. **全栈覆盖**：T4 是唯一前后端全栈主题（Python SSE + TS hook + React UI），证明管线能交付跨栈一致性。

## 3. 与 iter3 现状的 diff

| 域 | iter3 | iter4 目标 | 触达 |
|----|-------|-----------|------|
| 目录 ingestion | 合成 ini 样例 | 真实多引擎目录 + 安全 ingestion | udify/core/ingestion/(新), engine_detector.py(改), models/detection.py(新) |
| LLM 可观测 | JobLLMBudget 数次数 | token/成本/降级 trace + 三级预算 | cognition/{intent_trace,llm_pricing,llm_budget}.py(新), llm_intent.py(改) |
| 多 Mod | ConflictType 检测 | 三路合并解决 + semantic + suffix replay | mod_manager/real_merge/(新) |
| 任务进度 | 1s 轮询状态串 | SSE + per-stage progress + 取消 | orchestration/{progress,cancellation}.py(新), api/job_events.py(新), web hooks/components(新) |
| 评测 CI | @bench 不进 CI | bench-gate 进 CI + 退化 block | tests/bench(改), .github/workflows(改), fixture(新) |

## 4. 风险与红线

- T1 引擎契约：用字段级指纹 + RuntimeProfile 探测，不写死猜测；真实游戏目录测试样本可能过于干净（官方 demo 缺插件冲突/损坏引用），验收需加混合版本/损坏样本。
- T2 成本估算：定价随时间变，必须标注来源日期并设计更新流程。
- T3 semantic 合并：安全边界必须可执行，宁可 manual 也不静默错误自动合并。
- T4 SSE：单 worker uvicorn 限制明确，回退轮询必须可用。
- T5 bench-gate：小样本显著性，避免噪声误报 block。
- 全程不 commit/push/部署/迁移（未授权）。

## 5. 下一步

本报告 → PRD-iter4.md（逐模块接口 + 验收标准）→ 分布式 Sol 编码 → Codex 整合 → 验收。
