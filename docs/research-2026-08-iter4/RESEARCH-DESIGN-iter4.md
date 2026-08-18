# Udify iter4 深度研究设计

日期: 2026-08-06 | 模式: orchestrate-sol-browser（多轮循环研究 → 综合 → PRD → 分布式编码 → 整合）
基线: iter3 交付（452 passed, 2 skipped）

## 0. 为什么是 iter4（不是 iter2/3 的重复）

iter2 把引擎骨架补真（语义可观测、目标解析、Playwright 探针骨架、字节稳定 Patch、Agent 循环骨架）。
iter3 把边界补真（LLM 意图真接通、JSON 跨文件 Patch、macOS seatbelt 真沙箱、30 case 评测、RuntimeProfile 探测）。

两轮的共同模式：每一块都停在「能跑通合成样例，但离真实用户五分钟闭环还有一跳」。iter4 不再补骨架，
而是把五个已经存在的能力推进到「真实游戏目录 + 真实意图 + 真实多 Mod 叠加」下的产品级健壮性，
并补齐两轮里反复出现但从未落地的横切能力（可观测性、成本护栏、流式 UX、评测驱动 CI）。

## 1. 五个研究主题（按价值 × 真实缺口排序）

### T1 — 真实游戏目录 ingestion 与引擎自适应（ENGINE-AUTO）
缺口：欠条 C 至今未清——从未处理过真实 game_root。miu2d 是浏览器引擎，但 RPG Maker MV/MZ、Godot、Unity 的
真实目录结构、资源格式、可修改契约完全未触达。iter3 的 RuntimeProfile 只扫 window 全局对象，不解决
「给一个真实解压后的游戏目录，如何自动识别引擎、定位可改资源、生成 ContentGraph」。
研究目标：跨引擎目录识别 heuristics（package.json/RPGMV.json/project.godot/*.unity）、资源定位策略、
ContentGraph 从真实文件物化的失败模式与回退、如何在不写死引擎契约的前提下做引擎自适应。

### T2 — LLM 意图路径的成本护栏与可观测性（LLM-OBS-COST）
缺口：iter3 的 LLMIntentProposer 接通了 Anthropic tool use，但 JobLLMBudget 只数调用次数，
不追踪 token / 成本 / 延迟 / 降级原因；没有结构化 trace 让用户看到「为什么这次走了启发式而不是 LLM」。
产品级需要：每 job 的 LLM 调用审计（input/output token、成本估算、延迟、降级触发条件）、
预算策略（日/job/全局三级）、可观测信封（前端能看到意图解析的决策路径与置信度）。
研究目标：token 计量与成本估算方案（不依赖 vendor SDK 私有字段）、降级决策的可解释信封、
预算护栏的工程实现（防 runaway）、与现有 audit chain 的收敛。

### T3 — 多 Mod 叠加的真实冲突解决（MODSTACK-REAL）
缺口：iter3 的 ModStack 合并检测复用 ConflictType，但只做检测不做解决；真实用户会叠加多个 Mod
（难度 Mod + 翻译 Mod + 内容 Mod），同一文件同一字段的三路合并是核心产品场景。
研究目标：三路合并算法选型（diff3 / structured merge / 语义合并）、冲突解决策略（auto / manual / semantic）、
ModStack 的依赖序与回滚传播、与 CDLPatch reverse 的关系、冲突 UI 的数据契约（前端要渲染什么）。

### T4 — 流式任务进度与前端实时性（STREAMING-UX）
缺口：当前前端 1s 轮询 GET /jobs/{id}，感知/规划阶段可能跑数分钟，用户只看到状态字符串跳动。
产品级需要：阶段内进度（感知到第 N 个文件、规划搜索到第 K 步）、SSE/WebSocket vs 轮询的真实取舍、
取消机制（用户中途想停）、长任务的 UX（预估剩余时间、可中断恢复）。
研究目标：流式进度的事件契约（per-stage progress events）、轮询→SSE 的迁移路径与回退、
取消的端到端语义（kill job + 状态机恢复点）、前端 TanStack Query 的流式适配。

### T5 — 评测驱动 CI 与回归闭环（EVAL-CI-LOOP）
缺口：iter3 的 30 case bench 是 @pytest.mark.bench，但不进 CI 默认运行，没有回归门禁、
没有 LLM 在线评测的离线 mock 策略固化、没有「评测结果→PRD 优先级」的反馈闭环。
研究目标：bench 进 CI 的 gating 策略（哪些指标做 hard gate、哪些做 informational）、
mock LLM 的稳定 fixture 策略（避免 flaky）、评测报告的产物契约、与覆盖率门禁的协同、
「能力退化」检测（A/B 基线对比，退化即 block）。

## 2. 研究纪律（继承 iter2/3，强化）

- 不臆造未确认契约：真实引擎的目录结构/全局对象/API 必须有来源（官方文档/源码/实测），不能写死猜测。
- 真实优先：T1 必须基于真实游戏目录格式（RPGMV.json/project.godot 等真实 manifest 字段）。
- 诚实的 fail-closed：安全相关（T2 成本护栏、T3 冲突）宁可拒绝也不静默错误降级。
- 产物落盘：每轮研究写入 .ai-bridge/sol/<ID>.md，综合报告单独成文。

## 3. 循环深度策略（R1→R2→R3）

- R1（建立）：自包含专家级 prompt，覆盖范围/约束/交付物。要求版本号、bundle 大小、可运行代码、具体算法。
- R2（深挖）：批评 R1「不够深」，要求失败模式、安全威胁模型、与 Udify 现有代码的精确接口对接。
- R3（落地）：要求完整可运行代码（拒伪码）、PR 级迁移计划、10 分钟可验证 demo、诚实承认最大错误。

每个主题一个 Sol 标签页，三轮循环后 Codex 综合成 DEEP-RESEARCH-REPORT-iter4.md。
