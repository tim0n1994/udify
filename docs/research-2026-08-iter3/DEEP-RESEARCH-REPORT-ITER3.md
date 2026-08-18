# Udify iter3 深度研究综合报告

日期: 2026-08-05（iter2 当日续）| 模式: orchestrate-sol-browser（5×Sol R1+R2 研究 + Codex 综合）
基线: iter2 交付工作树（427 passed + 1 skip）
研究产物: .ai-bridge/sol/{S1-LLMPATH,S2-MIU2D,S3-CROSSPATCH,S4-SANDBOX,S5-BENCH}.md（合计 ~181k 字符）
源码包: udify-src-iter3.zip（30 文件，85,991 字节）

## 0. 综合判断

iter2 交付了五个"骨架/修复"模块，但每块都留了真闭环边界。iter3 研究收敛到两条主线：
**A. 把骨架补成真闭环**——LLM 路径真接通、跨文件 Patch（JSON）、macOS 真沙箱、miu2d 真接入。
**B. 打开下一层能力**——评测体系与多 Mod 冲突。

五份研究的共同纪律信号：Sols 反复强调"不臆造未确认契约"（S2 的 miu2d 运行时对象、S3 的 ConflictType 成员），这与 iter2 一致，是诚实的。

## 1. 逐主题核心结论

### S1-LLMPATH（42k 字符）
- 推荐架构：规则分类器始终先运行，产生确定性 StructuredIntent 基线；有 key 时 Anthropic 强制 tool use 生成另一个候选；规则优先、LLM 只填空缺的确定性合并。
- 关键技术：Pydantic TypeAdapter(StructuredIntent) 动态生成 Anthropic tool schema，避免手写 schema 漂移。
- 预算：每 job 独立 JobLLMBudget，最多 2 次生成调用；首次校验失败允许 1 次修复；超时/网络/预算不足直接降级。
- 无 key：try/except 不 import anthropic 运行时，全启发式降级。

### S2-MIU2D（21k 字符）
- 诚实结论：不能确认 miu2d 真实文件级目录与 $dataEnemies/$gameTroop 等全局对象，这些只是 RPG Maker 兼容候选，不能写入稳定契约。
- 策略：设计 RuntimeProfile 探测器——Playwright 加载后扫描 window 全局对象，物化为 RuntimeProfile，断言表达式动态生成，避免臆造固定契约。
- 目录发现：discover_web_root(game_root) 找 index.html/www/，拒绝 symlink。

### S3-CROSSPATCH（49k 字符）
- 架构："语义操作 → SourceSpan 定位 → byte-range 编译 → 校验后原位拼接"四层。
- JSON：保留键序/缩进/浮点精度的字节稳定序列化（不破坏结构，只改目标字段）。
- SourceSpan：基于真实字段（file_path/line_start/line_end/ast_path）的行级填充。
- reverse + 合并：复用真实 ConflictType 枚举做冲突检测。

### S4-SANDBOX（30k 字符）
- 选型：macOS 原生 CLI/Python 脚本用 Seatbelt/sandbox-exec（启动快、能限制文件和网络）；WASM(wasmtime) 适合纯计算脚本但不能跑任意 subprocess。
- 关键安全红线：R3/R4 必须 fail closed；沙箱不可用时不得降级为 subprocess.run。
- 缺陷发现：call_approved（iter2 新增）必须走 runner，否则人工批准路径绕过真沙箱。需让 call_approved 与 call_with_runner 共用内部执行入口。

### S5-BENCH（39k 字符）
- 评测集：>=30 case（含圈外），分类法（难度/歧义/负向偏好）。
- A/B：heuristic vs resolver vs LLM 对照，mock LLM 离线可跑；指标（准确率/目标精度/是否误伤/延迟）。
- ModStack 合并：基于真实 ConflictType 的三路合并冲突检测。
- 自动化：pytest marker（@bench）+ JSON 报告。

## 2. 跨主题收敛

A. 真闭环优先于新功能：S1(LLM 真接通)、S2(真 miu2d)、S3(JSON Patch)、S4(真沙箱) 都是把 iter2 骨架补真。
B. 诚实契约：不臆造未确认契约（S2 RuntimeProfile 探测、S3 ConflictType 复用）。
C. 安全 fail-closed：S4 明确沙箱不可用不降级，与 S1 的无 key 降级互补（能力降级 OK，安全降级不 OK）。

## 3. 与 iter2 现状的 diff

| 域 | iter2 | iter3 目标 | 触达 |
|----|-------|-----------|------|
| LLM 意图 | target_resolver 规则 | LLM 候选 + 规则裁决 + cost tracker | cognition/intent_classifier.py(改), cognition/llm_intent.py(新) |
| 跨文件 Patch | ini 稳定 | JSON 稳定 + SourceSpan 行级 | execution/patch_executor.py(改) |
| 沙箱 | 降级占位 | macOS seatbelt + call_approved 走 runner | tool_gateway/sandbox.py(改), gateway.py(改) |
| 评测 | 10 golden | >=30 case + A/B + ModStack 合并 | tests/bench/(新), mod_manager(改) |
| miu2d | fake web root | RuntimeProfile 探测 + 目录发现 | validation/playwright_probe.py(改), adapters/miu2d.py(改) |

## 4. 风险与红线

- S4 沙箱 fail-closed：沙箱不可用时 R3+ 操作拒绝，不降级。
- S2 miu2d 契约未确认：用 RuntimeProfile 探测，不写死 $dataEnemies。
- LLM 无 key 全降级；测试不依赖网络。
- 不 commit/push/部署/迁移（未授权）。

## 5. 下一步

本报告 → PRD-ITER3 → 分布式编码 → Codex 整合。
