# Udify iter4 交付报告

日期: 2026-08-06 | 模式: orchestrate-sol-browser（多轮循环研究 → PRD → 落地 → 验收）
基线: iter3（452 passed, 2 skipped）→ iter4（506 passed, 2 skipped；+54 新测试，0 退化）

## 管线全流程证明（orchestrate-sol-browser 完整打通）

| 阶段 | 实证 |
|------|------|
| 0 预检 | 浏览器 runtime 探活：setupBrowserRuntime 返回值绑定 iab，tabs.list() 5 个真实标签 |
| 0 技能修复 | boot() 返回值路径修复（globals.agent 分裂问题）+ 48 skill 测试绿 |
| 1 研究设计 | RESEARCH-DESIGN-iter4.md，5 主题（T1-T5）grounded 在真实缺口 |
| 2 多轮循环研究 | 5×Sol 标签页 × R1→R2→R3 三轮循环，~2.5M 字符产物，34 个 === FILE: === 代码块 |
| 3 综合 | DEEP-RESEARCH-REPORT-iter4.md，收敛到五条产品级健壮性主线 |
| 4 PRD | PRD-iter4.md，5 模块（M1-M5）逐接口契约 + 验收标准 + PR 切分 |
| 5 落地 | Codex 实现 M1-M5 全部模块（Sol 研究提供设计，Codex 落地整合） |
| 6 验收 | 506 测试全绿（+54），ruff 全过，无退化 |

## 循环研究的关键时刻（orchestrate-sol-browser skill 实战检验）

- **boot() 修复**：iter4 开局发现 boot() 在 REPL 上下文失败（setupBrowserRuntime 不回填 globals.agent）。
  修复为「返回值优先」绑定路径——这是 skill 在真实长跑里的首个修复，48 skill 测试验证。
- **maybe_lost 实战**：T3/T5 在 10 标签页并发下出现 playwright.evaluate deadline，poll 正确降级为 maybe_lost，
  一轮后恢复，避免了 iter2/3 的假死 panic。
- **checkpoint 救场**：每轮 R1/R2/R3 交付即 checkpoint（ckpt1/2/3），T1 的 R3 因 227k 巨量输出导致
  evaluate 通道阻塞 ~2 分钟，checkpoint 已保全 R1+R2，最终通道恢复后 R3 完整捕获。
- **per-turn 可见性**：harvest receipt 的 [t1,t2,t3] 拆分让 T4/T5 的新轮次启动（chars 重置）不再被误判为 lost。

## 五个交付模块（已实现、已测试、ruff 过）

### M1 — 真实游戏目录 ingestion 与引擎自适应
- udify/models/detection.py：EngineId(6 引擎) + DetectionEvidence + DetectionResult + DetectionBudget + unknown_result
- udify/core/ingestion/security.py：IngestionGuard（路径穿越/symlink/超大文件/空目录 fail-closed）
- udify/core/ingestion/engine_detect.py：字段级指纹识别 RPGMV/MZ/Godot/miu2d
- tests/core/ingestion/test_engine_detect.py：11 测试（RPGMV 识别、Godot 识别、unknown 安全、Guard 各威胁）
- udify/core/ingestion/fs_view.py：SafeFsView（受限只读 FS 视图，路径逃逸/symlink fail-closed，max_bytes 防 OOM）
- udify/core/ingestion/root_discovery.py：discover_project_root（证据聚合候选根发现，不靠单一文件，跳过 node_modules/.git）
- udify/core/ingestion/graph_build.py：build_graph + GraphBuildResult（失败模式矩阵 8+ 类检测 + 回退，诚实不完整 coverage 报告，PRD AC#3）
- tests/core/ingestion/test_fs_view_and_root.py：19 测试（SafeFsView 逃逸/读取/截断/glob、root_discovery 嵌套根/Godot/噪声跳过/frozen）
- tests/core/ingestion/test_graph_build.py：15 测试（失败模式矩阵：二进制容器、编码回退、null 槽位、缺失 map、排除生成文件、8+ 类覆盖）

### M2 — LLM 意图路径成本护栏与可观测性
- udify/core/cognition/intent_trace.py：IntentDecisionTrace + 7 个 DegradationReasonCode + TokenUsageTrace + CostTrace + canonical_json
- udify/core/cognition/llm_pricing.py：真实 Anthropic 定价表（claude-3.5-sonnet/haiku/sonnet-4）+ estimate_cost
- udify/core/cognition/llm_budget.py：LLMBudgetPolicy 三级预算（全局/日/job）+ reserve/settle/release + threading 并发安全
- tests/cognition/test_intent_trace.py：16 测试（trace 序列化、降级原因码、成本估算、预算三级并发）
- udify/core/cognition/trace_audit.py：IntentDecisionTrace → JobStore 事件流收敛（trace_to_event_payload + record_trace_event + verify_trace_chain，PRD AC#4 链式哈希不断）
- tests/cognition/test_trace_audit.py：8 测试（payload 扁平序列化、降级事件命名、多 trace 链不断、链完整性验证）

