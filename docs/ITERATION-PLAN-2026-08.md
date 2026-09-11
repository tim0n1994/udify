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

## 11. 批次 5B 执行级设计与结果（2026-07-29）

> 状态：**已实现并完成本地阻塞门禁**。本节保留编码前施工图，并把真实运行结果、mock/real 边界和剩余风险一起落账；“脚本已配置”不等于“门禁已运行”。

### 11.1 目标和边界

- 目标：把已有 `/` 与 `/jobs/[id]` 从可演示切片升级为可配置、可审阅、可阻塞验证的本地产品工作台。
- 不扩展安全边界：风险档位、批准资格、状态迁移、路径策略和工具决策仍完全由后端拥有；前端 feature 只决定是否展示。
- 不做 Storybook、Zustand、ReactFlow、SSE/WebSocket、认证或云部署；它们不是当前两个页面的最小必要依赖。

### 11.2 模块和状态所有权

```text
web/config/defaults.ts           经审计的 v1 安全默认值
web/lib/config/*                 Zod 契约、env/local preference 合并、诊断
web/lib/api/*                    Zod envelope/data decode、query keys、polling policy
web/components/ui/*              Button/Input/Dialog/Tabs/Skeleton/Empty/Error
web/components/shell/*           AppShell/SidebarNav/TopStatus
web/features/jobs/console/*      创建表单、过滤、表格、selected-row inspector
web/features/jobs/review/*       file rail、line diff、operation/evidence、timeline/checklist/actions
web/test/*                       Vitest + Testing Library + MSW（仅测试包图）
web/e2e/*                        Playwright 真浏览器；默认使用明示 mock API
```

| 状态 | 唯一事实来源 | 前端权限 |
|---|---|---|
| Job/plan/report/risk/checklist | FastAPI + JobStore + 工件 | decode、查询、展示；不本地重算准入 |
| 当前审阅 tab | URL `?tab=` | 读写 URL，使刷新/复制可复现 |
| 选中文件/操作 | Review workspace local state | 临时视图状态，不持久化 |
| density/default tab | versioned local preference | 只影响展示，坏数据可重置 |
| 品牌/导航/轮询 | defaults + checked public env | 受 v1 Zod 白名单约束 |

### 11.3 配置加载与失败语义

```text
frozen defaults
  -> NEXT_PUBLIC_UDIFY_CONFIG 完整 JSON 解析/字段白名单
  -> NEXT_PUBLIC_UDIFY_API 回环 HTTP URL 单独校验
  -> localStorage(udify.display.preferences) v1
  -> resolved display config + diagnostics[]
```

- env JSON 非法：整个 env override 不进入 resolved config，使用安全默认值并在 UI/测试诊断中保留原因。
- local preference 旧版/损坏：只忽略该层，不污染 build config；用户可一键重置。
- API 任何不符合 envelope/data schema 的 2xx/4xx 响应都转为可诊断 `ApiError`，不让 `undefined` 渗入组件树。

### 11.4 组件和主流程

1. 任务控制台：`CreateJobForm -> JobFilters -> JobTable -> JobInspector`；搜索覆盖 intent/game_root，状态可筛选，row 可键盘选中/打开。
2. Job 审阅：`JobHeader -> URL ReviewTabs -> FileRail + DiffPane + Timeline/Checklist -> OperationTable`；操作证据点击反向定位文件和行。
3. 状态动作：批准、拒绝、回滚均走可访问 confirm dialog；对话框展示文件数、操作数、最高风险和静态阻塞，最终仍以 API 响应为准。
4. 已完成任务暴露 package URL 与 rollback；failed/rejected/rolled_back 均是显式终态，不显示伪进度。

### 11.5 测试金字塔和迁移顺序

