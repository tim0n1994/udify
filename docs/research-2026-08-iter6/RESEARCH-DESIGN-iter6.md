# Udify iter6 深度研究设计

日期: 2026-08-06 | 模式: orchestrate-sol-browser（循环深度研究 → 综合 → PRD → 分布式编码 → 整合 → 验收）
基线: iter5 交付（759 passed, 2 skipped；5 模块 PR1+PR2 数据结构与逻辑已落地）
skill 版本: iter6（已修复 timing 持久化、innerText 去缩进、parseFiles END FILE、integrate 计数四个缺陷）

## 0. 为什么是 iter6（不是 iter5 的重复）

iter5 把五个信任链模块的数据结构和逻辑落地了（ReferenceSpec、ValidationReport、PhaseTiming、ScriptAnalyzer、DependencyGraph），
但 iter5 PRD 的 PR3「接入主路径」全部展期——五道闸门都停在「逻辑就绪、未接入」：

1. resolve_targets_grounded 已写但 pipeline.py 不调用 → 「第一个 Boss」改错 Hero 的根因仍在主路径上。
2. HeadlessRuntimeProbe.run_by_engine 已写但 job_runner 仍走旧的 run(graph) → 引擎分派是死代码。
3. process_intent_timed 已写但默认入口仍是 process_intent → 延迟不可观测。
4. seatbelt profile 已生成但 SandboxExecutor.execute 不实际 sandbox-exec 包裹 → 沙箱是声明而非执行。
5. graph_from_manifests 已写但 MultiModManager.install 不做依赖检查 → 冲突静默通过。

但 iter6 的研究价值不只是「把五条线接进去」——接进去是落地工作。iter6 的研究要回答的是接进去之后暴露的更深层产品硬问题，
它们决定了 Udify 能否从「组件各管一摊」走到「用户跑一个真实意图就能拿到可信结果」：

- **闭环编排（orchestration）**：五道闸门如何串成一条有状态、可回滚、可观测的 Job 主路径？
  当前 JobRunner 是线性 glue，没有「闸门失败时如何降级/重试/问用户」的编排策略。
- **前端可观测性契约**：用户在 web 工作台要看到闸门的实时状态（感知了什么、改了谁、验证结果、耗时），
  当前 API envelope 只回最终结果，没有 streaming 阶段进度。
- **意图到 Patch 的端到端正确性验证**：合成样例之外，能否用真实 RPGMV/Godot fixture 跑通
  「自然语言 → 正确接地 → 合法 Patch → 验证通过」的完整闭环？iter5 的 UdifyBench 只测了 Patch 合成，没测接地+验证。

这三个是产品级硬问题，决定了「可上线」是否成立。iter6 的研究围绕它们展开。

## 1. 六个研究主题（按产品价值 × 真实缺口排序）

### V1 — Job 闭环编排与闸门降级策略（ORCHESTRATION）
缺口：JobRunner 是线性 glue，五道闸门（接地/验证/计时/沙箱/依赖）各自独立，没有统一的「闸门失败→降级/重试/问用户」策略。
产品级闭环要求：意图接地失败时是问用户还是拒绝？验证失败时是回滚还是降级标注？沙箱拒绝时是终止还是降级到静态分析？
研究目标：闸门编排的状态机（每个闸门 pass/fail/needs-clarification 三态如何流转）、
降级决策矩阵（每个闸门失败时的 fallback 策略与产品语义）、
可观测事件流（每个闸门产什么事件、前端订阅什么）、
与现有 EventBus/JobRunner/ModJob 的精确接口、诚实的能力边界（哪些失败可自动恢复、哪些必须人工）。
接地证据：基于现有 JobRunner.process_job 的真实代码路径与 EventBus 事件类型，不能臆造编排模型。

### V2 — 流式可观测性的前后端契约（STREAMING-OBSERVABILITY）
缺口：当前 API envelope 只回最终结果，web 工作台无法看到「正在感知第 N 个文件」「正在规划」「验证失败原因」。
产品级 UX 要求用户看到 Job 的实时阶段进度。
研究目标：SSE/WebSocket 的真实选型（FastAPI StreamingResponse vs WebSocket vs polling）、
事件序列化契约（PhaseEvent 的 JSON schema 与前端 TanStack Query 订阅模型）、
前端渲染（进度条/阶段卡片/错误内联/澄清请求弹窗）、
与 PhaseTiming/ValidationReport/ClarificationRequest 的数据流对接、
回压与断连恢复（客户端断连后重连如何补齐缺失事件）、诚实的前端能力边界。
接地证据：基于现有 web/ 的 TanStack Query + Radix 技术栈与 lib/api/ 的 envelope 解码层。

