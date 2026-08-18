# Udify iter5 深度研究综合报告

日期: 2026-08-06 | 模式: orchestrate-sol-browser（5×Sol 标签页 × 4 轮循环研究 → Codex 综合）
基线: iter4 交付（637 passed, 2 skipped）
研究深度: 5 标签页 × 4 轮（U3/U5 各 3 轮），机器可核验累计思考时间 9h46m，产物 439,000 字符
研究产物: .ai-bridge/sol/{U1-INTENT-GROUNDING,U2-VERIFIED-EXECUTION,U3-LATENCY-PROFILE,U4-SANDBOX-REAL,U5-MODSTACK-DEPENDENCY}.md + ckpt1-4
研究设计: docs/research-2026-08-iter5/RESEARCH-DESIGN-iter5.md

## 0. 综合判断

iter4 把五个能力推进到产品级健壮性，但每一块都停在「数据结构已落地、未接入主路径」。iter5 的研究回答的不是"再补一个模块"，
而是 iter4 留下的三个真正决定产品可信度的硬问题：意图能否正确接地、修改能否被验证、延迟能否被承诺。五轮循环研究（R1 建立 →
R2 失败模式与威胁模型 → R3 落地代码 → R4 综合决策矩阵）收敛到一条主线：**Udify 要从「能跑通合成样例」走到「真实用户反复使用且结果可信」，
必须补齐三道信任闸门——语义正确的意图接地（U1）、可验证的执行闭环（U2）、可测量的延迟承诺（U3），并用真实沙箱边界（U4）和
依赖感知的 Mod 管理（U5）守住安全与多 Mod 叠加的产品场景。**

五条主线的关系不是五个独立功能，而是一个信任链：U1 保证"改对对象"，U2 保证"改完能验证结果"，U3 保证"改得够快"，
U4 保证"改的过程不失控"，U5 保证"多个改能共存"。任何一环缺失，产品承诺都不成立。

## 1. 逐主题核心结论

### U1 — 指代消解与意图接地（INTENT-GROUNDING）
研究产物 ~60k 字符，4 轮。

**核心诊断**：iter4 的"第一个 Boss 改错 Hero"不是排序能力不足，而是**缺少顺序域（order domain）**。
target_resolver 把 `first(filter(all_nodes, is_boss=True))` 错误退化成 `filter(all_nodes, is_boss=True)`——
没有"第一个"这个序数指代的概念。

**关键技术决策**：
- **A 路径（确定性消解）作为权威执行层**：ReferenceSpec（entity_type=boss, operator=ordinal, ordinal=1, order_domain=first_encounter）
  → SemanticView 硬过滤 → 按来源顺序（RPGMV Enemies.json 数组下标 / Troops.json.members / Map 事件首次遭遇序）排序 → 唯一性检查。
- **C 路径（CSP 约束求解）作为唯一性检测层**：指代对象=变量，候选节点=定义域，序数/类别/属性/空间/上下文=约束，只接受唯一解。
- **B 路径（LLM）只解释语言**：可以从文本提取 entity=boss/ordinal=1/suggested_order_domain，但绝不直接选中节点；
  规则层重新验证候选。无 Key 完全跳过。
- **消歧失败 → ClarificationRequest**：唯一解失败或证据不足时，产 ClarificationRequest（让前端问用户）。
  绝不静默猜错。

**诚实能力边界**：ContentGraph 的数组顺序 ≠ 游玩顺序；"剧情顺序"无法凭空推断，必须问用户。
形容词指代（"最强的"）依赖语义定义（max(attack) vs max(hp)）；空间指代（"最近的"）依赖 SpatialGraph（当前 ContentGraph 无空间信息，需补建）。

### U2 — 可验证执行闘环（VERIFIED-EXECUTION）
研究产物 ~74k 字符，4 轮。

**核心架构**：预览 → 隔离物化（临时副本）→ 探针执行 → 三层判定 → 生成报告 → 发布或销毁。
不修改真实项目再逆向回滚。