1. 先修 JobStore/lifespan 关闭协议：统一 `RLock`，`transition` 单事务，executor 等待已运行 future 后才 close。
2. 再建配置与 API decode 纯函数层，用 Vitest/MSW 锁定坏配置、坏信封、旧 preference 和 polling policy。
3. 最后迁移页面到专用 feature 组件，每步保持 `lint + typecheck + unit + build`可运行。
4. Playwright desktop/mobile 以 route interception 做可重复 mocked E2E；真本地 FastAPI 流程另行运行并与 mocked 证据分栏。

门禁：Python 子集/全量；Web ESLint 9、TypeScript strict、Vitest、Next production build、Playwright Chromium desktop/mobile。CI 中的 mock 不进入 production import graph。

### 11.6 实现结果和证据

- `web/lib/config/*` 已实现 v1 Zod 配置契约：默认值 → `NEXT_PUBLIC_UDIFY_CONFIG` → 回环 `NEXT_PUBLIC_UDIFY_API` → versioned local display preference；非法层被整层丢弃并产生可见诊断。Mods/系统不能在没有真实路由时被配置为启用。
- `web/lib/api/*` 已实现统一 envelope/data 运行时解码、`ApiError`、query key 和页面可见性感知轮询；production 模块不 import MSW。
- `/` 已迁移为任务控制台（创建、搜索、状态筛选、键盘打开、选中预览），`/jobs/[id]` 已迁移为 URL 驱动三标签审阅台（文件 rail、带行号 diff、操作/证据、时间线、检查表、批准/拒绝/回滚确认）。loading/empty/error/terminal 均有显式状态。
- OSS 采用：Zod 4、Radix Tabs/AlertDialog/Slot、jsdiff、Lucide、CVA/clsx/tailwind-merge、Vitest/Testing Library/MSW、Playwright；不引入 Storybook，因为当前只有两个页面，Vitest 状态夹具与阻塞 E2E 已覆盖关键状态，Storybook 会增加独立构建与版本维护面。
- SQLite 并发缺陷已修复：JobStore 的同一 connection 在所有读/写/事务/关闭上统一走连接级 `RLock`；状态快照与事件追加为单事务；API shutdown 先停止接收、等待/取消 futures，再关闭 store。原 `test_plan_not_ready_404` 进程崩溃循环修复后 40/40 通过。

### 11.7 真实门禁记录

| 层 | 命令 | 结果 | 验证类型 |
|---|---|---|---|
| Python style | `ruff check udify/ tests/` + `ruff format --check udify/ tests/` | 通过；115 files formatted | real local |
| Python type | §8 指定 15 文件 `mypy --follow-imports=silent` | 0 issue | real local；全包历史 strict 未宣称通过 |
| Python test | `pytest tests/api tests/core/orchestration -q` / `pytest tests/ -q` | 59 / 399 passed | real local，Python 3.13.13 |
| Web lint/type | `pnpm lint` / `pnpm typecheck` | exit 0 | real local |
| Web supply chain | `pnpm audit --prod --audit-level high` | 0 vulnerability；exit 0 | real npm advisory database |
| Web unit | `pnpm test --run` | 9 files、31 tests passed | Vitest/RTL/MSW |
| Web build | `pnpm build` | Next 15.5.22 通过；`/` 152 kB、job 页 177 kB first load | production build |
| Web E2E | `pnpm test:e2e` | Chromium desktop/mobile 4/4 passed | mocked API route interception |
| 产品链路 | create → review → approve → validate → package | 探针 6/6、package link 可用、browser console 0 warning/error | real FastAPI + real browser |
| 移动端 | 390×844 job review | `innerWidth=scrollWidth=bodyScrollWidth=390` | real browser |

### 11.8 未完成与风险（不改写成功定义）

1. 当前真实后端 PatchOperation 的 SourceSpan 只定位到文件，`line_start/line_end` 为空；UI 明示“文件级证据（无行号）”并显示 `可定位 SourceSpan 0/2`，没有伪造行号。精确行证据仍是后端数据质量债。
2. “Boss 攻击力翻倍”真实样例仍错误修改 Hero；属于既有 COG-LLM/reference resolution 缺口，批次 5B 只把错误清晰呈现，没有在前端重算语义。
3. ini 重写仍产生同值 remove/add 噪声；`PATCH-SYN-10` 未在本批修复。
4. E2E 是明确的 mocked API；另行完成的真实本地后端链路验证不等同于远端 CI 或真实商业游戏验收。Storybook、认证、SSE、远端部署仍在本批边界外。

