# Udify iter7 批次 7A 交付报告

日期: 2026-08-13 | 范围: **M1 可达性门禁 + M4 补丁保真**（PRD-iter7 §3 批次 7A）
基线: 800 passed / **1 failed** / 2 skipped → 交付后 **842 passed / 0 failed** / 2 skipped
授权边界: 未 commit / 未 push / 未部署

---

## 1. 交付内容

### M1 — 可达性门禁（FIT-01..04）

| 产物 | 说明 |
|---|---|
| `scripts/check_reachability.py` | 入口点可达性检查，stdlib `ast` + BFS，零新依赖 |
| `.udify-reachability.toml` | 基线 allowlist，147 条，2026-11-13 到期 |
| `.github/workflows/ci.yml` | 新增 blocking 步骤（置于 ruff check 之后） |
| `tests/infrastructure/test_reachability.py` | 23 测试 |

**两层判定**（粒度经实测校准，缺一不可）：

1. 模块层：从 `udify.cli` / `udify.api.app` 经 import 图 BFS，不可达即孤儿。
2. 符号层：可达模块内的公共顶层函数/类/方法，名字从未被任何模块引用即孤儿。

**为什么符号层不可省**（实测数据）：

| 模块 | 被 import 次数 | 模块层判定 | 真实情况 |
|---|---|---|---|
| `gate_orchestrator` | 0 | 孤儿 ✅ | 正确 |
| `target_resolver` | 0 | 孤儿 ✅ | 正确 |
| `runtime_probe` | 4 | 可达 | 但 `run_by_engine` 是死方法 ❌ 漏判 |
| `sandbox` | 2 | 可达 | 但 `execute_sandboxed` 是死方法 ❌ 漏判 |

### M4 — 补丁保真（PATCH-SYN-10）

修复 6 条序列化路径的字节保真（全部复用文件内已有的 `_split_keep_eol`，未新造工具）：

`_add_ini_section`、`_remove_ini_section`、`_modify_obj`、`_add_obj_entry`、`_remove_obj_entry`、`_execute_dsl_insert`。

根因：`content.splitlines()` 丢弃行尾信息，`"\n".join()` 把 CRLF 归一化成 LF 并吞掉尾换行。

**最严重的表现**：`_remove_ini_section(src, "不存在的section")` 这个**零改动操作**会让整个文件产生字节差异。这直接击穿 M3-PR4 依赖的 pass-to-pass 回归断言——若无关内容的字节都会变，"未修改部分逐字节不变"根本无法成立。

`tests/core/execution/test_patch_fidelity.py`：18 测试，LF/CRLF 参数化。

### 附带：M5-PR1 的**部分**修复

开工前即存在的红测试 `test_proposer_budget_exhausted_emits_budget_trace` 已转绿。

根因：`is_available()` 把「无 key」与「SDK 未安装」合并判定，且该分支排在预算检查之前——本机未装 `anthropic`，因此即使设了 key 也返回 `NO_KEY`，**预算耗尽在生产中永不可见**。

修复：预算检查前置（预算为 0 时无论有无凭证都不会发起调用，`BUDGET_EXHAUSTED` 才是可操作原因）。

> **这不是 M5-PR1 的完整交付**。单值 `degradation_reason` 仍会互相掩盖（无 key + 预算耗尽只显示一个）。完整的正交原因集合仍欠 M5-PR1（批次 7C），已在代码中以 `ponytail:` 注释标注天花板与升级路径。

---

## 2. 门禁验证证据

| 项 | 命令 | 结果 |
|---|---|---|
| 全量测试 | `pytest tests/ -q` | **842 passed, 2 skipped, 0 failed** |
| 可达性（基线态） | `scripts/check_reachability.py` | 退出码 0：133 模块，89 可达，147 已知孤儿在 allowlist |
| 可达性（新增孤儿） | 临时新建无调用者模块 | 退出码 **1**，精确报出 |
| 可达性（过期条目） | 改一条 expires 为 2020-01-01 | 退出码 **1**，报出过期项 |
| ruff check | 我触碰的 5 个文件 | All checks passed |
| ruff format | 我触碰的 5 个文件 | 5 files already formatted |
| mypy | `check_reachability.py` | Success: no issues |

**校准证据（门禁可信度的核心）**：

- 正对照 4/4：`gate_orchestrator`、`target_resolver`、`run_by_engine`、`execute_sandboxed` 全部抓到。
- 负对照 0 误报：`Miu2dClosedLoop`、`JobStore`、`JobRunner`、`create_app` 均未被误标。
- 误报源排查：`getattr` 仅用于数据字段取值（`getattr(op, "payload")`），非方法动态派发，不构成误报源。

误报消除过程（两轮校准，从 257 → 147）：

1. 跳过接口桩体（`...` / `pass` / 纯 docstring）——Protocol/ABC 的方法声明是契约不是调用点。
2. 同模块引用计入"已使用"——`cmd_mod` 只在 `cli.py` 的 `commands` 字典里被引用，但那条路径是真的。

---

## 3. 推翻 PRD 假设的实测发现

**PRD 假设 6 个孤儿，实测 147 个（44 模块 + 103 符号），约 25 倍。**

PRD §0.1 的表是对 iter5/iter6 点名符号的抽样；门禁建成后全量扫描才看清真实规模。不可从 CLI/API 到达的整片区域包括：`tool_gateway`、`ingestion`、`real_merge`、`evaluation`、cognition 的 LLM 栈。

**对 PRD 的影响**：§2「六个模块全接线」的目标不成立。iter7 只可能清掉主路径关键路径上的那批，其余冻结进基线由季度复审驱动。已回写 PRD §0.1。

孤儿簇现象被实证：`agent_loop` → `tool_gateway` 有真实 import，但 `agent_loop` 自身不可达，整簇悬空。这正是朴素 import 计数会漏判、而入口点可达性能抓住的情形。

---

## 4. 未完成与风险（不改写成功定义）

1. **147 条孤儿仅冻结未清偿**。基线 2026-11-13 到期，到期未清则 CI 红。iter7 M2/M3 只负责主路径关键项。
2. **M5-PR1 只做了一半**：降级原因仍是单值，正交集合欠 7C。
3. **74 个文件 `ruff format` 未过**——前序会话遗留的未提交存量（经 stash 探针验证：HEAD 干净，115 文件全部已格式化）。不在 7A 范围，但会阻塞 CI，需要一次独立的格式化提交。
4. **可达性符号层是保守近似**，基于 AST 标识符引用而非真调用图：会把"提到名字但没真调用"算作已使用（可能漏报），但极少误报。这是刻意取舍——门禁的价值在零误报，否则会被 allowlist 淹没。
5. 未 commit/push；M2/M3（接地与闸门接线）未开始。
