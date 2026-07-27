# Udify 迭代方案 2026-08 —— 产品化：从引擎闭环到产品闭环

> status: **active**（唯一北极星文档；取代 ITERATION-PLAN-2026-07.md，后者转 frozen）
>
> **一句话判断**：7 月北极星（miu2d 引擎闭环）已在本地真实成立——337 测试全绿、10 个 golden case 通过、成果已落库推送。但它只有工程师能触达：跨进程无状态、无 API、无界面、意图理解是关键词表。本轮唯一北极星是把引擎闭环变成**产品闭环**——一个人在浏览器里五分钟走完"意图 → 审阅带证据的计划 → 批准 → 验证 → 可回滚 ModPackage"，并顺手坐实 7 月的三张欠条。

---

## 0. TL;DR

| 维度 | 现状（2026-07-27 实测） | 本轮目标 |
|---|---|---|
| 引擎闭环 | ✅ NL→语义图→file_patch→VFS→静态验证→headless 探针→评分→可回滚（合成样例） | 保持全绿，不动核心 |
| 跨进程状态 | ❌ CLI preview/apply/rollback 依赖同进程 VFS，重启即失忆 | ModJob 状态机 + SQLite durable，崩溃可恢复 |
| API | ❌ 不存在 | 薄 API 8 端点（FastAPI，127.0.0.1，单用户免认证） |
| 前端 | ❌ 0 行 | Next.js 审阅切片：提交/时间线/Plan Diff/Risk/Report/Package |
| 意图理解 | ⚠️ 正则关键词表，LLMClient 悬空 | LLM 结构化输出增强（可选层，无 key 全启发式降级） |
| CI | ⚠️ 首跑红（mypy/playwright，已修复） | 远端持续全绿，覆盖率 62%→70%（向 80% 爬坡） |
| 三张欠条 | CI 未远端绿 / 探针是 headless 模拟 / 样例是合成 ini | 欠条 1 本轮必清；欠条 2、3 在批次 6 清或明确改判据 |

**纪律不变**：能删就删、能复用开源就不自研、能推迟就推迟。前端只做审阅切片，不做 DAG 编辑器、不做 marketplace。

---

## 1. 现状诚实盘点（实测）

- 批次 0-3 全部成果已以 13 个主题 commit 落库并推送（+23,289/−4,775，233 文件）；`main` 337 测试 0.6s 全绿，ruff check+format 全过。
- 首次远端 CI 揭示本地盲区：本机无 mypy，CI 的 blocking mypy 因可选依赖 playwright 无 stub 而红——已用 pyproject override 修复。**这正是"判据 #7 必须以远端 CI 为准"的证据。**
- 四个产品化缺口（按依赖序）：
  1. **durable ModJob**：`ModSession` 不落盘恢复，`udify preview/apply/rollback` 跨进程是摆设（cli.py 的 `self._vfs` 只活在单次进程内）。
  2. **API 缺失**：pipeline 只能 CLI 单发调用，无法被前端消费。
  3. **前端为零**：审阅体验（diff、风险、证据、探针报告）目前是终端彩色文本。
  4. **意图理解纸糊**：`_INTENT_PATTERNS` 正则表 + 关键词命中，"意图驱动"名不副实；LLMClient（真 SDK 代码）无任何运行路径实例化。
- 三张欠条（7 月遗留，欠条不是耻辱，是台账）：
  - 欠条 A：判据 #7"10 case 在 CI 运行"——CI 已存在但需持续远端绿。
  - 欠条 B：判据 #5 被降级为 headless 模拟——miu2d 是浏览器引擎（github.com/luckyyyy/miu2d），真 Playwright 探针可行，`PlaywrightLauncher` 已留口。
  - 欠条 C：从未处理过真实 game_root——benchmarks 的 input_game 是手工 ini。

## 2. 核心诊断