### 11.9 独立静态审查闭环（2026-07-29）

- 任务筛选后，Inspector 只允许从 filtered rows 中保留 selection；隐藏的旧 selected ID 会回退到第一条可见任务或 null。
- public API base 现在拒绝 credentials、非根 path、query、fragment、HTTPS 和非 loopback host；端口仍允许。
- localStorage getter/read/write/remove 任一步抛出 SecurityError/QuotaExceeded 时，ConfigProvider 保留内存安全配置并追加 `CONFIG_LOCAL_UNAVAILABLE` 可见诊断；reset 不再向组件树抛错。
- 上述回归加入 Vitest 参数化/组件测试；最终 Web 门禁为 9 files、31 tests，build 与 mocked E2E 复跑通过。

### 11.10 供应链与测试资源复核（2026-07-29）

- npm 当前无 Next 15.5.23，15.5.22 仍是 15.5 最新 patch；其 manifest 仍声明 `postcss 8.4.31` 与 optional `sharp ^0.34.3`，单升 Next 无法清除新公告。
- `pnpm.overrides` 只定向替换 Next 的传递依赖：`postcss 8.5.25`（patched ≥8.5.18）与 `sharp 0.35.3`（patched ≥0.35.0）。sharp 0.35 的 Node 下限为 20.9，因此项目/CI 明示 Node ≥20.9 / Node 22。
- `pnpm audit --prod --audit-level high` 从独立验收的 1 moderate + 3 high 变为 `No known vulnerabilities found`；CI 在 frozen install 后阻塞运行 `pnpm audit:prod`。
- Next 上下文真实加载 `sharp 0.35.3 / libvips 8.18.3`，随后 lint、typecheck、31 tests、production build 与 4 E2E 全绿，证明 override 不只让审计静音。
- API/编排测试的 `store` fixture 原先 return 而不 teardown，两个 reopen 测试也漏关第二个 store。改成 yield/finally 与局部 finally 后，59 / 399 tests 在 `ResourceWarning=always` 且 `PytestUnraisableExceptionWarning=error` 下只剩 1 条第三方 Starlette deprecation；覆盖率 64.00%。生产契约未变。

### 11.11 AGENTS.md 重构与门禁复核（2026-09-03）

- 根 `AGENTS.md` 重构为 9 节：技术栈表移入新 §3，web 专属门禁契约逐字迁入新建 `web/AGENTS.md`（原 189–204 行），mypy 15 文件清单固化为 `scripts/typecheck.sh`（与 CI 清单一致）。技术栈表、D1–D3、快照模块表、JC 协作风格等段落与 HEAD 逐字节一致。
- Python 门禁（.venv）：`ruff check udify/ tests/` exit 0；`bash scripts/typecheck.sh` exit 0；`pytest tests/ -q` 860 passed / 2 skipped。裸 `python3`（Homebrew）因 GHSA 受影响 chromium 环境确定性失败 4 个 runtime-probe 用例（`Page.wait_for_function` 15s 超时），属与本变更无关的既有环境问题，已在 AGENTS.md 记录。
- 供应链：新增 `pnpm.overrides["postcss>nanoid"]="3.3.18"`（pnpm 10 拒绝三级选择器，无法写 `next>postcss>nanoid`），清除新公告 GHSA-2v37-7h3g-55p8；lockfile diff 仅 nanoid 3.3.16→3.3.18 与 override 记录。`audit:prod`、lint、typecheck、Vitest 49、production build 复跑全绿。
- E2E 根因修正：3000 端口被用户另一项目（gesture-synth-weld vite dev server）占用，此前 8 例全部打到外部应用而失败。`playwright.config.ts` 增加 `E2E_PORT` 环境变量覆盖端口（默认仍 3000，行为不变）；`E2E_PORT=3100 pnpm test:e2e` 8/8 passed（desktop+mobile Chromium，exit 0），Playwright 自建 production server 复验。

