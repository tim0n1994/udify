# Udify 2026-08 第二轮大迭代深度研究 · 研究设计

日期: 2026-08-05 | 模式: handoff（深度研究）+ coding（落地实现）
执行: Codex 统一调度 + ChatGPT Sol 标签页智能体（orchestrate-sol-browser）
基线 commit: c5a6479808a95bff3326ee496a2a648b92b516d0（main，399 测试全绿）

## 背景：为什么是第二轮大迭代

2026-08 第一轮（产品闭环）已基本落地：批次 4A（ModJob + SQLite durable）、4B（薄 API 8 端点）、5（Next.js 审阅切片）完成；北极星浏览器五分钟走完意图-审阅-批准-验证-回滚本地实测通过。剩余批次 6（P1 尾部）：LLM 意图真化、真实 miu2d 验收、真 Playwright 探针、覆盖率爬坡、PATCH-SYN-10。

第一轮把引擎闭环搬成了产品闭环，但没有改变能力的本质边界：意图仍是关键词表、只支持 miu2d 合成样例、运行时验证仍是 headless 模拟、Patch 抽象只在 ini/lua 上成立、工具执行仍是预留。第二轮目标是突破这些能力天花板。

## 五个深度研究主题（相互独立，可并行）

| ID | 主题 | 当前瓶颈 | 第二轮目标 |
|----|------|----------|------------|
| R1-INTENT | LLM 意图接地工程化 | 关键词表；Boss 翻倍误伤 Hero | 结构化输出框架选型 + Reference Resolution 算法 + 评测集 + 三源隔离 |
| R2-REALGAME | 真实游戏验证闭环 | 合成 ini + headless 探针 | 真 miu2d game_root 接入 + 真 Playwright probe + 欠条 B/C 清偿 |
| R3-ENGINE | 跨引擎适配器泛化 | miu2d 单引擎硬编码 | EngineAdapter Protocol 实装第二引擎（RPG Maker MV / Unity）工程路径 |
| R4-PATCH | 语义 Patch 与可逆性 | ini 同值 diff 噪声；仅 ini/lua | 跨文件类型语义 Patch + 字节级稳定序列化 + 完整 reverse/merge |
| R5-AGENT | 智能体工具执行与安全 | ToolGateway/MCP 预留无真执行 | 安全 agent 循环：规划-网关-沙箱-审计-反馈 + 威胁模型 |

## 多轮深化策略（每主题 4-5 轮）

1. R1 初始：自包含 expert-grade prompt。
2. R2 暂存深化：版本号/bundle size、可编译代码、具体算法、基准设计。
3. R3 极限：可运行完整代码、failure mode、威胁模型、批判自评。
4. R4 落地：依赖清单、PR 切分、10 分钟 demo、诚实自评。
5. R5 综合：一页纸决策矩阵、3 行动项、矛盾裁决、与 Udify 现状 diff。

每个标签页目标累计推理时间 >90 分钟，5 主题并行 >7.5 小时。

## 交付链路

5×Sol 多轮研究 → harvestAll → 综合报告 → PRD → 分布式 Sol 编码 → harvestCode → Codex 中心整合 → 门禁验收。

## 红线

- 优先成熟开源，不自研可复用轮子。
- LLM/网络是可选增强层；无 key 时 399 测试不依赖网络。
- 不下版权资源、不改生产配置、不部署、不迁移真实数据。
- Sol 交付物在 Codex 侧独立验证，不以 Sol 自述为准。
