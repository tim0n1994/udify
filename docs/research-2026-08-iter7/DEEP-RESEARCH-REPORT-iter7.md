# Udify iter7 深度研究报告

日期: 2026-08-13 | 研究设计: `RESEARCH-DESIGN-iter7.md`
研究方式: 定向 web 检索（官方文档 + 2026 arXiv 论文 + 社区实践）+ 本地代码实测取证
基线实测: 800 passed / **1 failed** / 2 skipped；`udify/` 30,787 行；6 个孤儿符号

---

## W1 — 接线的结构性强制

### W1.1 工具能力边界（核对官方文档）

`import-linter` 提供三类契约：

| 契约类型 | 语义 | 能否检出孤儿簇 |
|---|---|---|
| **Layers** | 有序模块列表，高层可依赖低层，反向（含间接）禁止 | ❌ 管方向，不管可达性 |
| **Independence** | 一组模块之间不得互相依赖（含间接） | ❌ 恰好相反：孤儿簇内部**是**互相依赖的 |
| **Forbidden modules** | A 组不得被 B 组导入（含后代、含间接） | ❌ 管"不许被导入"，不管"必须被导入" |

**结论（重要）**：`import-linter` 的三类契约**全部无法直接表达"必须被主路径调用"**。它是"禁止型"约束语言，而孤儿检测需要的是"要求型"约束。

`vulture` 做 AST 静态分析找未使用的函数/类/变量/import，是最主流的 Python 死代码工具。但它的判定单位是**符号级未引用**，对孤儿簇同样失效——簇内符号互相引用，`vulture` 会认为它们"被使用了"。

社区工具里最接近的是 JS 生态的 `unimported`，它显式区分两件事：未使用依赖，以及**orphan files（存在于仓库但没有被任何其他文件 import 的文件）**。这个"orphan"概念是对的，但它仍是**文件级 import 关系**，不是**入口点可达性**。

### W1.2 结论：必须自建可达性检查（且这是唯一合理的自建）

三个现成工具都不解决问题，原因是它们回答的问题不同：

- `vulture`：这个符号有没有被引用？
- `import-linter`：这些模块之间的依赖方向对不对？
- 我们要问的：**从 `udify/cli.py` 和 `udify/api/app.py` 出发，沿 import + 调用边做闭包，这个模块在不在闭包里？**

这是一个约 60-100 行的图可达性计算（stdlib `ast` + `networkx` 已在依赖里，或直接用 dict-of-sets 做 BFS），**不需要新依赖**。

> 这是 iter7 唯一被允许的"新建"，因为 §W1.1 已证明现有工具无法承载（符合研究纪律 #4）。

**算法契约**：

```
入口点 = {udify/cli.py 的 CLI 子命令, udify/api/app.py 的路由处理函数}
可达闭包 = BFS(入口点, 边 = import + 模块级符号引用)
孤儿集 = 所有 udify/ 下的公共符号 - 可达闭包 - allowlist
门禁 = 孤儿集非空则 CI 红
```

**已知误报来源（必须框架感知）**：

| 模式 | 为什么看似孤儿 | 处理 |
|---|---|---|
| FastAPI 路由处理函数 | 由装饰器注册，无显式调用者 | 装饰器即入口点，纳入 roots |
| pytest fixture | 由 pytest 收集 | 只扫 `udify/`，不扫 `tests/` |
| `Protocol` / 抽象基类实现 | 由鸭子类型调用 | allowlist + 契约测试佐证 |
| `__all__` 导出的公共 API | 供外部使用 | allowlist 且必须有 docstring 说明消费者 |

社区共识是**渐进式启用**：一天内阻塞会瘫痪存量代码库。因此门禁必须支持基线快照（baseline）——冻结当前 6 个孤儿为"已知债务"，只阻塞**新增**孤儿，同时用带过期日期的 allowlist 强制存量清零。

### W1.3 allowlist 治理

allowlist 条目必须带三个字段，缺一不可：符号名、豁免理由、**过期日期**。过期日期到期未清 = CI 红。这把"展期"从一个静默动作变成一个必须显式续签的动作——直接针对 iter5→iter6 的失效模式。

---

## W2 — 引用接地的正确性

### W2.1 序数/最高级接地的确定性算法