## 12. iter8：真实可审阅闭环（2026-09-08）

状态：**本轮 A1–A10 本地验收完成（2026-09-09），代码未提交、未发布**。本节是当前执行依据；前文与 iter2–iter7 报告的测试数字均为历史快照，不能充当本轮通过证据。本轮在既有四份活跃文档内维护设计，不增加新的宏大蓝图。

### 12.1 回顾与选择

Udify 的长期使命仍是让非技术用户用意图驱动内容改造。当前产品承诺是本地浏览器里的“表达愿望 → 审阅 → 批准 → 获取可撤回的包”，本轮继续兑现这个承诺。

2026-09-08 从当前代码直接确认的差距：

| 差距 | 当前证据 | 本轮处理 |
|---|---|---|
| iter7 接地修复与浏览器入口不是同一条链 | `pipeline.py` 的通用规划接地测试与 `JobRunner → Miu2dClosedLoop.plan` 分离 | 在实际 miu2d API/浏览器路径验收目标与字段，不能借 RPGMV 单测证明产品正确 |
| 闸门接入但事实输入不真实 | `job_runner.py` 存在 `ambiguous=False`、`sandboxed=True`、`dependency_conflicts=[]` | 从实际规划与执行工件取得事实；未运行的检查不能作为已通过证据 |
| 运行覆盖等级可能来自引擎名 | 无 Godot 探针仍可能标为 `NATIVE_HEADLESS`，RPGMV 静态代理可能标为自动运行 | 等级由实际启动与观测结果决定；静态检查、未运行、运行失败分开 |
| 前端进度能力未形成产品闭环 | `useJobProgress`/`JobProgressPanel` 存在，但真实审阅页面未消费；进度与持久审计存在两种来源 | 产品使用持久 `job_events`，SSE 与轮询消费同一事件流 |
| 原游戏与包的操作语义需要说清 | JobRunner 写 VFS 与任务工件，不安装到原 `game_root` | 明示生成包、验证覆盖、撤回包；不能把撤回下载工件说成已还原用户游戏 |
| 旧完成声明不足以证明恢复与撤回 | 模块测试、报告与浏览器实际入口之间缺少同一任务证据 | 用真实本地 HTTP、浏览器、重启及 ZIP 字节检查验证完整任务 |

选项比较：多引擎扩展可以兑现更广场景，但当前入口尚需补全；清理全部孤儿可以改善代码结构，但不能单独证明改对内容。本轮选择把实际 miu2d 入口做成可解释、可恢复的完整闭环。RPGMV 的既有能力保留，其浏览器产品化另列后续任务，不宣称本轮完成多引擎统一。

### 12.2 本轮产品目标与边界

用户从浏览器提交 miu2d 目录与意图，系统先确定语义类别、目标和修改字段。目标唯一时给出精确 Patch；目标歧义时展示候选并持久等待澄清。用户批准后只生成任务目录中的 ModPackage，报告明确静态检查与真实运行证据；撤回后不再能从 API 下载该任务的包。刷新、断连与后端重启不丢失审阅、澄清或撤回状态。

原始 `game_root` 在感知、预览、批准、验证、打包、撤回的全过程逐字节不变。这里的“撤回”是撤销本地任务的包交付资格和相关工件状态；已经被用户另存的 ZIP 无法远程收回，系统也不声称安装或还原了原游戏。

本轮继续使用本地单用户 FastAPI、SQLite、Next.js 与现有适配器。不新增云服务、认证、市场、DAG 编辑器或自由执行的 LLM agent。SSE 的采用在本节明确更新前文红线 13/ADR-v3-008 的“先轮询”阶段决策：后端已具备事件端点，本轮将它接入真实 UI，并保留同源持久事件轮询作为回退。

