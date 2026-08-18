# Q3：LLM 意图理解工程化深度研究

## 项目背景

Udify 当前意图理解是正则关键词表（_INTENT_PATTERNS），已验证产品缺陷：用户说"把 Boss 血量翻倍"时，关键词引擎不做目标过滤，会把 Hero 的血量也翻倍。LLMClient（支持 OpenAI/Anthropic 的 SDK 代码）存在但无任何运行路径实例化。

迭代计划 COG-LLM-01..03 要求：LLM 只在意图解析一个点位用结构化输出，候选身份（规则层裁决合并），每 job 最多 2 次调用，无 API key 时全启发式降级（CI 无 key 必须全绿）。游戏内容/工具输出永远作为数据段传入，不进指令位。

## 需要深度研究的问题

1. **结构化输出的成熟开源框架选型**：
   - Anthropic SDK tool use / JSON schema 强约束 vs OpenAI function calling / structured outputs
   - Pydantic AI、Instructor、Marvin、BAML、Outlines/Guidance、LMQL 等结构化输出框架对比
   - 框架的预算控制、重试、超时降级能力
   - Python 3.12+ 兼容性与类型安全（与 Udify 的 mypy strict 对齐）

2. **意图接地（Intent Grounding）工程化**：
   - 从"像魂系一样更硬核"到可执行目标（难度曲线、死亡惩罚、Boss 行为）的语义分解
   - Reference Resolution：如何把"第一个 Boss"精确解析到 ContentGraph 中的目标节点（而非 Hero）
   - 歧义消解：当用户意图模糊时，如何生成候选集并让用户在审阅台选择
   - 上下文窗口管理：游戏 ContentGraph 可能很大，如何做子图提取与 prompt 压缩

3. **预算与降级工程**：
   - Token 预算护栏的实现模式（per-job 上限、cost tracking、超限降级）
   - 超时与重试策略（指数退避 vs 立即降级）
   - 无 key 模式下的启发式意图解析质量边界评估
   - 结构化输出校验失败时的 fallback（Pydantic 校验不通过时如何恢复）

4. **评测体系**：
   - UdifyBench 现有 10 个 golden case 如何扩展为意图理解评测集
   - A/B 评测框架设计（heuristic vs LLM，不同模型对比）
   - 评测指标：意图准确率、目标精度、token 成本、延迟
   - 如何构建圈外（非 miu2d 内置）的意图测试样例

5. **安全与隔离**：
   - 三源隔离（系统指令/用户意图/游戏内容）的工程实现
   - Prompt injection 防御（游戏内容中的恶意文本不污染指令）
   - LLM 输出永远不直接写文件（只产生候选 StructuredIntent，规则层裁决）

## 交付物

- 结构化输出框架选型对比表（至少 6 个框架，含 API 风格/预算控制/类型安全/许可证）
- 推荐 LLM 意图解析方案（完整架构：输入预处理→子图提取→LLM 结构化输出→校验→裁决）
- Reference Resolution 的具体算法设计（ContentGraph 目标定位）
- 预算降级工程的可运行代码骨架
- 扩展的意图评测集设计（至少 30 个测试 case，含圈外样例）
- 安全隔离层的威胁模型与防御措施

## 约束

- 优先使用成熟开源框架，不自研结构化输出引擎
- LLM 是可选增强层，无 key 时全降级且 399 测试不依赖网络
- 只在意图解析一个点位用 LLM，不做 agent 自由发挥
- 三源隔离不可违反，LLM 输出永远是候选身份
- Python 3.12+ / mypy strict 兼容