**关键技术决策（三引擎诚实分级）**：
- **Godot 4**：原生严格 headless（`godot --headless --path /staging --script probe.gd --quit-after`）。
  GDScript 探针读节点/资源/Autoload/运行时属性。NATIVE_HEADLESS，第一优先完整闭环。
- **RPGMV / NW.js**：`nw --remote-debugging-port=9222 /staging/game` + CDP 注入 JS 读 `$dataEnemies/$gameActors`。
  NW.js 无官方原生 --headless 承诺 → 称 AUTOMATED_NON_HEADLESS（隔离桌面自动化验证）。
- **Unity**：Editor `-batchmode -executeMethod` 可读序列化数据；Standalone Player 需预植入 Udify Probe。
  商业未植入 Player 只能观察进程/日志。INSTRUMENTED_PLAYER_ONLY。

**验证状态语义**：`ValidationStatus.PASSED` 必须同时满足：进程正常退出 + 无未处理运行时异常 + 所有必需语义断言有可信观测值且通过。
"成功启动"绝不等于"修改已验证"。三层判定：进程崩溃（exit code + stderr）/ 运行时异常（console）/ 静默逻辑错误（数值断言）。

**诚实引擎覆盖边界**：商业加密游戏不能自动获得内部状态；GPU/真实音频/视觉行为不能由 headless 证明。

### U3 — 端到端延迟建模与优化（LATENCY-PROFILE）
研究产物 ~39k 字符，3 轮。

**核心诚实结论**：当前**不能证明** Udify 满足"五分钟闭环"。原因不是已知性能差，而是：
(1) 没有端到端统一时钟和分阶段分布数据；(2) EnhancedValidator/ConflictDetector 内部算法未提供，存在未建模黑箱；
(3) 增量感知"只处理变更文件"≠"检测变更只读取变更文件"（无可靠变更日志时仍可能全量哈希）。

**关键技术决策**：
- **延迟预算公式**：`T_total = ΣT_mandatory + ΣT_optional`。安全、冲突检测、验证、最终应用=mandatory（不可降级）；
  LLM 调用、额外 MCTS rollout=optional（可因时间/成本预算降级）。
- **MCTS 早停必须有可证明收敛**：用带置信区间的独立验证样本，把"已收敛"和"预算耗尽"分开报告。
  "连续 N 步 value 方差小"不能证明收敛。
- **缓存正确失效**：ContentGraph 缓存键=目录内容 hash，文件变更必须失效。增量感知收益=只处理 ΔF 变更文件，
  但变更检测本身可能需全量 hash。

**诚实边界**：在"只使用 prompt 上下文"约束下不能填入 LLM 延迟数值；落地时必须真实测量（采集 exact-model Anthropic traces）
才能做任何 SLO 承诺。建议补 Instrumentation 层（统一计时 + 分阶段记录）作为落地前提。

### U4 — 安全沙箱的真实隔离边界（SANDBOX-REAL）
研究产物 ~200k 字符，4 轮。

**核心诚实结论**：无法诚实交付一个"公开规范支持、已验证可移植"的 SBPL (version 3) profile。
sandbox-exec/sandbox_init 已弃用；SBPL 是 Apple 私有接口，Apple 无公开完整语言规范。Chromium 实际使用的仍是 (version 1) (deny default)。

**关键技术决策（两层防御）**：
- **第一层（静态）**：InputSanitizer → AST 静态分析/validate_script_safety → 拒绝已知危险 API
  （Lua: os.execute/os.exit/io.popen/loadstring/load/ffi.C；JS: require('child_process')/require('fs')/eval/Function）。
- **第二层（运行时兜底）**：ToolGateway policy 要求具体隔离能力 → Seatbelt（version 1 真实模板 + close_fds=True，
  仅临时目录可写）或 gVisor（仅 Linux，runsc 截获系统调用）。