- **D1 价值不可触达**：能力存在但只对写 Python 的人存在。产品闭环 = 把已验证能力搬进浏览器，而不是新造能力。
- **D2 状态是产品的地基**：没有 durable job，就没有"回来继续看"、没有历史、没有审计回放、没有前端可轮询的对象。**先 infra 再界面**。
- **D3 关键词天花板**：启发式意图在 10 个 golden case 内够用，出圈就失效。LLM 增强是把"演示"变"产品"的分水岭，但必须是可选层（红线：本地无 key 必须成立）。
- **D4 审阅体验即信任**：本产品卖的不是"自动改"，是"改得让你敢批准"。diff、风险分、证据链、探针报告的呈现质量 = 产品核心竞争力（竞品调研结论：质量评估层是护城河）。

## 3. 北极星与成功判据

### 3.1 北极星：产品闭环

```
浏览器打开 localhost:3000
  → 选择 miu2d 游戏目录 + 输入"让第一个 Boss 更难，但不要单纯翻倍血量"
  → 提交，看到 Job 时间线逐步推进（感知→规划→待审阅）
  → Plan Diff Viewer：文件级 diff + 每个操作的证据(SourceSpan)与风险分
  → 点击批准 → VFS 应用 → 静态验证 + 运行时探针 → 报告呈现
  → 下载可回滚 ModPackage；点击回滚，checksum 复原
  → 关掉终端重开，Job 历史与状态原样恢复
```

### 3.2 成功判据（逐条可验收）

1. `udify serve` 一条命令起后端；`pnpm dev` 起前端；README 有 5 分钟上手路径。
2. **durable**：任一阶段 kill -9 后端进程，重启后 job 列表、状态、计划、审计链完整恢复，可从 `awaiting_review` 继续。
3. API 8 端点全部有 OpenAPI schema、统一信封、DOMAIN_CATEGORY_DETAIL 错误码，契约测试覆盖。
4. 前端完成北极星全流程，无需终端参与（除启动命令）。
5. 每个 PatchOperation 在 UI 上能看到 SourceSpan 证据与 risk；R2+ 操作必须人工批准才应用（判据继承 7 月 #2/#3）。
6. 回滚经 API 触发，回滚后 graph checksum 与基线一致（继承 7 月 #6）。
7. 远端 CI 全绿常态化：pytest+mypy+ruff+UdifyBench，覆盖率门槛 62→70。
8. 审计回放：`GET /jobs/{id}` 能还原每一步（含每次工具调用的 audit 链）。
9. LLM 增强：设 `ANTHROPIC_API_KEY` 时意图解析走结构化输出且有预算护栏；不设 key 时行为与现在完全一致（337 测试不依赖网络）。
10. 新增代码全部带测试与类型注解，无"幻觉资产"（红线 #10 继承）。

> 判据 2/4/7 是本轮的"不可谈判项"。欠条 B/C 若批次 6 未及清偿，必须在 INDEX 中明文展期，不许静默。

## 4. 技术架构迭代

### 4.1 ModJob 状态机与持久化（ORCH-JOB-01..05 + OBS-01..02）

```
created → perceiving → planning → awaiting_review → applying → validating → packaging → completed
   任意态 → failed → compensating → rolled_back
   awaiting_review → rejected（终态）
   completed → rolled_back（事后回滚，走 reverse patch）
```

- 存储：**stdlib sqlite3（WAL 模式）**，两张表：`jobs`（当前状态快照）+ `job_events`（append-only 事件流，OBS-01 trace schema 即此表）。工件落 `.udify/jobs/<job_id>/`（graph.json / patch.json / vfs 快照 / package.zip / report.json）。
- checkpoint：每个状态迁移后写 checkpoint（ORCH-JOB-02），恢复 = 读最新 checkpoint + 重放未完成步骤（幂等键 `(job_id, op_id)` 预留，为将来 Temporal 留口但**本轮禁 Temporal**）。
- 人工门：`awaiting_review` 即 ORCH-JOB-03 的 pause/resume；approve/reject 是唯一出口。
- 审计：复用 `tool_gateway/audit.py` 链式哈希，job 级 audit chain（ORCH-JOB-04），`infrastructure/audit_log.py` 与其收敛为一套（清理 7 月点名的双实现）。
- 复用不重写：JobRunner 把 `Miu2dClosedLoop` 拆成步进调用，**不改闭环内部逻辑**。

