# Udify iter5 深度研究设计

日期: 2026-08-06 | 模式: orchestrate-sol-browser（循环深度研究 → 综合 → PRD → 分布式编码 → 整合）
基线: iter4 交付（637 passed, 2 skipped；15 PR 切片已落地）
skill 版本: iter5（已加 timing/dispatch/defect/integrate；send 打 dispatchedAt、poll 打 deliveredAt）

## 0. 为什么是 iter5（不是 iter4 的重复）

iter4 把五个能力推进到产品级健壮性（真实目录 ingestion、LLM 成本护栏、多 Mod 冲突解决、流式进度、评测 CI），
但每一块都停在「数据结构与逻辑已落地、但未接入主路径」。iter4 的诚实台账列了 5 个 wiring gap：
trace_audit 未从 llm_intent 调用、JobProgressPanel 未挂载到审阅页、SourceSpan 仍是文件级无行号、
graph_build 失败模式矩阵未全量、ModStack suffix replay 未接入。

但 wiring 不是研究课题——wiring 是落地。iter5 的研究价值在于回答 iter4 留下的三个真正的产品级硬问题，
它们决定了 Udify 能否从「单次合成样例跑通」走到「真实用户反复使用且结果可信」：

1. **意图接地（grounding）的语义正确性**：iter4 明确记录「Boss 攻击力翻倍」仍错误修改 Hero。
   这是 reference resolution 的核心缺陷——当前 target_resolver 是纯规则确定性生成，
   对「第一个 Boss」这种指代消解无能为力。这不是 wiring 问题，是语义建模的硬问题。
2. **可验证执行（verified execution）的闭环**：iter4 的 HeadlessRuntimeProbe 是骨架，
   从未在真实游戏二进制上跑过「patch → 启动 → 状态读取 → 报错捕获」的完整闭环。
   一个无法验证结果的自动修改系统在产品上等于不可用。
3. **端到端延迟的真实分布与优化**：iter4 设计了可观测性但从未测量过真实延迟分布。
   产品级「五分钟闭环」需要知道瓶颈在哪（感知？规划？LLM？Patch 应用？）。

## 1. 五个研究主题（按产品价值 × 真实缺口排序）

### U1 — 指代消解与意图接地（INTENT-GROUNDING）
缺口：「让第一个 Boss 更难」改错对象是致命缺陷。当前 target_resolver 基于 SemanticView 字段确定性过滤，
对「第一个/最强的/离玩家最近的」这类指代无能为力。
研究目标：指代消解（coreference）在游戏内容场景的算法选型（规则+约束满足 vs LLM-assisted vs 图查询）、
「第一个 Boss」的真实消解路径（ContentGraph 拓扑序 vs SpatialGraph 距离 vs 数值排序）、
消歧失败时的可解释降级（向用户问澄清 vs 启发式猜测 vs 拒绝）、
与现有 StructuredIntent/Constraint/target_resolver 的精确接口对接、诚实的能力边界（什么能消解、什么不能）。
接地证据：必须基于真实 RPGMV Actors.json/Enemies.json 结构（敌人出场序、属性字段、地图关联），
不能基于臆造的游戏模型。

### U2 — 可验证执行闭环（VERIFIED-EXECUTION）
缺口：HeadlessRuntimeProbe 探针骨架存在但从未在真实游戏上跑通「应用 patch → headless 启动 → 
读全局状态 → 捕获报错 → 生成验证报告」的完整闭环。没有验证的自动修改不可信。
研究目标：headless 启动的真实方案（RPGMV 用 nwjs/electron headless vs Godot --headless vs Unity -batchmode）、
状态读取的真实技术（注入探针脚本读 window 对象 vs 存档文件解析 vs console 日志解析）、
报错捕获（stderr/stdout 正则 vs crash dump vs exit code）、
patch 应用的原子性（失败回滚）、验证报告的数据契约（前端渲染什么）、
与 SandboxExecutor/VirtualFileSystem/CDLPatch 的接口、诚实的引擎覆盖边界（哪些引擎能 headless 验证、哪些不能）。
接地证据：RPGMV 的真实启动参数、Godot headless 的真实 CLI、真实报错样例。

