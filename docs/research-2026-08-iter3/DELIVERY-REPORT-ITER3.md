# Udify iter3 交付报告

日期: 2026-08-05（iter2 当日续）| 模式: orchestrate-sol-browser（研究→PRD→编码→整合）
基线: iter2（427 passed）→ iter3（452 passed, 2 skipped；+25 新测试）

## 管线全流程（沿用 iter2 方式，第二轮循环）

| 阶段 | 实证 |
|------|------|
| 预检 | REGIME=FAST |
| 研究设计 | 5 主题（S1-LLMPATH/S2-MIU2D/S3-CROSSPATCH/S4-SANDBOX/S5-BENCH），深化 iter2 边界 + 打开评测/多 Mod |
| 多轮研究 | 5×Sol R1+R2（attach 不稳未走 R3），~181k 字符产物 |
| 综合 | DEEP-RESEARCH-REPORT-ITER3.md |
| PRD | PRD-ITER3.md，5 模块（N1-N5）独占路径 |
| 分布式编码 | 5×Sol 编码标签 dispatch + attach；harvest 中断（iter2 同款），lead 接管整合 |
| 中心整合 | Codex 实现 N1-N5，全门禁绿 |

## 五个交付模块（已实现、已测试、已整合）

### N1 — LLM 意图路径真接通
- 新增 udify/core/cognition/llm_intent.py：LLMIntentProposer（Anthropic tool use 候选）+ JobLLMBudget（2 次/超限降级）+ merge_intent（规则优先、LLM 填空缺）。无 key try/except 全降级、不触网。
- tests/cognition/test_llm_intent.py：6 测试。无 key 全降级不触网；预算追踪；规则优先合并；malformed 响应处理。

### N2 — 跨文件字节稳定 Patch（JSON）
- 修改 udify/core/execution/patch_executor.py：_modify_json（保留键序/缩进/浮点精度，只改目标字段）+ _detect_json_indent。
- tests/core/execution/test_json_stable.py：3 测试。嵌套修改保留键序/缩进；浮点不漂移；只目标键变。

### N3 — macOS seatbelt 真沙箱（fail-closed）
- 修改 udify/core/tool_gateway/gateway.py：新增 call_sandboxed（R3+ 经沙箱，fail-closed 不降级）。修复 iter2 call_approved 绕沙箱缺口。
- tests/core/tool_gateway/test_seatbelt.py：6 测试。含真 SandboxExecutor 跑 /bin/echo 验证 seatbelt 后端；fail-closed 断言；R4 不放行；审计覆盖。

### N4 — 评测体系 + ModStack 合并
- 新增 tests/bench/cases.py（30 case：20 miu2d + 10 圈外）+ runner.py（A/B 对照 + mock LLM 离线 + ModStack 合并冲突检测复用 ConflictType）。
- tests/bench/test_bench.py：7 测试（@bench marker）。A/B 结果：resolver target_precision=1.0 vs heuristic 0.067（证明 iter2 M2 消除误伤）。

### N5 — miu2d RuntimeProfile 探测
- 修改 udify/core/validation/playwright_probe.py：discover_web_root（找 index.html/www/，拒 symlink）+ RuntimeProfile（扫描 window 全局对象，不臆造固定契约）+ assertions_from_profile（动态生成断言）。
- tests/core/validation/test_runtime_profile.py：3 passed + 1 skip（Playwright 未装）。

## 门禁

| 门 | 结果 |
|----|------|
| pytest tests/ -q | 452 passed, 2 skipped |
| ruff check（iter3 文件） | All checks passed |
| 回归 | iter2 的 427 全绿，无破坏 |

## 关键研究证据回流（A/B 评测数据）

A/B 对照证明 iter2 价值：
- heuristic: target_precision 0.067（几乎全误伤）
- resolver(iter2 M2): target_precision 1.0（精确锁定，零误伤）
- mock_llm: target_precision 1.0

## 诚实边界

1. Sol 编码 harvest 中断（iter2 同款 attach/release 不稳），lead 实现整合。
2. S4 沙箱：seatbelt/restricted 后端在本机可跑（/bin/echo 测试通过），但 profile 的越权写/联网拦截需实机 seatbelt 环境深度验证（当前 fail-closed 测试用 FakeSandbox）。
3. S2 miu2d：RuntimeProfile 探测用合成 web build；真 miu2d 闭环需 JC 合法 demo（欠条 C 仍待资源）。
4. LLM 路径：无 key 时全降级（测试证明不触网）；有 key 走通需手测（不进 CI）。
5. 未 commit/push/部署/迁移（未授权）。

## 产物索引

- 综合报告: docs/research-2026-08-iter3/DEEP-RESEARCH-REPORT-ITER3.md
- PRD: docs/research-2026-08-iter3/PRD-ITER3.md
- 研究（~181k）: .ai-bridge/sol/{S1-LLMPATH,S2-MIU2D,S3-CROSSPATCH,S4-SANDBOX,S5-BENCH}.md
- 对话链接: docs/research-2026-08-iter3/CHATS.md
- 源码包: udify-src-iter3.zip（30 文件，85,991 字节）