### 12.3 架构与状态契约

主链路：`浏览器 → API → JobRunner → Miu2dClosedLoop → Patch/VFS → 验证工件 → Package`。目标解析与澄清结果必须穿过这条链，不在前端重新猜测，也不通过另一个引擎的测试替代。

| 契约 | 约束与失败语义 |
|---|---|
| 目标选择 | 先按语义类别筛选，再在类别内应用序数、名称或最高级选择；显式字段与倍率进入计划；不得退回全部角色或任意首个节点 |
| 澄清 | 歧义产生结构化候选与原因，暂停任务；候选选择必须对应原任务与当前图版本；缺失、失效或非法选择不应用 Patch |
| 持久状态 | 澄清请求、选择结果、审阅计划、批准与撤回状态落盘；状态迁移和审计事件保持事务一致；重启不能把等待用户输入的任务自动批准 |
| 批准与恢复 | 批准依据已审阅的计划和图版本；原游戏漂移拒绝应用；重复批准和恢复不能产生重复副作用，也不能绕过当前状态门 |
| 交付证据 | 报告区分生成包、静态检查、运行验证和沙箱事实；没有进程启动与观测证据时不能显示原生或浏览器运行通过；不适用与未知不伪装成功 |
| 包与撤回 | 包路径与可下载资格以持久任务状态为准；撤回完成后，即使旧文件仍在磁盘或后端重启，旧下载端点也拒绝交付；失败中断可以恢复完成撤回 |
| 事件源 | `job_events` 是生命周期事件唯一权威来源；SSE 的 `id` 和轮询游标均使用持久 seq；同一任务按 seq 单调消费、去重、补发 |
| UI 生命周期 | 从历史列表进入、刷新、后台任务完成、SSE 断连、轮询回退、批准、拒绝与撤回都更新同一任务；终态和等待输入状态不遗留无意义的请求循环 |
| 兼容 | 保留现有 API 信封和结构化错误；新增字段在 Python 与 Zod 边界同步；旧任务无新增证据时展示未知，不补造历史事实 |

澄清与撤回的具体端点、状态枚举以及报告字段以实现时的 API schema 为准，必须由后端与前端共同收敛，不能出现两套状态名称。新增状态需要同时更新持久化读取、迁移表、恢复逻辑和 UI 状态分支。

### 12.4 并行工作流与所有权

| 工作流 | 主要代码范围 | 必须交付的用户行为 | 依赖 |
|---|---|---|---|
| I8-INTENT | `miu2d_pipeline.py`、现有目标解析与规划模块、对应测试 | 真实入口的类别过滤、序数/字段/倍率、结构化歧义结果 | 与 I8-JOB 协调规划结果契约 |
| I8-JOB | `orchestration/job_runner.py`、`mod_job.py`、`job_store.py`、相关 API schema | 持久澄清、批准状态门、诚实报告、可恢复包撤回 | 消费规划结果；给 API/UI 提供稳定状态 |
| I8-EVENT | `api/job_events.py`、事件路由及契约测试 | 同一 `job_events` 的 SSE/轮询、续传与去重 | 与 I8-JOB 协调状态事务；避免重复事件存储 |
| I8-WEB | `web` API 契约、任务审阅/进度/报告组件与测试 | 候选澄清、真实覆盖提示、实时生命周期、撤回后的正确操作状态 | 使用已确认 API 契约；不重算后端业务事实 |
| I8-QA | 真实本地服务与浏览器验收、工件比对 | HTTP → 浏览器 → ZIP 精确修改 → 重启 → 撤回的证据 | 核心链路集成后执行；单元测试可先行 |
| I8-DOC | 本节与技术索引 | 当前状态、验收台账、未完成义务 | 按已观察结果回写，不提前打勾 |

并行实现按文件所有权隔离；共享 `JobRunner`、状态模型与 API 契约由对应负责人统筹。每批集成包含接线和验证，不再拆成“本轮写逻辑、下一轮接主路径”。最终由主调度检查真实入口、合并差异与全链路证据。