- **资源限制真实执行点**：CPU（ulimit/cgroups）、内存（ulimit -v）、时间（timeout + 进程组 kill）、磁盘（quota）。

**诚实逃逸边界**：静态分析不是沙箱；沙箱不能替代静态拒绝。Seatbelt 能拦文件系统/fork，不能拦内存破坏/内核漏洞。
gVisor 能拦系统调用，不能消除 Sentry/Goofy/宿主侧信道。任一层不可用 → 拒绝执行（fail-closed）。

### U5 — 多 Mod 叠加的依赖图与冲突可视化（MODSTACK-DEPENDENCY）
研究产物 ~65k 字符，3 轮。

**核心架构**：拆成两个互补层次——DependencyGraph 管"哪些 Mod 可同时存在、安装/卸载顺序合法"；
ModStack 管"合法 Mod 集合按什么线性顺序叠加、变更后从哪里 suffix replay"。DAG 只给偏序，互不依赖的 Mod 仍可能改同一文件。

**关键技术决策**：
- **DependencyGraph（DAG）**：ModManifest 加 `depends_on`（带默认值，向后兼容）。核心不变量：
  每 mod_id 最多一个版本；安装序保证依赖先于依赖者；卸载序保证依赖者先于被依赖；有效集合始终无环/无缺失/版本约束成立。
- **依赖冲突检测三类**：循环依赖（拓扑排序检测环）、缺失依赖（依赖未安装）、版本冲突（requires >=1.0 装了 0.9）。每类用户可读错误。
- **依赖感知回滚传播**：卸载 A 时依赖它的 B/C 处理（级联卸载 + 用户确认 + 原子性）。suffix replay 只在依赖决策完成后执行。
- **决策持久化**：用户手动解决的冲突，DecisionRecord 持久化，下次叠加同样 Mod 时只在冲突指纹完全一致时自动复用（不做模糊匹配）。

**诚实边界**：DAG 不替代 ModStack；依赖正确 ≠ 叠加无冲突。模糊复用用户决策有风险，必须精确指纹匹配。

## 2. 落地优先级（综合判断）

按"产品信任链断点修复"价值排序：

1. **U1 意图接地（最高优先）**：改错对象是致命缺陷，用户第一次用就会失去信任。落地 ReferenceSpec 消解层 + ClarificationRequest。
2. **U3 延迟可观测（前提）**：没有测量就没有承诺。落地 Instrumentation 层（统一计时 + 分阶段记录）是 U2/U4 落地的前提。
3. **U2 可验证执行（信任闸门）**：先做 Godot native headless（最干净），RPGMV AUTOMATED_NON_HEADLESS 次之。
4. **U4 沙箱真实化（安全）**：两层防御，version 1 真实模板 + 静态 AST。
5. **U5 依赖图（多 Mod 场景）**：DependencyGraph + 冲突可视化数据契约。

## 3. 与 iter4 已落地模块的精确关系

| iter5 主题 | 依赖的 iter4 模块 | 新增/改造 |
|-----------|------------------|----------|
| U1 | target_resolver.py, semantic.py, intent.py | 新增 ReferenceSpec 消解层 + ClarificationRequest；改造 resolve_targets 插入消解 |
| U2 | runtime_probe.py, vfs.py, patch_executor.py, sandbox.py | 新增 ValidationReport 完整契约 + Godot headless 适配器；改造 HeadlessRuntimeProbe |
| U3 | pipeline.py, cost_controller.py, incremental_perception.py | 新增 Instrumentation（统一计时）；改造各阶段记录耗时 |
| U4 | sandbox.py, tool_gateway/, sanitizer.py | 新增 version 1 seatbelt profile + AST 静态分析增强；改造 validate_script_safety |
| U5 | mod_manager.py, mod_exporter.py, real_merge/conflict_report.py | 新增 DependencyGraph + DecisionRecord；改造 ModManifest 加 depends_on |