### V3 — 端到端正确性验证与真实 fixture（E2E-CORRECTNESS）
缺口：iter5 的 UdifyBench 只测 Patch 合成，没测「接地+验证」的完整闭环。
产品级信任要求有一个真实 RPGMV/Godot fixture 能跑通「自然语言 → 正确接地 → 合法 Patch → 验证通过」。
研究目标：最小可信 RPGMV fixture 的真实结构（最小可运行的 Actors.json/Troops.json/Map 系统）、
端到端断言的真实设计（接地结果正确 + Patch 语法合法 + 应用后游戏可启动 + 断言通过）、
Godot fixture 的最小 headless 闭环（最小 .tscn + probe.gd）、
与 UdifyPipeline/JobRunner/UdifyBench 的接口、诚实的覆盖边界（合成 fixture vs 真实游戏）。
接地证据：RPGMV 的真实最小项目结构与 Godot headless 的真实最小场景。

### V4 — 语义提升与 LLM 降级的真实接地（SEMANTIC-LIFT-LITE）
缺口：iter5 的 SemanticLifter 产标签+证据+置信度，但 LLM 降级路径未真正测试。
「无 LLM 时语义提升能到什么程度」「有 LLM 时正确率提升多少」是产品承诺的基础。
研究目标：确定性语义提升的能力边界（哪些标签可纯规则产、哪些必须 LLM）、
LLM-assisted 提升的真实接口（提示模板 + 解析 + 校验 + 成本）、
无 Key 完全降级的诚实能力声明、与 SemanticLifter/LLMClient/LLMBudget 的精确接口、
缓存与增量（只对变更文件重新提升）、诚实的能力矩阵（规则层覆盖什么、LLM 层补什么）。
接地证据：基于现有 SemanticLifter 的真实标签体系与 RPGMV/Lua 真实内容。

### V5 — Mod 冲突的前端可视化与决策回放（CONFLICT-VISUALIZATION）
缺口：iter5 的 DependencyGraph 解决了依赖拓扑，但冲突的前端可视化（用户要决定冲突时看到什么）未研究。
产品级多 Mod 场景要求用户能看懂冲突、做决策、回放历史决策。
研究目标：ConflictReport 的前端数据契约（并排 diff / 三方合并 / 语义冲突标注）、
决策记录的回放（DecisionRecord → 前端时间线）、
用户决策的持久化（选择 A 而非 B 如何记住）、
依赖感知的回滚传播可视化（卸载 A 时 B/C 受影响的展示）、
与 web/ 审阅页与 DecisionStore 的接口、诚实的前端能力边界。
接地证据：基于现有 web/ 审阅页结构与 DecisionRecord 的真实指纹。

### V6 — 安全边界与资源限制的真实执行（SANDBOX-EXECUTION-REAL）
缺口：iter5 的 seatbelt profile 已生成但 SandboxExecutor.execute 不实际 sandbox-exec 包裹。
沙箱是声明而非执行，安全承诺不成立。
研究目标：sandbox-exec 真实包裹的执行点（subprocess.run(["sandbox-exec","-p",profile,cmd])）、
profile 的真实生成与路径白名单、资源限制（cpu/mem/time）的真实执行（ulimit vs seatbelt vs cgroups）、
无 sandbox-exec 时的诚实降级（声明 UNSANDBOXED 而非假装沙箱）、
逃逸测试用例（真实危险脚本是否被拦）、与 ToolGateway/ScriptAnalyzer 的两层防御真实联调、
诚实的安全声明（哪些威胁被拦、哪些不能被拦）。
接地证据：真实 seatbelt profile 语法与真实 sandbox-exec 行为（macOS）。

## 2. 研究纪律（继承 iter2/3/4/5，强化 iter6 timing 诚实）

- 不臆造未确认契约：真实编排状态/事件 schema/fixture 结构/沙箱执行点必须 grounding 在现有代码或官方文档。
- 真实优先：V1 基于 JobRunner 真实代码、V2 基于 web/ 真实技术栈、V3 基于真实 RPGMV/Godot 最小结构、V6 基于真实 seatbelt。
- 诚实的 fail-closed：安全/验证/接地相关宁可拒绝也不静默降级。
- 产物落盘：每轮研究写入 .ai-bridge/sol/<ID>.md，checkpoint 每轮，综合报告单独成文。
- 计时诚实可核验：iter6 的 send() 已修复 timing 持久化（recordRoundDispatch 在 saveState 前、recordDelivery 即时持久化），
  timing() 从 state.json 机器可核验。任何深度声明必须能从 state.json 重算。

## 3. 循环深度策略（R1→R4，每轮加深）

- R1（建立）：自包含专家级 prompt，覆盖范围/约束/交付物。要求真实代码路径、真实接口、可运行设计。
- R2（深挖）：批评 R1「不够深」，要求失败模式、降级策略、与现有代码的精确接口对接（指到文件/函数）。
- R3（落地）：要求完整可运行代码（拒绝伪代码）、数据契约、测试设计、与 UdifyPipeline/JobRunner/web 的接口。
- R4（综合）：决策矩阵、能力边界、PR 切分（每 PR < 400 行）、验收标准、与 iter5 PR3 carryover 的合并策略。

每轮用 deepen() 生成（priorGaps 从上一轮 gaps-remaining 取），不手写 prompt 文件。
每轮交付后 checkpoint(id) 保底，poll() 打 deliveredAt 即时持久化。