### 12.5 验收矩阵

以下是本轮必须取得的证据，不是已经执行的测试报告。准备包含玩家、普通敌人和至少两个 Boss 的 miu2d 测试资产，保留原始字节快照；资产来源及是否为合成 fixture 必须注明。

| ID | 场景 | 通过条件与权威证据 |
|---|---|---|
| A1 | 真实 HTTP 创建“第一个 Boss 攻击力翻倍” | 实际 JobRunner 产生的计划只选第一个 Boss 的攻击字段；玩家、普通敌人与其他 Boss 不被修改；同时覆盖类别内排序而非全局首项 |
| A2 | 字段与约束 | 明确的血量、攻击、倍率和否定约束不会被默认动作覆盖；无法可靠承载的意图进入澄清或明确失败，不悄悄生成另一种修改 |
| A3 | 歧义与恢复 | 浏览器展示候选；刷新和重启后同一任务仍等待选择；有效选择后进入审阅；非法/过期候选与未澄清批准被拒绝 |
| A4 | 真实交付与字节 | 浏览器批准并下载真实 ZIP；解压验证目标字段值，非目标文件及未修改部分保持字节；原 `game_root` 全文件 checksum 从始至终不变 |
| A5 | 证据真实性 | 静态成功但未启动运行时、缺探针、验证失败等场景报告/UI 正确区分；无运行、沙箱或依赖检查证据时不显示已通过对应检查 |
| A6 | 进度与断连 | 真实 API 的 SSE 与轮询读取同一持久事件；断连续传不漏状态、不重复展示；SSE 失败可轮询完成；浏览器真实页面挂载与状态更新有证据 |
| A7 | 批准恢复与漂移 | 重新打开服务可恢复待审阅及中断任务；重复批准不重复副作用；审阅后修改游戏源数据会被版本守卫拒绝 |
| A8 | 撤回与恢复 | 浏览器撤回后下载不可用；旧下载 URL 在服务重启后仍拒绝；中断撤回可以恢复；界面不宣称已回收用户另存的文件或修改原游戏 |
| A9 | 浏览器完整流程 | 真实 FastAPI 与真实浏览器完成创建、澄清、审阅、批准、报告、下载、历史恢复、撤回；desktop/mobile 无关键控件遮挡；不能仅用 mocked route 证明 |
| A10 | 回归门禁 | 按当前 `AGENTS.md`/`web/AGENTS.md` 运行相关测试、Python lint/typecheck/full pytest、可达性门禁及 Web lint/type/unit/build/E2E；每条记录实际命令、退出码和证据路径 |

不把 Python 测试数量增加视为产品验收。A1–A9 必须能追溯到实际入口和同一任务的计划、状态、事件及工件；窄范围测试只能证明对应边界。远端 CI 需要独立观察，不能由本地绿灯推断。

### 12.6 进度与证据台账

2026-09-09 实跑台账。浏览器资产是仓库自建合成 miu2d fixture，不是真实商业游戏；运行的是实际 CLI/FastAPI、SQLite 与 Next.js 生产构建，没有 mock 产品执行路径。