### U3 — 端到端延迟建模与优化（LATENCY-PROFILE）
缺口：从未测量过真实端到端延迟分布。产品级「五分钟闭环」需要知道瓶颈。
研究目标：各阶段延迟的真实建模（IncrementalPerception N 文件扫描 vs MCTS K 步搜索 vs LLM 调用 vs Patch 应用）、
并行化机会（哪些阶段可并行）、增量感知的真实收益（只扫变更文件）、
MCTS 搜索的早停策略（value 收敛 vs 预算耗尽）、
缓存策略（ContentGraph 缓存 vs 感知结果缓存 vs LLM 响应缓存）、
LLM 降级的延迟收益（启发式 value function vs LLM value function 的真实时间差）、
预算护栏与延迟的权衡（硬停 vs 软降级）。
接地证据：基于真实算法复杂度 + 真实 LLM 延迟（Anthropic API P50/P95），不能臆造毫秒数。

### U4 — 安全沙箱的真实隔离边界（SANDBOX-REAL）
缺口：SandboxExecutor 存在但 macOS seatbelt/gVisor 方案是预留，从未验证真实隔离强度。
真实 Mod 可能含恶意脚本（infinite loop、文件系统访问、网络外联）。
研究目标：macOS seatbelt-sandbox-init 的真实 profile（允许什么、拒绝什么）、
gVisor 容器的真实配置（runsc + Docker）、
脚本静态分析拦截危险 API（os.execute/io.popen/loadstring/ffi）的真实清单、
资源限制（CPU/内存/时间/磁盘）的真实执行点、
逃逸路径分析（沙箱能做什么、不能做什么）、
与现有 ToolGateway/Sanitizer 的接口、诚实的隔离强度声明（哪些威胁能拦、哪些不能）。
接地证据：真实 seatbell profile 语法、真实 Lua/JS 危险 API、真实逃逸案例。

### U5 — 多 Mod 叠加的依赖图与冲突可视化（MODSTACK-DEPENDENCY）
缺口：iter4 的 ModStack suffix replay 解决了「移除中间 Mod」的算术，但未建模 Mod 间的依赖关系
（Mod B 依赖 Mod A 的存在）和冲突的前端可视化（用户要决定冲突时看到什么）。
研究目标：Mod 依赖图的建模（DAG + 拓扑序安装/卸载）、
依赖冲突检测（循环依赖、缺失依赖、版本冲突）、
冲突解决的前端数据契约（ConflictReport → 前端渲染：并排 diff、三方合并视图、语义冲突标注、决策记录）、
依赖感知的回滚传播（卸载 A 时 B/C 的处理）、
与现有 ModStack/ModManifest/real_merge 的接口、诚实的能力边界。
接地证据：真实 Mod 依赖场景（翻译 Mod 依赖基础 Mod、内容 Mod 与难度 Mod 叠加）。

## 2. 研究纪律（继承 iter2/3/4，强化）

- 不臆造未确认契约：真实引擎/全局对象/API/延迟/沙箱必须 grounding 在官方文档或实测，不能写死猜测。
- 真实优先：U1 基于 RPGMV Actors.json 真实结构、U2 基于 nwjs/Godot headless 真实 CLI、U3 基于真实 LLM 延迟、U4 基于 seatbelt 真实 profile。
- 诚实的 fail-closed：安全相关（U4 沙箱、U2 执行验证、U3 预算）宁可拒绝也不静默降级。
- 产物落盘：每轮研究写入 .ai-bridge/sol/<ID>.md，checkpoint 每轮，综合报告单独成文。
- 计时可核验：iter5 的 send() 打 dispatchedAt、poll() 打 deliveredAt，timing() 机器可核验每轮深度。

## 3. 循环深度策略（R1→R4，每轮加深）

- R1（建立）：自包含专家级 prompt，覆盖范围/约束/交付物。要求版本号、真实 CLI/字段、可运行代码、具体算法。
- R2（深挖）：批评 R1「不够深」，要求失败模式、安全威胁模型、与 Udify 现有代码的精确接口对接（指到文件/函数）。
- R3（落地）：要求完整可运行代码（拒伪码）、PR 级迁移计划、10 分钟可验证 demo、诚实承认最大错误。
- R4（综合）：一页纸决策矩阵、top-3 行动项、矛盾裁决、与 iter4 已落地模块的精确关系。

每个主题一个 Sol 标签页，用 deepen() 生成追问 prompt（不手写），四轮循环后 Codex 综合成报告。