基于 `tests/fixtures/rpgmv/minimal/` 的真实结构：`Enemies.json[0]=Slime(params[2]=10)`、`[1]=BossA(params[2]=50)`、`[2]=BossC(params[2]=120)`。

关键洞察：**"第一个 Boss" 的排序键不是 `Enemies.json` 的数组下标**，而是"在已过滤为 boss 的子集内的次序"。iter6 的 E2E 测试正是这样断言的（`db_index=0 in bosses` → BossA，而 BossA 的全局下标是 1）。

因此接地是一个**两阶段**过程，不能合并：

```
阶段1 过滤：全体实体 → 语义类别子集（boss / actor / item）
            依据 = semantic_tags（来自 SemanticLifter）
阶段2 选择：子集内按引用类型施加选择器
            序数（第一个/最后一个）→ 子集内出现序
            最高级（最强/最弱）→ 指定数值字段排序（params[2]=attack）
```

**歧义的形式化定义**（决定何时产 `ClarificationRequest` 而非猜测）：

| 条件 | 判定 |
|---|---|
| 阶段1 子集为空 | 拒绝，`ClarificationRequest`：找不到该类别 |
| 阶段2 排序键缺失或字段不存在 | 拒绝，不得回退到下标 |
| 最高级引用出现并列第一 | 拒绝，`ClarificationRequest` 列出并列候选 |
| 引用未指明类别（"让它更难"） | 拒绝，要求澄清 |
| 子集唯一元素 | 直接选中，无歧义 |

**"最强"必须显式绑定字段**：`params[2]` 是 attack。"最强"在游戏语义里可能指 attack / HP / 综合，这本身是歧义源。研究结论：**产品应固定为 attack 并在 UI 明示口径**，而不是让 LLM 自由裁量——因为口径漂移在回归测试里不可见。

### W2.2 语法约束解码的真实增益与代价

2026 年的论文给出了比"用 structured output 就对了"更精细的结论：

- **《Grammar-Constrained Decoding for Structured NLP Tasks without Finetuning》**：语法约束解码显著提升实体消歧表现，受约束的 LLaMA-33B 超过仅在有限数据集上训练的专用模型。这直接支持我们在**实体消歧**上用约束解码。
- **《When Correct Isn't Usable: Improving Structured Output Reliability in Small Language Models》(2026-05)**：刻画了"正确性"与"格式合规"之间的鸿沟；语法约束在生成时强制语法有效性。含义：格式合规 ≠ 语义正确，schema 约束只解决前者。
- **《The Format Tax》(2026)**：分离了 prompt 层格式要求与 decoder 层采样约束的性能损失来源，发现**采样约束只占损失的一小部分，主要代价来自 prompt 层**。含义：不要因为怕"格式税"而放弃约束解码——真正该优化的是 prompt 设计。
- **《Empirical Study for Structured Output Control in LLMs for SE》(2026-06)**：把失败分为语法/结构/语义三类，并对比了语法约束解码、正则校验、模板驱动的缓解效果。含义：**三层失败需要三层防御**，schema 只挡语法与结构，语义错误必须靠规则层裁决。
- **PARSE（schema 优化用于可靠实体抽取）**：schema 本身的设计影响抽取可靠性。含义：`StructuredIntent` 的 schema 应为 LLM 优化（扁平、枚举优先、避免深嵌套），而非直接复用内部 dataclass 形状。

**汇总结论**：LLM 只产**候选 + 置信度**，规则层做**最终裁决**。约束解码保证 schema 合规；语义正确性由 §W2.1 的确定性算法保证。这与项目既有的"LLM 只产候选，不能越过 schema"红线一致，本轮把它落到实处。

### W2.3 无 Key 时的能力边界（诚实矩阵）

| 引用类型 | 纯规则可否接地 | 说明 |
|---|---|---|
| 显式命名（"BossA"） | ✅ | 精确匹配 |
| 序数（"第一个 Boss"） | ✅ | §W2.1 两阶段算法，无需 LLM |
| 最高级（"最强的 Boss"） | ✅ | 固定字段排序，无需 LLM |
| 模糊描述（"那个很难的关底"） | ❌ | 需要 LLM 或澄清 |
| 跨语言同义（"头目"/"BOSS"） | ⚠️ 部分 | 依赖同义词表覆盖度 |