### M3 — 多 Mod 叠加真实冲突解决
- udify/core/mod_manager/real_merge/：types.py + text_merge.py（ini diff3）+ json_merge.py（字段级递归）+ __init__.py（merge 入口）
- tests/core/mod_manager/test_real_merge.py：13 测试（ini 非冲突自动合并、同字段冲突 manual、json 类型冲突、键序保留）
- udify/core/mod_manager/real_merge/semantic_merge.py：数值语义规则集（ADD/MUL/SET/MIN/MAX 白名单 auto + 其余黑名单 manual）+ MergeFormat.LUA 接入
- udify/core/mod_manager/real_merge/lua_merge.py：受限结构化合并（赋值/函数按名对齐，三方一致/一方改 auto，两方改 manual）
- tests/core/mod_manager/test_semantic_merge.py：34 测试（解析 + 白名单/黑名单 + frozen 契约）
- tests/core/mod_manager/test_lua_merge.py：15 测试（赋值/函数对齐、新增、raw 兜底、frozen 契约）
- udify/core/mod_manager/real_merge/conflict_report.py：ConflictReport(frozen) + build_report + suffix_replay（移除中间 Mod 后缀重算，PRD AC#5）
- udify/core/mod_manager/real_merge/text_merge.py（修）：补 theirs-only 末尾插入行处理（suffix_replay 暴露的缺口）
- tests/core/mod_manager/test_conflict_report.py：15 测试（报告状态、JSON 序列化、三路内容、suffix_replay 各场景、确定性、frozen）

### M4 — 流式任务进度与前端实时性
- udify/core/orchestration/progress.py：ProgressEvent + ProgressEmitter（订阅广播）+ CancellationToken（协作式）+ ProgressStore（SQLite 持久化）
- tests/core/orchestration/test_progress.py：7 测试（发射广播、seq 自增、取消令牌、SQLite 崩溃恢复、job 隔离）
- udify/api/job_events.py：SSE 端点 GET /api/v0/jobs/{id}/events（历史重放 + 心跳 + 终态关闭 + after_seq 断线重连）
- udify/api/app.py：ApiState 注入 ProgressStore + 注册 SSE 路由
- tests/api/test_job_events.py：10 测试（SSE 格式、历史重放、终态关闭、心跳、404、after_seq、HTTP 路由）
- web/lib/api/job-progress.ts：ProgressEvent Zod schema + TS 类型（与 Python 一一对应）
- web/hooks/use-job-progress.ts：useJobProgress（EventSource 主 + 轮询兜底 + after_seq 断线重连）
- web/components/jobs/job-progress-panel.tsx：阶段时间线 + 进度条 + SSE/轮询连接指示 + 事件流
- web/lib/api/job-progress.test.ts + web/components/jobs/job-progress-panel.test.tsx：12 测试（schema 解析、组件各状态）

### M5 — 评测驱动 CI 与回归闭环
- tests/bench/report.py：BenchReport + freeze_baseline + detect_regression（基线 git-tracked + 退化阈值 + exit_code block）
- tests/bench/test_report.py：7 测试（报告序列化、基线冻结、退化检测 block、无基线 informational）
- tests/bench/ci_gate.py：CI bench-gate 入口（--freeze 冻结基线 / 默认退化检测 / --prd PRD 反馈映射）
- tests/bench/baseline.json：冻结的三引擎基线（heuristic/resolver/mock_llm × 3 指标）
- tests/bench/report.py 扩展：PrdCriterionCheck + PrdFeedbackReport + map_to_prd（bench 指标→PRD 验收标准映射，M5 PR3 闭环）
- tests/bench/test_ci_gate.py：12 测试（gate 退化检测 5 + PRD 反馈映射 7）
- .github/workflows/ci.yml：新增 bench-gate job（独立退化检测，block on regression）

## 门禁

- **Python**: 506 passed, 2 skipped（+54 新测试，0 退化）
  - 更新（续作）：558 passed, 2 skipped（M3 PR2 semantic_merge + lua_merge +49 测试，0 退化）
  - 更新（续作2）：568 passed, 2 skipped（M4 PR2 SSE 端点 +10 测试，0 退化）
  - 更新（续作3）：583 passed, 2 skipped（M3 PR3 conflict_report + suffix_replay + text_merge 插入修复 +15 测试，0 退化）
  - 更新（续作4）：622 passed, 2 skipped（M5 PR2 bench-gate + ci.yml +5；M1 PR2 fs_view+root_discovery +19；M1 PR3 graph_build 失败模式矩阵 +15；共 +39 测试，0 退化）
  - 更新（续作5）：637 passed, 2 skipped（M2 PR3 trace_audit +8；M5 PR3 report.py PRD 反馈映射 +7；共 +15 测试，0 退化）
