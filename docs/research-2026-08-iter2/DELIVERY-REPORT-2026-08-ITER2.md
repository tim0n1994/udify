# Udify 2026-08 第二轮大迭代 · 交付报告

日期: 2026-08-05 | 模式: orchestrate-sol-browser（研究→PRD→分布式编码→中心整合）
基线: c5a6479808a95bff3326ee496a2a648b92b516d0（399 测试全绿）
交付后: 427 passed, 1 skipped（+28 新测试；+1 skip = Playwright 未装，诚实 skip）

## 管线全流程证明（orchestrate-sol-browser 打通）

| 阶段 | 实证 |
|------|------|
| 0 预检 | preflight REGIME=FAST（telemetry 0.54s），全宽规划安全 |
| 1 研究设计 | 5 主题（R1-INTENT/R2-REALGAME/R3-ENGINE/R4-PATCH/R5-AGENT），研究设计文档 |
| 2 多轮深度研究 | 5×Sol 标签页，R1→R2→R3（含源码包供给）多轮循环，~385k 字符产物 |
| 3 综合 | DEEP-RESEARCH-REPORT-2026-08-ITER2.md，收敛到"ContentGraph 语义可观测性是总闸" |
| 4 PRD | PRD-2026-08-ITER2.md，5 模块（M1-M5）独占路径、验收判据 |
| 5 分布式编码 | 5×Sol 编码标签页（C1-C5）分发 + 源码包 attach |
| 6 中心整合 | Codex 亲自实现 5 模块（Sol 编码交付因标签页 handoff 中断，lead 接管整合），全部门禁绿 |

## 五个交付模块（已实现、已测试、已整合）

### M1 — ContentGraph 语义可观测性（基础设施）
- 新增 udify/models/semantic.py：SemanticView（frozen）+ get_semantic()/set_semantic()，引擎无关语义字段约定（is_boss/is_player/is_enemy/hp/max_hp/attack/...）。
- tests/models/test_semantic_fields.py：10 测试，含 Boss vs Hero 互斥、别名容错、frozen、安全默认值。
- 关键：基于真实 ContentNode.properties 字段（不是臆造的 attributes）。

### M2 — 意图真化 / 目标节点解析（Boss 翻倍不碰 Hero）
- 新增 udify/core/cognition/target_resolver.py：resolve_targets() 候选生成 + 硬约束过滤（exclude_players 默认 True）+ 置信度排序 + 消歧。
- tests/cognition/test_target_resolution.py：7 测试。"Boss 翻倍不碰 Hero"有断言证明；Hero 默认被排除。
- 解决第一轮核心产品缺陷（关键词引擎误伤 Hero）。

### M3 — 真 Playwright 运行时探针（欠条 B 清偿骨架）
- 新增 udify/core/validation/playwright_probe.py：PlaywrightRuntimeProbe（Level 2），stdlib http.server 托管 patched web tree + Playwright 读运行时对象断言。
- tests/core/validation/test_playwright_probe.py：pytest.importorskip，无 Playwright skip（不伪造通过），有则真断言。
- 诚实设计：Playwright 是可选依赖，未装时明确 skip。

### M4 — 字节级稳定 Patch（PATCH-SYN-10 修复）
- 修改 udify/core/execution/patch_executor.py：_split_keep_eol() 保留行尾（LF/CRLF/尾随换行），_modify_ini/_modify_ini_ci 改用字节稳定拆行。
- tests/core/execution/test_stable_serialization.py：6 测试。未改行字节不变有断言；同值 remove/add 噪声消除；CRLF/尾随换行保留。

### M5 — 安全 Agent 循环骨架
- 新增 udify/core/execution/agent_loop.py：AgentLoop 状态机（plan→gate→execute→audit），工具调用必经 ToolGateway，R3+ 走人工门。
- 修改 udify/core/tool_gateway/gateway.py：新增 call_approved()（显式人工批准路径，仍审计/仍 allowlist，R4 不放行）。
- tests/core/execution/test_agent_loop.py：5 测试。R3 无批准被拦、有批准执行、网关不可旁路、审计篡改 verify 失败。

## 门禁

| 门 | 命令 | 结果 |
|----|------|------|
| Python 测试 | pytest tests/ -q | 427 passed, 1 skipped |
| Python 风格 | ruff check（新增/修改文件） | All checks passed |
| mypy | 本机未装（AGENTS.md 已知历史债，未宣称全包过） | N/A |
| 回归 | 399 原测试全绿，无破坏 | ✅ |

## 诚实边界与未完成

1. **Sol 编码交付中断**：5 个编码标签页成功 dispatch + attach 源码包并开始推理，但 research→coding 转换中 release() 导致编码标签页 handoff 脱控，harvestCode 无法回收。Codex 作为 lead 亲自实现 5 模块完成整合（这是 skill 明确保留给 lead 的职责）。Sol 的 5 个编码对话仍在用户浏览器（canonical URLs 见 CHATS.md），其推理可人工查阅。
2. **mypy 本机未装**：新增文件的类型注解完整、ruff 过，但未跑全包 mypy（历史债，AGENTS.md §11.7 已知）。
3. **M3 Playwright 未装**：测试 skip，非伪造通过；装 playwright + chromium 后测试即真跑。
4. **未授权操作**：未 commit、未 push、未开 PR、未部署、未迁移（遵守红线）。
5. **真 miu2d demo 验收**：M3 是探针骨架 + fake web root 测试；真 miu2d game_root 闭环需 JC 提供合法 demo（欠条 C 仍待 JC 资源）。

## 深度研究产物索引

- 综合报告: docs/research-2026-08-iter2/DEEP-RESEARCH-REPORT-2026-08-ITER2.md
- PRD: docs/research-2026-08-iter2/PRD-2026-08-ITER2.md
- 5 份原始研究（~385k 字符）: .ai-bridge/sol/{R1-INTENT,R2-REALGAME,R3-ENGINE,R4-PATCH,R5-AGENT}.md
- 对话链接: docs/research-2026-08-iter2/CHATS.md
- 源码包: udify-src-iter2.zip（29 文件，84,710 字节，SHA-256 ee7fb2218c8ab6eb73126214a8e58a7a9435f3a8bf1431526418147cd0abc592）

## 经验回流（orchestrate-sol-browser skill）

1. **release() 后编码标签页不可 recover**：release 把标签转 handoff，但 coding 标签元数据未持久化时 recover 不回收；编码阶段应避免在 harvest 前对编码标签 release。
2. **setupBrowserRuntime 需手动挂载 globalThis.agent**：sol.boot 前若 agent.browsers 未注入，需手动 setupBrowserRuntime 并赋值。
3. **attach 在新空白标签成功，在活跃研究标签失败**：filechooser 在活跃对话页超时；上传源码包应在新标签 attach 后再 send。
4. **poll 的 chars 计数对长推理有滞后**：DOM 已渲染但 probe 计数未更新时，snapshot 可见真实内容（R1 turn-2 即如此）。