### 4.2 薄 API（API-01..05 + 新增 API-07/08 + SRV-01）

- FastAPI + Pydantic v2（依赖已在 `[server]` extra）。默认绑 `127.0.0.1:8765`，单用户零认证（**新增红线：不做多用户/认证/云部署**）。
- 端点（v0，统一前缀 `/api/v0`）：

| # | 端点 | 语义 |
|---|---|---|
| 1 | `POST /jobs` | game_root + intent → 202 + job_id（后台线程驱动状态机） |
| 2 | `GET /jobs` / `GET /jobs/{id}` | 列表 / 状态+时间线（前端 1s 轮询；**SSE 推迟**，轮询证明不够再上 API-06） |
| 3 | `GET /jobs/{id}/plan` | PatchOperation 卡片 + 文件 diff + risk + SourceSpan 证据 |
| 4 | `POST /jobs/{id}/approve` \| `/reject` | 风险确认门（状态迁移唯一入口） |
| 5 | `GET /jobs/{id}/report` | 静态验证 + 探针 + 意图对齐评分 |
| 6 | `GET /jobs/{id}/package` | ModPackage zip 下载 |
| 7 | `POST /jobs/{id}/rollback`（API-07 新增） | reverse patch + checksum 校验 |
| 8 | `GET /healthz`（API-08 新增） | 版本/引擎可用性 |

- 响应信封 `{success, data, error, meta}`；错误体 = ErrorRecord：`{code: "JOB_STATE_INVALID", message, owner_module, retryable, suggested_action}`（工业蓝图 IFACE 约束 #10，唯一被采纳进 v0 的部分）。
- `udify serve`（SRV-01）：CLI 新子命令，uvicorn 起 app；`--port/--host` 可调但默认本机回环。

### 4.3 前端审阅切片（UI-00 + UI-01..04 + UI-07；UI-05/06 维持不做）

- **选型定案**：Next.js 15（App Router）+ TypeScript strict + Tailwind v4 + TanStack Query v5。**不引** Zustand（当前无复杂客户端态）、ReactFlow（无 DAG 编辑）、Yjs（无协作）。目录 `web/`，pnpm。
- 页面即产品结构：
  - `/` Job 控制台（UI-07 新增）：历史列表 + 新建（目录路径输入 + 意图输入，中英文，UI-01）。
  - `/jobs/[id]`：状态时间线 + 三标签页 = Plan Diff Viewer（UI-02，文件 diff + 操作卡片 + 证据）/ Risk Review（UI-03，风险徽章 + approve/reject 大按钮）/ Report（UI-04，验证+探针+评分），底部 Package 下载与 Rollback。
- API client：手写薄封装（8 个函数 + 信封解包），**不上 openapi-typescript 代码生成**——端点太少，生成器是过早复杂度。
- 视觉基线：暗色工程风、diff 红绿、风险 R0-R4 色阶徽章；组件遵循无障碍基本项（键盘可达、对比度）。

### 4.4 LLM 意图增强（COG-LLM-01..03，新 ID）

- COG-LLM-01：`IntentClassifier` 的 LLM 路径实装——Anthropic SDK 结构化输出（tool/JSON schema 强约束到 `StructuredIntent`），LLM 只产候选，规则层裁决合并；游戏内容/工具输出永远作为数据段传入，不进指令位（7 月 §7.2 三源隔离照搬执行）。
- COG-LLM-02：预算与降级——每 job 最多 2 次调用、输出 token 上限、超时即降级启发式；`ANTHROPIC_API_KEY` 缺失时代码路径完全不触网（CI 无 key 必须全绿）。
- COG-LLM-03：离线 A/B 评测——UdifyBench 增加 `--intent-engine=heuristic|llm` 开关，10 case 对照记录（不进 CI 阻塞，人工触发）。

### 4.5 最小可观测（OBS-01..02 落地即止）

- OBS-01 trace schema = `job_events` 表（job_id/seq/ts/stage/event/payload），API 时间线直接读它——一份数据两用。
- OBS-02 结构化日志 = stdlib logging + JSON formatter，`udify serve` 输出即可采集。**不上** OTel/Prometheus/Grafana（OBS-05/06 维持 P2）。