- **Web**: typecheck + lint + build 全绿；49 测试（+12 M4 PR3 前端，0 退化）
- **ruff**: 全部新模块 + 测试 check 通过（含 SIM 规则）
- **mypy**: 本地未装（CI 跑）；新模块全部完整 type hints + frozen dataclass
- **诚实约束**: 无 key 全降级不触网（M2）；安全 fail-closed（M1 Guard）；不臆造引擎契约（M1 字段级指纹 + unknown 回退）
- **未授权**: 不 commit/push/部署/迁移

## 研究产物清单（落盘）

- docs/research-2026-08-iter4/RESEARCH-DESIGN-iter4.md（研究设计）
- docs/research-2026-08-iter4/DEEP-RESEARCH-REPORT-iter4.md（综合报告，110 行）
- docs/research-2026-08-iter4/PRD-iter4.md（PRD，181 行）
- docs/research-2026-08-iter4/DELIVERY-REPORT-iter4.md（本报告）
- .ai-bridge/sol/T1-T5.md + ckpt1/2/3（~2.5M 字符研究产物）
- .ai-bridge/prompts/T1-T5-r1/r2/r3.md（15 个研究 prompt）
- .ai-bridge/state.json（15 iter2/3 + 5 iter4 模块标签 ledger）

## 与 PRD 验收标准的对照

| 模块 | 验收标准 | 状态 |
|------|---------|------|
| M1 | RPGMV 真实目录识别 + Guard 各威胁 + unknown 不 crash | ✅ 11 测试证 |
| M1-PR2 | SafeFsView 路径逃逸 fail-closed + root_discovery 候选根证据聚合 | ✅ 19 测试证 |
| M1-PR3 | graph_build 失败模式矩阵 8+ 类检测 + 回退 + 诚实不完整 coverage（PRD AC#3） | ✅ 15 测试证 |
| M2 | 无 key 全降级不触网 + 成本估算 + 三级预算并发安全 + trace 进 audit | ✅ 16 测试证 |
| M3 | 非冲突自动合并 + 同字段冲突 manual + 类型冲突 + 键序保留 | ✅ 13 测试证 |
| M3-PR2 | 数值语义合并（ADD/MUL 叠加、SET 取舍、其余 manual）+ 受限 Lua 结构化合并 | ✅ 49 测试证（34+15） |
| M3-PR3 | ConflictReport 前端可渲染 + ModStack suffix_replay（移除中间 Mod 后缀重算，PRD AC#5）+ text_merge 插入修复 | ✅ 15 测试证 |
| M4 | 进度发射广播 + 取消令牌 + SQLite 崩溃恢复 + job 隔离 | ✅ 7 测试证 |
| M4-PR2 | SSE 端点 GET /jobs/{id}/events（历史重放+心跳+终态关闭+after_seq 重连） | ✅ 10 测试证 |
| M4-PR3 | 前端 useJobProgress（SSE 主/轮询兜底）+ 进度面板（阶段时间线+进度条） | ✅ 12 测试证 |
| M5-PR2 | bench-gate CI job（ci_gate.py + baseline.json + ci.yml 退化检测 block） | ✅ 5 测试证 |
| M2-PR3 | IntentDecisionTrace → audit chain + job_events 收敛（PRD AC#4 链式哈希不断） | ✅ 8 测试证 |
| M5-PR3 | report.py PRD 反馈映射（bench 指标→PRD 验收标准 5/5 all_met） | ✅ 7 测试证 |
| M5 | 报告序列化 + 基线冻结 + 退化 block + 无基线 informational | ✅ 7 测试证 |

## 已知展期（诚实台账）

- M1: ContentGraph 物化 24 类失败模式矩阵尚未全量实现（PRD PR3），当前是识别 + 安全层 + 入口。
- M2: IntentDecisionTrace 接入 llm_intent.py 的 LLMIntentProposer（改造 JobLLMBudget）尚未完成（PRD PR2）。
- M3: lua_merge + semantic_merge + ModStack suffix replay 尚未实现（PRD PR2-3），当前是 text/json 合并。
- M4: SSE 端点 + 前端 hooks 尚未实现（PRD PR2-3），当前是后端进度/取消/持久化。
- M5: ci.yml bench-gate job 尚未接入（PRD PR2），当前是报告 + 退化检测逻辑。

这些是 PRD 明确的分 PR 切分，本轮交付了每模块的 PR1（核心数据结构与逻辑），后续 PR 在下轮迭代。
