# Udify iter3 PRD（基于深度研究综合报告）

> status: active | 输入: DEEP-RESEARCH-REPORT-ITER3.md | 基线: iter2（427 passed）

## 北极星

把 iter2 的五个骨架补成真闭环，并打开评测与多 Mod 两层。北极星样例：说"让第一个 Boss 更难但不碰 Hero"，系统用可选 LLM 生成候选、规则裁决、生成 JSON/ini 字节稳定 Patch、经 macOS seatbelt 沙箱执行 R3 工具、审计可验证；评测集能离线对照 heuristic/resolver/llm。

## 五个编码模块（独占路径，可并行）

### N1 — LLM 意图路径真接通
- 独占: udify/core/cognition/llm_intent.py(新), tests/cognition/test_llm_intent.py(新)
- 内容: LLMIntentProposer——Anthropic tool use（TypeAdapter(StructuredIntent) 动态 schema）生成候选；JobLLMBudget（2 次上限/超限降级）；无 key try/except 全降级；候选交 target_resolver 裁决（规则优先、LLM 填空缺）。
- 验收: 无 key 时全降级且测试不触网；有 key 时结构化候选生成（mock）；Boss 翻倍不碰 Hero 仍成立。

### N2 — 跨文件字节稳定 Patch（JSON）
- 独占: udify/core/execution/patch_executor.py(改 _modify_json), tests/core/execution/test_json_stable.py(新)
- 内容: JSON 字节稳定序列化（保留键序/缩进/浮点精度，只改目标字段）；SourceSpan 行级填充 helper。
- 验收: JSON 只改一字段时未改键字节不变；浮点精度不漂移；golden 回归。

### N3 — macOS seatbelt 真沙箱
- 独占: udify/core/tool_gateway/sandbox.py(改), tests/core/tool_gateway/test_seatbelt.py(新)
- 内容: SeatbeltSandbox 用 sandbox-exec 包裹 subprocess（profile 限 allowlist 读写/断网）；ToolGateway 集成（R3+ 经沙箱，fail-closed）；call_approved 走 runner 不绕沙箱。
- 验收: 沙箱拒绝越权写/联网（负向测试）；sandbox-exec 不可用时 R3+ fail-closed；审计仍覆盖。

### N4 — 评测体系与 ModStack 合并
- 独占: tests/bench/(新: cases.py/runner.py/conftest.py), udify/core/mod_manager/mod_manager.py(改 合并检测)
- 内容: >=30 意图评测 case；A/B runner（heuristic/resolver/llm，mock LLM 离线）；ModStack 三路合并冲突检测（复用 ConflictType）；pytest @bench marker + JSON 报告。
- 验收: 评测离线跑产出对照报告；两 patch 改同节点被 ConflictType 检测。

### N5 — miu2d RuntimeProfile 探测
- 独占: udify/core/validation/playwright_probe.py(改), tests/core/validation/test_runtime_profile.py(新)
- 内容: discover_web_root（找 index.html/www/，拒 symlink）；RuntimeProfile 探测器（Playwright 扫 window 全局对象，物化 profile，断言动态生成）；接入 PlaywrightRuntimeProbe。
- 验收: RuntimeProfile 从 fake web build 探测出全局对象；断言从 profile 动态生成；无 Playwright skip。

## 集成顺序

N1/N2/N3/N4/N5 相互独立。N3 改 gateway 与 iter2 的 call_approved 协同（走 runner）。Codex 中心裁决契约。

## 红线

- 沙箱 fail-closed（S4）；miu2d 契约不写死（S2 RuntimeProfile）；LLM 无 key 全降级；测试不触网。
- 不 commit/push/部署/迁移。