| 项目 | 当前状态 | 证据 / 下一步 |
|---|---|---|
| 当前入口及历史差距审计 | 已取证（静态） | `JobRunner → Miu2dClosedLoop`、闸门常量、探针覆盖赋值、未挂载的进度组件；尚不能据此推断所有运行行为 |
| 迭代范围与验收定义 | 已明确 | 本节 12.2–12.5；不等于实现完成 |
| I8-INTENT | 已实现 / 已验证 | A1–A3：`tests/core/test_miu2d_grounding.py` 覆盖类别、序数、字段、倍率、否定约束、缺字段、多目标及不支持复合意图；真实 HTTP 只修改 BossA Attack |
| I8-JOB | 已实现 / 已验证 | A3–A5/A7/A8：`test_package_integrity.py` 覆盖审阅摘要、源文件漂移、额外字节/文件、补偿恢复与撤回；原文件保持 CRLF 字节 |
| I8-EVENT | 已实现 / 已验证 | A6：持久 `job_events` 单源；`test_detail_snapshot.py` 验证独立 WAL writer 下 detail 的事务一致性；真实 HTTP 验证 Last-Event-ID 与 seq；手机浏览器中止 SSE 后轮询完成 |
| I8-WEB | 已实现 / 已验证 | A3/A5/A6/A8/A9：候选选择、刷新/历史恢复、审计批准门、静态范围和未执行探针、任务进度、撤回下载；95 unit/component tests 通过；旧正面 coverage 缺明确执行证据时总览及结果项均中性呈现 |
| 真实 HTTP/浏览器/ZIP 验收 | 已通过 | HTTP 3 例包含重启、源漂移与撤回；最终生产浏览器 desktop/mobile 共 4 例，43.6 秒，0 skipped/failed/flaky；工件 `.ai-bridge/iter8-real-browser-final/` |
| 本轮完整门禁 | 已通过（明确跳过项见下） | Python 955 passed / 2 skipped、覆盖率 70.39%；Web lint/type/unit/build、mock 8 例和真实 4 例 E2E 通过 |
| 最终范围审查 | 已完成 | 独立检查 A1–A9 工件与代码，A10 由主调度按实际命令收口；`git diff --check` EXIT 0；原始游戏不变与后续义务保留，不宣称真实游戏运行或全平台完成 |

最终生产浏览器证据：`report.json` 的 `expected=4, unexpected=0, skipped=0, flaky=0`；测试 API `127.0.0.1:18765`、Web `127.0.0.1:13180`，使用全新临时状态，完成后测试服务已退出。直接任务 desktop `bed8c2440bee`、mobile `5d268447a2eb`；同一澄清全流程任务 desktop `55c44f30846e`、mobile `7312ff263858`。后两者经历史恢复、选择 BossC、批准、下载 ZIP（Attack 90→180、其他字节不变）、撤回、刷新与旧 URL 404；原始游戏全部文件从创建到撤回保持逐字节一致。截图、下载 ZIP、计划、报告和任务状态均保存在上述目录。上一轮 production 工件也保留，未覆盖或拿旧构建替代最终回归。

| 门禁 | 本轮实际命令 | 结果 / 证据 |
|---|---|---|
| Python lint / format | `.venv/bin/ruff check udify/ tests/`；`.venv/bin/ruff format --check udify/ tests/` | EXIT 0；207 文件格式通过 |
| blocking mypy | `bash scripts/typecheck.sh` | EXIT 0；15 文件；不代表全包 strict 通过 |
| Python 全量 + coverage | `.venv/bin/python -m pytest tests/ -q --cov=udify --cov-report=xml:.ai-bridge/iter8-coverage.xml --cov-report=term --cov-fail-under=62 --junitxml=.ai-bridge/iter8-pytest.xml` | EXIT 0；955 passed / 2 skipped / 8 warnings，45.24 秒；9406/13362 行，70.39% |
| 可达性 | `.venv/bin/python scripts/check_reachability.py` | EXIT 0；133 modules、93 reachable、138 known orphan 全部有 allowlist；不是零孤儿 |
| Web install / audit | `pnpm install --frozen-lockfile`；`pnpm audit:prod`（web） | EXIT 0；无已知生产依赖漏洞；esbuild build-script 的现有提示保留 |
| Web 静态 / unit | `pnpm lint`；`pnpm typecheck`；`pnpm test --run`（web） | 全部 EXIT 0；20 文件、95 tests 通过 |
| Web production build | `NEXT_PUBLIC_UDIFY_API=http://127.0.0.1:18765 pnpm build`（web） | EXIT 0；Next 15.5.22，实际生产包用于下面真实测试 |
| 真实浏览器 | `REAL_E2E_WEB_MODE=production pnpm exec playwright test --config playwright.real.config.ts`（web） | EXIT 0；4 passed，43.6 秒；`.ai-bridge/iter8-real-browser-final/report.json` |
| Mock 浏览器 | `E2E_PORT=13181 pnpm test:e2e`（web） | 最终构建 EXIT 0；8 passed，55.4 秒，单 worker；`.ai-bridge/playwright-mock-results/.last-run.json`；先前独立回归 17.8 秒及 API 隔离附件保留于 `.ai-bridge/iter8-mock-final/report.json` |