## 5. 选型定案（同步 ARCHITECTURE-OSS-OPTIMIZED-v3 新增 ADR）

| ADR | 决策 | 一句话理由 |
|---|---|---|
| ADR-v3-006 | Job 持久化 = stdlib sqlite3(WAL) + 文件工件，无 ORM/迁移框架（手管 schema_version 表） | 零新依赖，本地模式红线 |
| ADR-v3-007 | API = FastAPI+Pydantic v2，127.0.0.1 单用户免认证，统一信封+ErrorRecord | 依赖已备；认证是多用户命题，现在是过早复杂度 |
| ADR-v3-008 | 进度通信 = 1s 轮询；SSE(API-06) 推迟到轮询被证明不够 | 最短可用路径 |
| ADR-v3-009 | 前端 = Next.js15+TS strict+Tailwind4+TanStack Query5；无 Zustand/ReactFlow/Yjs | 与既有文档决策一致且做减法 |
| ADR-v3-010 | LLM = 可选增强层：结构化输出、预算护栏、三源隔离、无 key 全降级 | "意图驱动"补真，但本地必须成立 |

## 6. 分批次路线（PR 级）

### 批次 4A：Job 基座（~1 周，P0）

| PR | 任务 ID | 内容 | 验收 |
|---|---|---|---|
| 4A-1 | ORCH-JOB-01 | ModJob dataclass + 状态机 + 迁移表 | 非法迁移抛错；全部迁移路径参数化测试 |
| 4A-2 | ORCH-JOB-05 | SQLite JobStore（jobs+job_events，WAL） | 崩溃模拟测试：写一半重开库不丢已提交事件 |
| 4A-3 | ORCH-JOB-02/04 | checkpoint + job 级审计链（收敛双 audit 实现） | 重启后从 checkpoint 恢复；audit verify 通过 |
| 4A-4 | ORCH-JOB-03 + OBS-01/02 | JobRunner 步进驱动 Miu2dClosedLoop + 人工门 + 事件流 | dry-run 全流程事件序列快照测试；kill -9 恢复测试 |

### 批次 4B：薄 API（~1 周，P0）

| PR | 任务 ID | 内容 | 验收 |
|---|---|---|---|
| 4B-1 | API-01 | app 骨架 + 信封 + ErrorRecord + healthz | OpenAPI 生成；错误码表测试 |
| 4B-2 | API-02/03 | POST /jobs + GET 列表/详情/plan | TestClient 契约测试；后台线程驱动 |
| 4B-3 | API-04/05/07 | approve/reject + package 下载 + rollback | 状态门测试；回滚 checksum 一致 |
| 4B-4 | SRV-01 + MOD-STACK-01..03 | `udify serve` + ModStack 最小接线（已装 mod 列表/冲突检测暴露到 API） | serve 冒烟；冲突 case（golden #9）过 API 复现 |

### 批次 5：前端切片（~1-2 周，P0）

| PR | 任务 ID | 内容 | 验收 |
|---|---|---|---|
| 5-1 | UI-00 | web/ 脚手架 + API client + 布局 | pnpm build 过；healthz 显示 |
| 5-2 | UI-07/01 | Job 控制台：列表+新建+轮询 | 提交后时间线动到 awaiting_review |
| 5-3 | UI-02 | Plan Diff Viewer（diff + 操作卡 + 证据） | golden #1/#2 的 diff 与终端输出一致 |
| 5-4 | UI-03/04 | Risk 面板 + Report 页 + Package/Rollback | 北极星全流程浏览器走通（判据 4） |

### 批次 6：意图真化与欠条清偿（~1-2 周，P1）