**重要产品结论**：**「第一个 Boss」这个致命 bug 根本不需要 LLM 就能修**。它是纯粹的两阶段确定性算法问题。把它归因为"等 LLM 接入"是错误的归因，也是它被拖了三轮的原因之一。

---

## W3 — 模型路由与成本护栏

### W3.1 2026-08 当前定价（核对官方与多方汇总）

| 模型 | 输入 $/M | 输出 $/M | 适用 |
|---|---|---|---|
| Fable 5 | 10 | 50 | 不适用（成本失衡） |
| Opus 5 | 5 | 25 | 复杂规划批评，非意图解析 |
| Sonnet 5 | 2 | 10（**至 2026-08-31**，9/1 起 3/15） | 默认档 |
| Haiku 4.5 | 1 | 5 | **意图解析正解** |

意图解析的负载画像：输入短（意图文本 + schema + 少量图摘要）、输出短（结构化 `StructuredIntent`）、要求低延迟（交互式）。**Haiku 4.5 是正确档位**；Sonnet 5 作为置信度低时的升级档。

成本优化手段的适用性判断：

- **prompt caching**（缓存命中为标准输入价的 10%）：✅ 适用。schema 定义 + 系统指令 + 本体表是固定前缀，天然可缓存。
- **Batch API**（输入输出各 5 折）：❌ **不适用**。意图解析是交互式低延迟路径，batch 是异步非紧急工作负载的手段。
- **模型路由**（默认低档、按需升档）：✅ 适用，且是最有效的成本策略。

### W3.2 本地模型路径（对应 JC 的本地推理工作站方向）

这是"无 Key 也要能用"红线的关键：

- **llama.cpp**：支持 `--grammar-file schema.gbnf`，或 server 的 `response_format` 传 JSON schema，通过**每步屏蔽非法 token** 保证输出匹配形式语法。这是本地路径能做结构化输出的技术基础。
- **Ollama**（v0.5+）：可直接传 JSON schema 给 `format` 参数，内部转 GBNF 交给 llama.cpp。
- **MLX**：在 Apple Silicon 上吞吐更高（部分场景 21%-87% 优于 llama.cpp），但**核心栈没有 GBNF 等价物**，需外接 `outlines` / `lm-format-enforcer`。长上下文时 llama.cpp 带 `--flash-attn` 反而更快。

**选型结论**：本地结构化抽取路径**选 llama.cpp（或 Ollama 封装）而非裸 MLX**，理由是 GBNF 语法约束是内建能力而非外挂。这与"追求最高吞吐"的直觉相反，但结构化保证比吞吐重要。

### W3.3 降级原因的正交记录（直接修 §0.4 缺陷）

当前缺陷的本质：`degradation_reason` 是**单值**，多个降级条件同时成立时先判定者掩盖后判定者。

正确设计是**原因集合 + 优先级显示**，而非单值短路：

| 维度 | 取值 | 独立判定 |
|---|---|---|
| 凭证 | HAS_KEY / NO_KEY | 独立 |
| 预算 | WITHIN_BUDGET / BUDGET_EXHAUSTED | 独立 |
| 延迟 | WITHIN_TIMEOUT / TIMED_OUT | 独立 |
| 结果 | LLM_USED / RULE_FALLBACK | 派生 |

判定顺序不再决定记录内容：**所有成立的原因都要记录**，显示层按优先级挑主因。这样"无 Key 且预算耗尽"两个事实都可见，运维不会被掩盖。

---

## W4 — 流式可观测性

### W4.1 选型定论：SSE

产品场景是单向（服务端推进度）、单用户、127.0.0.1 回环。社区共识明确：**单向场景（通知、实时流、进度更新）SSE 几乎必然是更好选择**；WebSocket 用于真正需要双向的场景（聊天、多人游戏、协作编辑）。

SSE 的决定性优势是 **EventSource 内建自动重连**：连接断开后浏览器自动重连并携带 `Last-Event-ID` 头；WebSocket 的重连逻辑必须手写。

### W4.2 断连恢复与现有 `job_events` 表的天然对应

