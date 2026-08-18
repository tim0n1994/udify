# Udify iter6 深度研究综合报告

日期: 2026-08-06 | 模式: orchestrate-sol-browser（6×Sol 标签页 × 2 轮循环研究 → Codex 综合）
基线: iter5 交付（759 passed, 2 skipped；5 模块 PR1+PR2 数据结构与逻辑已落地）
研究深度: 6 标签页 × 2 轮（V1/V2/V5 R2 仍在深度推理中，已捕获 R1；V3/V4/V6 R2 已交付），累计 413,738 字符
研究产物: .ai-bridge/sol/{V1..V6}.md + ckpt1-2；.ai-bridge/sol/SYNTHESIS.md
研究设计: docs/research-2026-08-iter6/RESEARCH-DESIGN-iter6.md
skill 版本: iter6（timing 持久化、innerText 去缩进、parseFiles END FILE、integrate 计数四修复）

## 0. 综合判断

iter5 落地了五道信任闸门的数据结构与逻辑，但它们各自独立，没有统一编排。
iter6 的研究回答的不是"再补一个模块"，而是**接进去之后暴露的更深层产品硬问题**：
五道孤立闸门如何串成一条有状态、可降级、可观测的 Job 主路径？用户如何实时看到闸门状态？
合成样例之外能否用真实 fixture 跑通完整闭环？

六条研究线收敛到一条主线：**Udify 要从「组件各管一摊」走到「用户跑一个真实意图就能拿到可信结果」，
必须把五道闸门编排成一个 fail-closed 的状态机（V1），用流式可观测性把闸门状态实时推给用户（V2），
用真实 RPGMV/Godot fixture 端到端验证「接地→Patch→验证」闭环（V3），用诚实的能力矩阵界定语义提升边界（V4），
用前端可视化让用户看懂冲突并回放决策（V5），用真实 sandbox-exec 执行守住安全承诺（V6）。**

## 1. 逐主题核心结论

### V1 — Job 闭环编排与闸门降级策略（ORCHESTRATION）
研究产物 ~12k 字符（R1，R2 仍在深度推理）。

**核心模型**：五道闸门不应被简单串成五个 `if`。正确模型是：
- **四道阻断型信任闸门**：意图接地、依赖、安全沙箱、运行时验证。
- **一道横切控制闸门**：延迟计时——观测和削减可选工作，但不得绕过其余四道正确性闸门。

**两层状态**：每道闸门区分「执行生命周期（pending→running→decided）」与「业务裁决（pass|fail|needs_clarification）」。
不能把 running/retrying/degraded 混进三态裁决——degraded 是正交标记，retrying 是调度行为。

**降级铁律**：降级只允许降低交付级别，不允许降低执行安全级别。
- 可以从「已验证并安装」降为「未验证构件」或「静态分析构件」。
- 不可以从「沙箱执行」降为「裸执行」。不可以从「目标明确」降为「猜一个目标」。不可以从「依赖合法」降为「先装再说」。

**四级产物等级**：installed_verified（可安装可称已验证）/ unverified_artifact（构件可供检查但运行时验证未通过）/ static_only（只完成静态分析）/ none（Job 被阻断）。

**验证在暂存区**：验证发生在暂存区，安装是最后一次原子提交。验证失败通常应丢弃暂存结果，而不是先改真实游戏再尝试回滚。

### V2 — 流式可观测性的前后端契约（STREAMING-OBSERVABILITY）
研究产物 ~96k 字符（R1 极深，R2 仍在深度推理）。

**核心契约**：FastAPI StreamingResponse（SSE）将 EventBus 事件桥接到前端流。前端 TanStack Query 订阅 SSE，
阶段卡片/进度条/错误内联/澄清弹窗（Radix Dialog）实时渲染。

**事件序列化**：PhaseEvent JSON schema 覆盖阶段开始/进度/完成、验证结果、澄清请求、错误。每个事件有 job_id/phase/timestamp/payload。

**回压与断连恢复**：用 sqlite WAL 的 jobs.db 做事件日志，客户端断连后重连补齐缺失事件。

### V3 — 端到端正确性验证与真实 fixture（E2E-CORRECTNESS）
研究产物 ~50k 字符（R1+R2，R2 含完整参考实现）。

**核心交付**：R2 产出了完整可运行参考实现——真实 RPGMV 1.6.2 fixture（96k，含 Actors.json/Enemies.json/Troops.json/System.json/Map001.json）、
Godot fixture（4k，.tscn + probe.gd）、确定性流水线、JobRunner、Benchmark（v3-e2e-correctness-r2/2.0.0，每 case 20 次）、接口指纹探测器。