| PR | 任务 ID | 内容 | 验收 |
|---|---|---|---|
| 6-1 | COG-LLM-01/02 | LLM 结构化意图 + 预算降级 | 无 key CI 全绿；有 key 手测 3 条圈外意图 |
| 6-2 | COG-LLM-03 | Bench A/B 开关 | 对照报告入 docs |
| 6-3 | REAL-GAME-01/02 | 真实 miu2d 游戏验收（**用引擎自带 demo 资源或 JC 提供的合法拷贝，不自行下载版权资源**） | 真实 game_root 闭环留档（欠条 C） |
| 6-4 | VAL-RUNTIME-06 | 真 Playwright 探针接通（miu2d web build） | 判据 #5 补票或 INDEX 明文展期（欠条 B） |
| 6-5 | 覆盖率爬坡 | 62→70（CI 门槛上调） | CI 全绿 |

## 7. 明确不做（本轮红线）

继承 7 月红线 1-10（Unreal/通用试玩 AI/Neo4j/Temporal/LLM 直写文件/MCP≠安全边界/全 MCTS/LLM 评估替代运行时/文档只减不增/无测试模块），**新增**：

11. **不做多用户、认证、云部署**——API 绑 127.0.0.1，安全模型 = 本机单用户。
12. **不做 DAG 编辑器、marketplace、协作**（UI-05/06 维持 P2/P3）。
13. **不上 WebSocket/SSE**，轮询先行（ADR-v3-008）。
14. **不做 Electron/Tauri 打包**——`udify serve` + 浏览器即产品形态。
15. **LLM 不做 agent 自由发挥**——只在意图解析一个点位，结构化输出，候选身份。

## 8. 文档纪律

- 活跃集轮替：本文取代 ITERATION-PLAN-2026-07.md（转 frozen，历史功绩保留）；活跃集仍为 4 份（本文 + MODULE-ATTACK-MAP-v3 + ARCHITECTURE-OSS-OPTIMIZED-v3 + INDEX）。
- 新任务 ID（API-07/08、SRV-01、UI-00/07、COG-LLM-01..03、REAL-GAME-01..02）已登记进 MODULE-ATTACK-MAP-v3 附录 §21。
- 规则不变：代码为准、文档滞后必须补、不许新开宏大蓝图。

## 9. 执行日志（代码为准，日志滞后必须补）

**2026-07-27（迭代启动即三批连发）**：

- 批次 4A ✅：`udify/core/orchestration/`（mod_job/job_store/job_runner），44 测试。附带修复一个真缺陷：`CDLPatch` 序列化丢失全部 v3 字段（证据链落盘即消失，违反 ADR-v3-004），已补 `PatchOperation.to_dict/from_dict` 完整往返。
- 批次 4B ✅：`udify/api/`（10 端点）+ `udify serve` + `--json-logs`（OBS-02），12 契约测试；serve 冒烟经 healthz 信封验证。
- 批次 5 ✅：`web/`（Next.js 15 工作台），**判据 #4 浏览器全流程实测通过**：提交意图 → 时间线推进 → 审阅关口（DIFF/证据/风险）→ 批准 → 探针 6/6 → ModPackage 下载/回滚。
- 判据状态：#1 ✅ #2 ✅（durable 测试）#3 ✅ #4 ✅ #5 ✅（UI 呈现 SourceSpan+R 档）#6 ✅ #7 ✅（远端 CI 绿，覆盖率门槛待升）#8 ✅ #9 ⬜（批次 6）#10 ✅。
- **实测发现的产品缺陷（记入批次 6 输入）**：
  1. "把Boss的血量翻倍"会把 Hero 的血量也翻倍——关键词引擎不做目标过滤（reference resolution 缺位），正是 COG-LLM-01 要解决的核心样例。
  2. ini 重写产生同值 diff 噪声行（`Defense=10` 一删一增）——patch_executor 的 ini 序列化应保持未修改行字节不变。登记为 `PATCH-SYN-10`（P1）。

## 10. 一页纸总结

- **问题**：能力已验证但不可触达；状态不落盘；意图理解是关键词表；三张欠条。
- **动作**：ModJob+SQLite（地基）→ 薄 API 8 端点 → Next.js 审阅切片 → LLM 可选增强 → 欠条清偿。
- **判据**：§3.2 十条，判据 2（durable）/4（浏览器全流程）/7（CI 常绿）不可谈判。
- **纪律**：红线 15 条；能力不扩圈，体验补到位；每个 PR 有任务 ID、有测试、有验收。