这是本轮最省力的架构契合点。SSE 的恢复协议要求：每个事件带 `id:` 字段，客户端重连时通过 `Last-Event-ID` 请求头回传最后收到的 id，服务端据此续传。

而 `job_events` 表**已经是 append-only 且带 seq**（iter4A 设计，OBS-01 trace schema 即此表）。因此：

```
SSE 的 id: 字段  ←直接映射→  job_events.seq
Last-Event-ID 头 ←直接映射→  WHERE seq > :last_id ORDER BY seq
```

**无需新增存储、无需新增表、无需事件缓冲区**。这是"复用已有资产"的典型，也是 SSE 相对 WebSocket 的又一优势（WebSocket 需要自建补发机制）。

### W4.3 工程细节

- **心跳**：每 15-30 秒发注释行（`: heartbeat`）防止代理超时。本地回环虽无代理，但保留心跳可让前端区分"服务端卡住"与"没有新事件"。
- **字段**：`event:`（自定义事件名）、`id:`（恢复用）、`retry:`（重连延迟毫秒）。
- **与 TanStack Query 协同**：SSE 事件到达时用 `setQueryData` 局部更新（而非 `invalidateQueries` 触发重新请求），避免每个事件打一次 API。终态事件（completed/failed）时才 invalidate 拉取完整结果。
- **降级**：SSE 连接失败 → 回退现有 1s 轮询。轮询代码已存在，作为 fallback 零成本保留。

---

## W5 — 验证的诚实分级

### W5.1 从 APR 领域借来的补丁验证纪律

自动程序修复（APR）的评测方法论对 Mod 验证有直接可移植性。SWE-bench 的评测通过**测试执行**完成，包含两类断言：

- **fail-to-pass**：确认问题被解决（改动生效）
- **pass-to-pass**：检查回归安全（没改坏别的）

映射到 Udify：

| APR 概念 | Udify 对应 | 断言 |
|---|---|---|
| fail-to-pass | 意图达成 | BossA.params[2] 从 50 → 100 |
| pass-to-pass | 回归安全 | Slime/BossC/所有 Actor **逐字节不变** |

**这是当前验证体系最大的缺口**：现有探针验证"游戏能启动"，但不验证"没改坏别的"。"探针 6/6 通过"若不含 pass-to-pass 断言，含金量有限。

APR 研究还指出其工作流为：故障定位 → 补丁合成 → 补丁验证 → 代码集成，且现代流水线包含**复现测试生成**与**回归测试选择**。Udify 的对应能力（`ProbeGenerator` 从 patch 自动生成最小探针）目前仍是 P1 空缺。

### W5.2 引擎覆盖矩阵的诚实边界

| 引擎 | 可验证等级 | 技术依据 |
|---|---|---|
| Godot | `NATIVE_HEADLESS` | `--headless` 原生支持；GUT/gdUnit4 均提供 CLI 与 JUnit XML 导出供 CI 消费 |
| RPGMV | `AUTOMATED_NON_HEADLESS` | NW.js 无真 headless，只能自动化非 headless 启动 |
| 商业未植入 | `UNVERIFIABLE` | 无注入点，只能静态分析 |

Godot headless 的真实标志组合（社区实践）：`--headless`、`--display-driver headless`、`--audio-driver Dummy`、`--disable-render-loop`；CI 中需**先做一次 headless 预导入（warm-up import）再跑测试**，否则资源未导入导致假失败。这个"两步法"是最容易踩的坑。

**诚实声明的产品含义**：`run_by_engine` 接线后，`ValidationReport` 必须带 `engine_coverage` 字段，UI 上 `UNVERIFIABLE` 不得显示为绿色对勾——这是 iter6 确立的"降级只降交付级别、不降安全级别"铁律在 UI 层的延伸。

---

## W6 — 补丁噪声与序列化保真

### W6.1 问题本质

批次 5B 记录的真实噪声：`Defense=10` 在 diff 中一删一增，值完全相同。根因是 ini 重写走"全量解析 → 全量序列化"，未修改行的字节形态（空白、键序、行尾）无法保证复原。

### W6.2 与产品承诺的耦合

Udify 的核心卖点是"改得让你敢批准"，而**审阅信任直接正比于 diff 的信噪比**。同值噪声行有三重危害：