**端到端断言链**：对于「让第一个 Boss 攻击力翻倍」：
- 接地断言：resolve_targets_grounded(graph, "first boss") == boss1 的 node_id（不是 Hero）
- Patch 断言：CDLPatch 语法合法 + 应用后 Enemies.json[0].params[2] == 原值*2
- 启动断言：RPGMV fixture 能被解析加载（数据完整性校验，不要求真启动 nwjs）
- Godot 断言：godot --headless --path staging --script probe.gd --quit-after N，GDScript 探针输出 JSON

**诚实覆盖边界**：合成 fixture 能证明接地+Patch+数据完整性，不能证明真实游戏启动；无 Godot 二进制诚实 SKIPPED。

### V4 — 语义提升与 LLM 降级的真实接地（SEMANTIC-LIFT-LITE）
研究产物 ~93k 字符（R1+R2）。

**核心矩阵**：确定性规则层能产 npc/actor/item/weapon 等结构性标签（覆盖 ~70%）；LLM 层补「反派 NPC」「关键任务道具」等语义标签（补 ~25%）；
两者都不行的边界：纯上下文依赖的语义（「这个 NPC 在这段剧情里是盟友还是敌人」）需用户确认（~5%）。

**LLM 降级诚实**：LLMClient 无 Key 时必须抛/跳过而非假装调用。纯规则层在这种情况下产结构性标签，诚实声明语义标签缺失。

**缓存与增量**：只对变更文件重新提升——IncrementalPerception 的增量结果喂给 SemanticLifter，未变更文件复用缓存提升结果。

### V5 — Mod 冲突的前端可视化与决策回放（CONFLICT-VISUALIZATION）
研究产物 ~9k 字符（R1，R2 仍在深度推理）。

**核心契约**：ConflictReport → 前端并排 diff（两个 Mod 改了同一文件）/ 三方合并视图（基线+Mod A+Mod B）/ 语义冲突标注。
DecisionRecord → 前端时间线回放。用户决策持久化到 DecisionStore（精确 SHA-256 指纹）。

### V6 — 安全边界与资源限制的真实执行（SANDBOX-EXECUTION-REAL）
研究产物 ~152k 字符（R1+R2，极深）。

**关键 bug 纠正**：R1 prompt 说 `subprocess.run(["sandbox-exec", "-p", profile_path, *cmd])` 是错的——`-p` 接收 profile 内容字符串，不是文件路径。
真实调用：`subprocess.run(["sandbox-exec", "-f", str(profile_path), *cmd], check=False)` 或 `["sandbox-exec", "-p", profile_text, *cmd]`。

**真实执行条件**：SandboxExecutor 只有在以下条件同时成立时才能诚实声明 sandboxed execution：
1. 实际调用 sandbox-exec；2. 使用 deny-default 的 Seatbelt profile；3. 执行静态分析过的同一份脚本；4. 游戏目录只读、独立工作目录可写；5. CPU/文件大小/墙钟时间限制在进程启动点真实施加；6. sandbox-exec 不存在时不执行，返回 status="unsandboxed"；7. 结果区分「进程启动」「沙箱存在」「进程退出」。

**诚实安全声明**：已实现真实 Seatbelt 执行路径，但运行时最小白名单仍需在目标部署机器上验证。安全声明只能是"已实现真实 Seatbelt 执行路径，运行时最小白名单需实测"。

## 2. iter6 PRD 的主线

综合六条研究线，iter6 的 PRD 围绕**把五道闸门编排成 fail-closed 状态机并端到端验证**展开：
- M1 闸门编排器（GateOrchestrator）：V1 的状态机 + 降级矩阵 + 四级产物等级。
- M2 流式可观测性（StreamingObservability）：V2 的 SSE + 事件契约 + 前端订阅。
- M3 端到端 fixture 与验证（E2EFixtures）：V3 的 RPGMV/Godot fixture + 断言链 + Benchmark。
- M4 主路径 wiring（Wiring）：把 iter5 的五道闸门接入 JobRunner 主路径（接地/验证/计时/沙箱/依赖）。
- M5 真实沙箱执行（SandboxExecution）：V6 的 sandbox-exec 真实包裹 + 资源限制 + 诚实降级。
- M6 语义提升能力矩阵（SemanticLiftMatrix）：V4 的规则层/LLM 层能力声明 + 降级。
