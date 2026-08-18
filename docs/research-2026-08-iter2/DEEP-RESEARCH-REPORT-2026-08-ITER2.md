# Udify 2026-08 第二轮大迭代 深度研究综合报告

日期: 2026-08-05 | 模式: orchestrate-sol-browser（5×Sol 多轮循环研究 + Codex 中心综合）
基线 commit: c5a6479808a95bff3326ee496a2a648b92b516d0（main，399 测试全绿）
研究产物: .ai-bridge/sol/{R1-INTENT,R2-REALGAME,R3-ENGINE,R4-PATCH,R5-AGENT}.md（合计 ~385k 字符）
源码包: udify-src-iter2.zip（29 文件，84,710 字节，SHA-256 ee7fb2218c8ab6eb73126214a8e58a7a9435f3a8bf1431526418147cd0abc592）

## 0. 综合判断

第一轮（产品闭环）解决了能力不可触达，第二轮必须解决能力的天花板。五个主题的研究收敛到一个共同的根因：Udify 的 ContentGraph 语义可观测性不足。这不是单点缺陷，而是贯穿意图接地、真实游戏验证、跨引擎泛化、Patch 精度、agent 安全的总闸。R1-INTENT 的批判性自评最锐利：最大的技术风险不在 LLM 或结构化输出框架，而在 ContentGraph 的语义可观测性，任何 Reference Resolver 都只能把不确定性从正则关键词转移到另一套猜测系统。

因此第二轮的北极星不是加一个 LLM，而是让内容图谱对人和系统都可观测、可接地、可验证。五个主题是这个北极星在不同层面的展开。

## 1. 逐主题核心结论

### R1-INTENT（36k 字符）

- 框架选型定案：不引入通用 Agent 框架（Pydantic AI/BAML/Outlines/LMQL）。采用供应商原生结构化输出（Anthropic tool use / OpenAI structured outputs）+ Pydantic v2 + 自研 ReferenceResolver + 规则裁决层。Udify 只有一个 LLM 点位，这些框架解决的问题明显大于需求。
- 最关键架构红线：LLM 可解释用户可能在说什么，但不能决定修改哪些节点。目标节点必须由 ContentGraph 上确定性候选生成 + 硬约束过滤 + 排序裁决。LLM 只能在预提供节点白名单中表达偏好，不能创造节点 ID、不能输出路径、不能产生补丁。
- ReferenceResolver 设计：ReferenceSpec 提取器（Boss/第一个/不要 Hero）→ 候选生成（NodeType.CHARACTER + attributes.is_boss/hp 过滤）→ 置信度排序 → 消歧。Boss 翻倍不误伤 Hero 靠硬约束 is_boss=True 排除 Hero。
- 根因洞察：意图真化的天花板是 ContentGraph 的语义可观测性，不是 LLM 选型。

### R2-REALGAME（79k 字符）

- 欠条 B/C 不可分：真实 game_root 与真 Playwright 探针必须一起做。闭环 = 合法真实 game_root → 物化 patched web tree → Playwright 实际加载 → 读取真实运行时对象 → 断言修改生效。
- 目录发现先行：不能假设 game_root 就是 web 服务根目录。miu2d 可能是根 index.html 或 www/index.html，必须先跑目录发现器。相对路径以声明该引用的文件目录为基准解析。符号链接默认拒绝（防逃逸）。
- ProbeSpec→Playwright 映射：字段级映射表（probe type → Playwright 行为 → 失败分类）。风险：运行时全局对象可能被封装在模块作用域而非 globalThis，Playwright 可能无法直接读取。
- 诚实判据：真实 game_root 不以体积定义，而以来源真实、实际可运行、实体来自真实内容、修改后由真实引擎加载定义。Level 2（启动游戏读运行时状态）才算清偿欠条 B。

### R3-ENGINE（62k 字符）

- 第二引擎定案：RPG Maker MV（.json 数据 + js/plugins.js）。数据可解析 JSON、运行时可观测、社区 Mod 案例量大、与 miu2d 同属浏览器 RPG 形态。
- EngineAdapter Protocol 泛化性：基于真实 base.py，六个方法（detect/perceive/get_action_schemas/emit_patch/build_runtime_probes/package_mod）是引擎无关契约。
- 跨引擎本体：真实 NodeType 枚举已含 CHARACTER/ITEM/EVENT/MECHANIC/LEVEL，RPG Maker 的 enemy/actor/item/event/map 基本可映射。

