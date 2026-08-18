# iter7 研究与 PRD（2026-08-13）

**主题**：接线迭代——让已建成的能力真正进入主路径

## 阅读顺序

1. `RESEARCH-DESIGN-iter7.md` — 为什么是 iter7：孤儿簇的实测取证与六个研究主题
2. `DEEP-RESEARCH-REPORT-iter7.md` — 研究发现（工具能力边界、接地算法、模型路由、SSE、验证纪律、补丁保真）
3. `PRD-iter7.md` — **主交付物**：六模块、PR 切分、接口契约、验收标准

## 一句话结论

六个模块有实现、有测试、有类型注解、ruff/mypy 全过，**生产调用者为零**。iter7 零新模块，全部接线，并建立让这个失效模式在结构上不可能再发生的门禁。

## 实测基线

- 测试：800 passed / **1 failed** / 2 skipped（iter6 交付宣称 801 全绿）
- 代码：`udify/` 30,787 行 / `tests/` 11,362 行
- 孤儿符号：`GateOrchestrator`、`run_gates`、`resolve_targets_grounded`、`run_by_engine`、`process_intent_timed`、`execute_sandboxed`

## 七条关键研究纠正

1. `import-linter` 与 `vulture` 均无法检出孤儿簇——前者是禁止型约束语言，后者以符号级引用为判据而簇内互引即"已使用"。
2. 「第一个 Boss」不需要 LLM——它是两阶段确定性算法（语义过滤 + 子集内序数选择）。
3. 本地路径选 llama.cpp 而非 MLX——MLX 吞吐更高但核心栈无 GBNF 等价物。
4. SSE 的 `id:` 直接映射 `job_events.seq`——断连补发零新增存储。
5. 「格式税」主要来自 prompt 层而非采样约束——不应因性能顾虑放弃约束解码。
6. `PATCH-SYN-10` 是 P0 而非 P1——diff 噪声使 pass-to-pass 回归断言无法成立。
7. 降级原因必须是集合而非单值——单值短路导致 BUDGET_EXHAUSTED 被 NO_KEY 永久掩盖。