1. 稀释真实改动，审阅者疲劳
2. 使"影响范围"评估失真（风险分基于改动行数则被高估）
3. **破坏 §W5.1 的 pass-to-pass 断言**——若未涉及实体的字节都会变，"逐字节不变"这个最强回归断言根本无法成立

第 3 点是本轮的关键发现：**W6 不是体验优化，它是 W5 回归验证的前置条件**。`PATCH-SYN-10` 从"P1 体验债"升级为"P0 验证阻塞项"。

### W6.3 实现策略

格式保持型序列化的通行做法是**只重写被修改的行区间，其余字节原样透传**——这正好与 `SourceSpan` 的 `byte_start/byte_end` 设计吻合。项目已有 `SourceSpan` 数据结构，缺的是让 emitter 真正基于它做局部替换而非全量重写。

附带收益：批次 5B 记录的"SourceSpan 只到文件级、`line_start/line_end` 为空"这一数据质量债，在做局部替换时**必须**被解决——因为局部替换没有行号就无法进行。两笔债共用一个修复。

---

## 关键研究纠正

1. **`import-linter` 无法检出孤儿簇**：它是禁止型约束语言（layers/independence/forbidden），而孤儿检测需要要求型约束。`vulture` 同样失效（簇内互引即"已使用"）。必须自建入口点可达性分析——这是 iter7 唯一被允许的新建。
2. **「第一个 Boss」不需要 LLM**：它是两阶段确定性算法（语义过滤 + 子集内序数选择）。把它归因为"等 LLM"是三轮未修的原因之一。
3. **本地路径选 llama.cpp 而非 MLX**：MLX 吞吐更高但核心栈无 GBNF 等价物，结构化保证优先于吞吐。
4. **SSE 的 `id:` 直接映射 `job_events.seq`**：断连补发零新增存储，这是 SSE 相对 WebSocket 的决定性优势。
5. **格式税主要来自 prompt 层而非采样约束**：不应因担心性能而放弃约束解码。
6. **`PATCH-SYN-10` 是 P0 而非 P1**：diff 噪声使"逐字节不变"的 pass-to-pass 回归断言无法成立，它阻塞验证体系而不只是影响体验。
7. **降级原因必须是集合而非单值**：单值短路导致 BUDGET_EXHAUSTED 被 NO_KEY 永久掩盖（当前红测试的根因）。

---

## 来源

- [Import Linter — Contract types](https://import-linter.readthedocs.io/en/latest/contract_types.html)
- [Dead Code Detection Tools: knip vs ts-prune vs Vulture vs unimported](https://www.pistack.xyz/posts/2026-06-19-dead-code-detection-tools-knip-ts-prune-vulture-unimported/)
- [Grammar-Constrained Decoding for Structured NLP Tasks without Finetuning](https://arxiv.org/pdf/2305.13971)
- [When Correct Isn't Usable: Structured Output Reliability in Small LMs (2026)](https://arxiv.org/html/2605.02363v1)
- [Empirical Study for Structured Output Control in LLMs for SE (2026)](https://arxiv.org/html/2606.09395)
- [PARSE: LLM Driven Schema Optimization for Reliable Entity Extraction](https://arxiv.org/html/2510.08623v1)
- [Claude Platform Docs — Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Claude API Pricing (August 2026)](https://benchlm.ai/anthropic/api-pricing)
- [llama.cpp](https://github.com/ggml-org/llama.cpp)
- [Best Local LLMs for Structured Output (2026)](https://insiderllm.com/guides/structured-output-local-llms/)
- [FastAPI — Server-Sent Events](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [SSE vs WebSockets: Comparing Real-Time Communication Protocols](https://softwaremill.com/sse-vs-websockets-comparing-real-time-communication-protocols/)
- [Understanding APR Agents Through the Lens of Traceability](https://arxiv.org/html/2506.08311v2)
- [Dissecting the SWE-Bench Leaderboards](https://arxiv.org/html/2506.17208v2)
- [GdUnit4](https://github.com/godot-gdunit-labs/gdUnit4)
- [CI-tested GUT for Godot 4](https://medium.com/@kpicaza/ci-tested-gut-for-godot-4-fast-green-and-reliable-c56f16cde73d)
