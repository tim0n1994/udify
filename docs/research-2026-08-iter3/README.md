# Udify iter3 大迭代 · 研究设计

日期: 2026-08-05（iter2 当日续）| 模式: orchestrate-sol-browser（研究→PRD→编码→整合）
基线: iter2 交付后工作树（427 passed + 1 skip），HEAD c5a6479 + iter2 未提交改动
iter2 已交付: M1 语义层 / M2 目标解析 / M3 Playwright 探针骨架 / M4 ini 稳定序列化 / M5 agent 循环骨架

## 为什么是 iter3

iter2 证明了管线并交付了五个"骨架/修复"模块，但每一块都留了真闭环的边界：M2 的 LLM 路径还是占位、M3 只在 fake web root 上测、M4 只修了 ini（JSON/跨文件未做）、M5 沙箱还是降级占位。同时 iter2 打开但未填的下一层：评测体系、多 Mod 冲突、感知性能。iter3 的目标是把这些骨架补成真闭环，并打开评测与多 Mod 两层新能力。

## 五个研究主题（深化 iter2 + 打开下一层）

| ID | 主题 | iter2 状态 | iter3 目标 |
|----|------|-----------|------------|
| S1-LLMPATH | LLM 意图路径真接通 | M2 只有规则 target_resolver，LLM 路径占位 | Anthropic tool use 结构化候选 + cost tracker + 无 key 全降级，真接通 IntentClassifier |
| S2-MIU2D | miu2d 真实接入与运行时契约 | M3 只在 fake web root | miu2d 真实目录发现 + 运行时对象契约 + 探针到真引擎（用 demo/合成 web build） |
| S3-CROSSPATCH | 跨文件类型语义 Patch | M4 只修 ini | JSON（RPG Maker 风格）+ 文本资源的字节稳定序列化 + SourceSpan 行级 |
| S4-SANDBOX | macOS 可用真沙箱 | M5 沙箱降级占位 | macOS seatbelt/sandbox-exec 或 WASM 真隔离方案 + 与 ToolGateway 集成 |
| S5-BENCH | 评测体系与多 Mod 冲突 | iter2 未涉及 | UdifyBench 扩展（>=30 case）+ ModStack 三路合并冲突检测 |

## 多轮深化策略（每主题 3 轮）

1. R1 自包含 expert prompt。
2. R2 深化：版本号、可编译代码、具体算法。
3. R3 落地：基于真实源码（附源码包）的可应用 diff + 测试夹具。

吸取 iter2 教训：编码标签不提前 release；attach 在 send 前；poll 计数滞后时用 snapshot 核实。

## 交付链路

5×Sol 多轮研究 → harvestAll → 综合报告 → iter3 PRD → 分布式 Sol 编码 → harvestCode → Codex 整合 → 门禁。

## 红线（继承）

- LLM 只产候选、规则裁决、无 key 全降级、测试不依赖网络。
- 不下版权资源、不改生产配置、不部署、不迁移、不 commit/push（未授权）。
- Sol 交付物 Codex 侧独立验证。