Python 两项跳过均与此解释器未安装 Playwright 有关（一个 collection skip、一个 runtime-profile case）；不据此宣称 Python 探针或真实游戏运行已验收。Node Playwright 的真实产品浏览器验收独立执行。新增两条可达性临时例外：旧 `ProgressStore` 已被持久事件替代、`run_by_engine` 不再对原游戏执行不安全的运行探针；到期日均为 2026-10-08，后续需审查移除或按隔离工件重新接入。

失败记录没有删除：最初 mock 固定 8765 导致 18765 请求穿透、8 例失败，已改为 context 层拦截所有 `/api/` 请求；独立回归的 79 条 API 请求全部被拦截、无未处理路由。修复后 5 worker 出现 GPU stall 与 4 条导航超时，单 worker 同断言全过，因此默认使用单 worker；资源争用为有证据支持的推断，不声称已经完成 GPU 根因分析。失败工件分别保留在 `.ai-bridge/iter8-mock-initial-failure/`、`.ai-bridge/iter8-mock-parallel-first/`。旧受跟踪 `.last-run.json` 内容恢复为原基线，仅留末尾换行差异，不将其作为本轮通过证据。

研究与集成链路索引：`.ai-bridge/ITER8-PIPELINE.md`。Sol 两个标签页分别进行了 2 轮可信执行研究、3 轮事件研究/编码/缺陷返工；直接收获并整合的 Sol 源码为 `web/lib/api/job-event-state.ts` 一份，其余实现由本地并行代理完成并统一验证。研究是对给定源码与复现的审查，不包装成外部文献核验或模型思考时长证明。

### 12.7 后续义务与完成口径

本轮完成必须覆盖 A1–A10；不会因实现部分模块或通过单元测试而缩减验收。以下是继续保留的产品路线义务，其“未纳入本批”不表示已经清偿：

| 后续事项 | 来源与当前边界 | 下一阶段需要的证据 |
|---|---|---|
| 可选 LLM 意图候选、预算、超时与本地模型对照 | COG-LLM-01..03、iter7 M5-PR2/PR3；本批确定性入口修复不等于 LLM 已接入 | 真实入口有/无 Key 行为、失败降级、候选裁决与离线对照报告 |
| 真实商业游戏或合法引擎 demo 的运行验收 | REAL-GAME-01/02；本批合成资产与本地真实 HTTP 是不同证据等级 | 资产合法来源、实际游戏启动观测与改造后可运行结果 |
| 多引擎浏览器产品化 | 通用 Pipeline 的 RPGMV 修复、Godot 探针能力不能替代 JobRunner 全链路 | 每引擎从感知到 Patch、工件、运行验证、包与恢复的独立验收 |
| 多 Mod 安装依赖与冲突可视化 | iter6 V5 与 MOD-STACK 系列；本批不把空冲突列表视为已检查 | 真实已装 Mod 状态、冲突裁决及可操作 UI |
| 精确 SourceSpan 与基准扩展 | 文件级证据仍须诚实展示；iter7 M3-PR4 pass-to-pass 的长期基准维护继续保留 | 精确定位验证与 golden case 非目标字节断言，不伪造行号 |
| 全量孤儿清偿、覆盖率 70% 与远端 CI | iter7 冻结基线到期审查、批次 6 及判据 7 | 按范围清偿并复核可达性；实际覆盖率与远端运行记录 |

在这些义务完成前，只能宣称本轮选定的 miu2d 本地闭环通过，不能宣称长期 PRD、真实游戏运行能力或整个内容平台已完成。