### R4-PATCH（80k 字符）

- PATCH-SYN-10 根因方向：ini 序列化产生同值噪声，方向是 ini_parser 序列化器全量重写（OrderedDict 重建丢失原格式）。需行级确认具体函数。
- 字节级稳定序列化：保持注释/空白/键序/未改行字节不变是硬要求。JSON 文件需保留键序/缩进/浮点精度。
- reverse + ModStack 合并：复用真实 ConflictType 枚举做冲突检测。ModStack 卸载中间 Mod 优先从 base 重放剩余 stack。

### R5-AGENT（129k 字符，最深）

- agent 循环定案：LangGraph 作为循环编排层（显式状态图/checkpoint/interrupt/恢复），不使用框架内置 LLM 绑定工具自动执行路径。LangGraph 的 tool node 只能调用统一的 Udify 适配器。自研安全节点、策略层、批准凭证、审计链。
- 沙箱现实：gVisor/Firecracker 需 Linux，macOS 本地不可用。macOS 可用方案是 seatbelt/sandbox-exec 或 WASM。
- 威胁模型：路径逃逸（allowlist）、R3 绕过人工门（PolicyDecision.requires_human_confirmation）、沙箱逃逸、审计篡改（ToolAuditChain 链式哈希）。

## 2. 跨主题收敛

A. 语义可观测性是总闸。R1 意图接地、R2 运行时探针、R3 跨引擎本体、R4 SourceSpan 精度，全部依赖 ContentGraph 节点是否有足够语义字段（is_boss/hp/enemy/role）。第二轮基础设施投入，必须先做。

B. 真实闭环取代合成闭环。R2（真 game_root + 真 Playwright）、R5（真沙箱而非预留）、R4（字节级稳定而非全量重写）共同指向：所有合成/模拟/预留的欠条必须清偿。

C. LLM/Agent 是可选增强，安全边界是硬约束。R1（LLM 只产候选不决策）、R5（LangGraph 编排但自研安全边界、R3+ 人工门）一致：LLM 永远不进关键路径决策位，ToolGateway 是唯一入口。

## 3. 与 Udify 现状的 diff

| 能力域 | 现状 | 第二轮目标 | 触达代码 |
|--------|------|------------|------------|
| 意图 | INTENT_KEYWORDS 关键词表 | 可选 LLM 结构化候选 + ReferenceResolver 裁决 | cognition/intent_classifier.py, cognition/reference_resolver.py |
| 验证 | HeadlessRuntimeProbe 模拟 | 真 Playwright + 真 game_root | validation/runtime_probe.py, adapters/miu2d.py |
| 引擎 | miu2d 单实现 | EngineAdapter + RpgMakerAdapter | adapters/base.py, adapters/rpg_maker.py(新) |
| Patch | ini 全量重写噪声 | 字节级稳定序列化 + SourceSpan 行级 | execution/patch_executor.py, perception/parsers/ini_parser.py |
| Agent | ToolGateway/MCP 预留 | LangGraph 编排 + 自研安全 agent 循环 | execution/agent_loop(新), tool_gateway/ |

## 4. 风险与红线

- 最大风险：ContentGraph 语义字段缺失会让 R1/R3 的努力空转。优先补节点语义属性。
- macOS 沙箱现实：gVisor 不可用，第二轮沙箱目标定为 seatbelt 或 WASM。
- 真 miu2d 资源：用引擎自带 demo 或 JC 合法拷贝，不下版权资源。
- LLM 红线不变：只产候选，规则层裁决，无 key 全降级，399 测试不依赖网络。

## 5. 下一步

本报告作为 PRD-2026-08-ITER2.md 的输入。PRD 据此拆分可独立交付的编码模块，再用 orchestrate-sol-browser 的分布式编码阶段落地，Codex 中心整合与验收。

详见五份原始研究：.ai-bridge/sol/R1-INTENT.md（36k）、R2-REALGAME.md（79k）、R3-ENGINE.md（62k）、R4-PATCH.md（80k）、R5-AGENT.md（129k）。对话链接见 CHATS.md。
