# Udify 迭代方案 2026-07

> 面向工程落地的深度迭代方案。基于对当前代码与 30+ 份文档的实测盘点，结合 2026 年社区最佳实践（MCP 2026-07 规范、Temporal+LangGraph 双层持久化、Landlock/seccomp 沙箱、分层 evals），给出从技术架构、前后端、接口契约到工程治理的完整迭代路径。
>
> **一句话判断**：Udify 不缺架构，缺的是"一个真实跑通的闭环 + 对已写代码的验证"。本轮迭代的唯一北极星是让 miu2d 的"自然语言 → 可回滚、经运行时验证的 ModPackage"真实成立，其余一切服从它。

---

## 0. TL;DR

| 维度 | 现状 | 本轮目标 |
|---|---|---|
| 端到端闭环 | 从未在真实游戏上跑通 | miu2d 单条黄金路径真实跑通并进 CI |
| 文档 vs 代码 | 34.7k 行文档 : 17.3k 行代码，v3 落地约 0% | 冻结宏大蓝图，只落地支撑闭环的 v3 原语 |
| 测试覆盖 | 183 通过，但只覆盖旧 4 子系统 | Session 4 四个模块补测试，整体门槛 80% |
| Session 4 代码 | cognition/evaluation/toolchain/pipeline_v2 零测试、未接线 | 补测试、接 CLI、或按结论删并 |
| 工具执行安全 | subprocess 直调、sandbox 占位、无网关 | ToolGateway + Landlock/seccomp + 默认断网 |
| 运行时验证 | 不存在 | Playwright probe 证明 mod 真的能跑 |
| CI | 无 | pytest + mypy + ruff + UdifyBench 全绿才可合并 |

**做减法优先**：删除重复 pipeline、冻结未被闭环用到的文档、砍掉 Unreal/Neo4j/云/marketplace/前端全量。**只补三件不能省的事**：证据链（可调试、可审计）、工具沙箱（安全边界）、运行时验证（证明有效）。

---

## 1. 现状诚实盘点（实测）

### 1.1 代码事实

- 主包 `udify/` 约 **17,309 行** Python；测试约 2,900 行。
- `python3 -m pytest tests/` → **183 passed in 0.48s**。
- 但测试目录只有 `tests/{core,infrastructure,models,perception}/`。
- **Session 4 新增的四个模块没有任何测试**：
  - `core/cognition/`（intent / intent_classifier / reference_resolver / conflict_detector）
  - `core/evaluation/intent_alignment.py`
  - `core/toolchain/__init__.py`
  - `core/pipeline_v2.py`（`AutomatedModPipeline`，号称 13 步全自动）
- **`pipeline_v2` 未接入 CLI**：`cli.py` 仍 import `core.pipeline.UdifyPipeline`，`AutomatedModPipeline` 只在 PROGRESS 文档里被示范调用，实际入口从未连上。
- **两条 pipeline 并存**：`pipeline.py`（342 行）与 `pipeline_v2.py`（280 行）职责重叠、来源不同，属于典型的"加了新的、没删旧的"技术债。

### 1.2 v3 架构落地度

`ARCHITECTURE-OSS-OPTIMIZED-v3.md` 与 `MODULE-ATTACK-MAP-v3.md` 已把 v3 拆到任务 ID 粒度，但代码里：

| v3 原语 | 文档状态 | 代码状态 |
|---|---|---|
| `SourceSpan` / `Provenance` / `Confidence` / `Evidence` | 详细定义 | **不存在** |
| `PatchOperation.execution_mode`（graph/file/runtime/package） | 详细定义 | **不存在**，Patch 仍是图操作 |
| `EngineAdapter` / `ToolAdapter` 协议 | 详细定义 | **不存在**，toolchain 是硬编码 if/else |
| Secure Tool Gateway（policy/sandbox/audit/lockfile） | 详细定义 | **不存在**，`toolchain` 直调 `subprocess.run` |
| Runtime probe（Playwright） | 详细定义 | **不存在** |
| UdifyBench / golden case | 详细定义 + 10 个首批 case 清单 | **不存在** |
| `ModJob` 状态机 / durable job | 详细定义 | **不存在**，只有 `ModSession` |

**结论**：v3 是一份优秀的施工图，但施工尚未开始。当前代码停留在 v2 骨架 + Session 4 的未验证增量。

### 1.3 安全现状

- `core/execution/sandbox.py`：`execute_in_docker()` 明确返回 `"Docker execution not configured"`，真实隔离是**占位**；实际走 `subprocess.run` + 超时。
- `core/toolchain/__init__.py`：调用 AssetStudio/UABE/umodel/miu2d converter 用的是 `subprocess.run([list], ...)`——**参数以 list 构造、无 `shell=True`、无 f-string 拼接**，这一点是对的（无命令注入面）；但**没有路径 allowlist、没有网络隔离、没有 audit、没有配额**，且这些工具在本机根本没安装（`_is_tool_available` 会全部判 False）。
- 反编译工具（dnSpy/ILSpy/Frida）已登记进 toolchain 配置，但只是 `download_url` 元数据，无集成。
- LLM 客户端 `core/llm_client.py` 包了 `openai` / `anthropic`，但二者不在核心依赖里（可选），且**无重试、无结构化输出约束、无超时预算**可见。

### 1.4 文档体量

- `docs/` 共 30+ 份、**34,689 行**。其中 `ARCHITECTURE-v2.md`（2,406 行）、`ARCHITECTURE-DATA/SECURITY/DEVOPS/EVENT-DRIVEN/API`（各 1,400–1,900 行）、以及一整套"AI 原生游戏工业"蓝图（芯片、主机、云调度、生态治理）——**这些内容目前 0 行代码支撑，且与"让 miu2d 第一个 mod 跑通"无直接关系**。
- 文档写作速度远快于验证速度，是本项目当前最大的系统性风险。

---

## 2. 核心诊断

### D1. 价值主张从未被验证

Udify 的全部意义是"非技术用户用自然语言产出可玩 mod"。到今天为止，**没有任何一次真实的 game_root + 自然语言 → 可运行 mod 的记录**。所有"✅ 完成"都是模块单测层面的完成，不是能力层面的完成。这是必须最先解决的事。

### D2. 架构负债 > 代码负债

问题不是代码写得少，而是**架构承诺远超已验证能力**。继续写文档/加模块只会拉大缺口。正确动作是冻结蓝图扩张，把已有的 v3 施工图**只落地到闭环所需的最小子集**。

### D3. 新代码无测试无接线 = 幻觉资产

Session 4 的 1,500 行是项目最核心的认知/评估层，却零测试、未接 CLI。它现在既不能证明对，也不能被用户触达，等于**账面资产、实际为零**。要么补测试+接线转成真实资产，要么承认过早、删掉减负。

### D4. 安全边界缺失会在接真实工具那一刻爆炸

一旦开始真的调 AssetRipper/BepInEx/converter 处理**外部下载的游戏文件**（不可信输入），当前"直调 subprocess、无沙箱、无网络隔离、无审计"的方式就是一个远程代码执行温床——注意 AssetRipper 自己在 2026 就修过一个"恶意 AssetBundle 容器路径 RCE"。ToolGateway 不是锦上添花，是接工具前的硬门槛。

---

## 3. 迭代北极星与成功判据

### 3.1 北极星：唯一的黄金闭环

```
miu2d 样例游戏
  + 自然语言意图（"让第一个 Boss 更难，但不要单纯翻倍血量"）
  → 带证据与置信度的语义图（ContentGraph + SourceSpan/Provenance）
  → 带风险分的候选 Patch 计划（execution_mode=file_patch）
  → VFS 预览（不碰原文件）
  → 静态验证（引用完整性 + 数值范围 + 危险 API 扫描）
  → Playwright 运行时探针（游戏真能启动 + Boss 状态可读）
  → 意图对齐评分
  → 可回滚 ModPackage（回滚后 graph checksum 一致）
```

### 3.2 成功判据（照搬 MODULE-ATTACK-MAP-v3 §20，逐条可验收）

1. 同一 miu2d 样例、同一意图连续运行得到**稳定** Patch。
2. 每个 `PatchOperation` 能回溯到 `SourceSpan` 和 planning reason。
3. 修改只进 VFS，原文件不受影响。
4. 静态验证能抓出无效引用与危险脚本。
5. Playwright probe 证明游戏启动并读到关键状态。
6. Patch 可回滚，回滚后 checksum 一致。
7. **≥10 个 UdifyBench case 在 CI 中运行**。
8. 工程师能按任务 ID 拆 PR，无需重新解释架构。

> 达成这 8 条 = 本轮迭代成功。**不看新增代码行数，不看新增文档份数。**

---

## 4. 技术架构迭代

原则：**只落地支撑北极星的 v3 原语，全部作为现有 dataclass 的 optional 字段兼容挂载，不做大搬家**（遵循 `PROJECT-RESTRUCTURING-IMPLEMENTATION-MAP` 的 facade + wave 策略）。

### 4.1 数据模型（证据链先行）

对应 `DATA-CG-01..05`、`DATA-PATCH-01..06`。

- 新增 `udify/models/source.py`：`SourceSpan`（file_path / byte/line/col / ast_path / archive_path / content_hash / extractor:ToolRunRef）、`Provenance`（tool_id, version, args_hash, input_hash）、`Confidence`（score, method, evidence_refs）、`Evidence`。
- `ContentNode` / `ContentAsset` 增 optional：`semantic_tags`、`provenance`、`confidence`、`license_hint`（未知显式 `unknown`）。**保持 `to_dict/from_dict` 向后兼容**，旧 session 可读。
- `PatchOperation` 增 optional：`execution_mode`（默认 `graph_only`）、`PatchTarget`（图节点 ↔ SourceSpan 双向）、`preconditions/postconditions`、`reverse`、`validation_probes`（先可空）、`risk`（先启发式）。
- **graph checksum**（`DATA-CG-08`）：稳定哈希，用于回滚一致性验收（判据 6）。

> 关键验收：round-trip 序列化 + 旧格式兼容 + reverse patch 的 property-based test（用已装的 `hypothesis`）。

### 4.2 引擎适配器协议（把硬编码变契约）

对应 `ADAPT-ENGINE-01..04`、`ADAPT-MIU2D-01..09`。

- 新增 `udify/core/adapters/base.py`：`EngineAdapter` Protocol（`detect / perceive / get_action_schemas / emit_patch / build_runtime_probes / package_mod`）+ `DetectionResult`（engine_id, confidence, evidence, supported_operations）。
- 新增 `udify/core/adapters/miu2d.py`：**把现有 `perception/parsers/*`（ini/obj/npc/lua）包装成 miu2d adapter**，输出带 `SourceSpan` 的节点。这是复用而非重写——现有 parser 已经能解析，只需补 span 与 adapter 门面。
- Lua 用 **Tree-sitter**（`ADAPT-MIU2D-04`）拿函数/调用/危险 API，替代手写 lua_parser 的脆弱部分（`tree-sitter` + `tree-sitter-lua` 是成熟库，别自研）。
- `adapter contract test suite`：任何新引擎必须通过同一组契约测试，保证扩展 RPG Maker 时不用重讲架构。

### 4.3 Secure Tool Gateway（接真实工具的硬门槛）

对应 `TOOL-GW-01..06`。**所有外部工具调用必须经此唯一入口**（ADR-v3-003）。

```
ToolCallRequest(tool_id, capability, args, job_id, requested_paths, risk)
  → schema 校验
  → policy 决策（本地 policy 文件，先不上 OPA）
  → sandbox 分配（见 4.4）
  → 路径 allowlist（仅 game_root + workspace_cache，越权拒绝）
  → 资源配额 + 超时
  → 工具执行
  → output sanitizer（超大输出截断落盘为 artifact）
  → audit append（链式哈希，每次可回放）
  → ToolCallResult
```

- 新增 `udify/core/tool_gateway/{gateway,policy,audit,lockfile}.py`。
- **迁移策略**：先让 `toolchain/__init__.py` 的一个真实调用（如 miu2d converter）走 gateway，验证拦截有效，再逐个搬（`TOOL-GW` 是渐进的，不是一次性重写）。
- Tool lockfile（`TOOL-GW-07`，P1）：version + sha256 pin，防供应链漂移。

### 4.4 沙箱：从占位到真实（2026 社区共识）

现状 `execute_in_docker` 占位。2026 最佳实践**不是**上来就 Docker，而是 OS 级原语：

- **首选 Landlock + seccomp-bpf**（Linux 5.13+，无需 root/namespace/容器，启动约 5ms，OpenAI Codex 已默认用这套）。对我们"跑一个受限工具/脚本"的场景，per-tool 最小权限正好。
- **macOS 开发机**：用 Seatbelt（`sandbox-exec`）作等价物；这是 JC 的主力平台（darwin），必须有可用路径，不能只写 Linux。
- **默认断网**：工具默认 `--network=none` + 显式 allowlist，直接掐断 prompt-injection 数据外泄链路。
- **密钥不进沙箱**：LLM/converter 需要的凭证留在宿主，沙箱内进程永远看不到 API key。
- **容器仅作可选升级层**：真需要跨平台一致性时再上 gVisor/Firecracker（生产，P2），本地闭环不依赖它。

> ponytail 取舍：`# 本地闭环用 Seatbelt/Landlock 进程级隔离；容器/microVM 留给生产多租户，届时再上`。

### 4.5 ModJob 与本地持久化（durable，但先别上 Temporal）

对应 `ORCH-JOB-01..05`。

- 新增 `ModJob` 状态机（created→…→completed，任意态→failed→compensating→rolled_back）+ checkpoint（graph/patch/vfs 快照）+ audit chain。
- **本地 durable 用 JSON/SQLite 即可**（`ORCH-JOB-05`），实现"崩溃后从最近 checkpoint 恢复"。
- **Temporal 明确推迟到 P2**：2026 共识是 Temporal（管副作用）+ LangGraph（管推理）双层，但那是生产化命题。现在上 Temporal 是过早复杂度——先让本地 runner 的闭环真实成立（MODULE-ATTACK-MAP §17「不要提前做的事」第 4 条）。幂等键设计上预留 `(job_id, op_id)`，为将来接 Temporal 留口。

---

## 5. 后端与接口契约

### 5.1 统一 pipeline（先还债）

- **删除 `pipeline.py` 与 `pipeline_v2.py` 的重复**：保留一个 `AutomatedModPipeline` 作为编排门面，但按 `PROJECT-RESTRUCTURING` §2 的意图，**pipeline 不应是巨型 13 步方法**，而是 `session/job_runner` 驱动的状态机步进。第一步先合并去重，第二步再逐步瘦身为 job 驱动。
- **接入 CLI**：`cli.py` 增 `udify mod <game> "<intent>"` 走新的编排入口，让 Session 4 的认知/评估层第一次被真实触达。

### 5.2 Intent Compiler（把 cognition 补成真资产）

对应 `COG-INTENT-01..05`、`COG-CONFLICT-01..02`。现有 `cognition/*` 已有 classifier/resolver/conflict 三件，本轮：

- 补 `StructuredIntent v3`：goal / constraints / negative_preferences / references / **acceptance_probes**（每个目标至少一个可验证探针建议——这是连接"意图"和"运行时验证"的关键，当前完全缺）。
- ambiguity detector：模糊目标要求澄清或降级，不能硬猜。
- **LLM 用结构化输出**（2026 已是 API 原生能力）：classifier/resolver 的 LLM 增强路径必须走 JSON schema 约束，禁止自由文本再正则解析；LLM 只能产出候选，不能越过 schema 写入 final（防注入）。
- **给这三个模块补齐单测**：`tests/cognition/test_cognition.py`（中英文分类、参考映射、5 类冲突检出）。

### 5.3 Validator + Evaluator 四层

对应 `VAL-STATIC-01..05`、`VAL-RUNTIME-01..05`、`EVAL-INTENT-01..04`。

| 层 | 确定性 | 本轮落地 |
|---|---|---|
| Schema validation | 确定 | 复用 `enhanced_validator`，补 patch/file schema |
| Semantic validation | 半确定 | 引用完整性、数值范围、任务链 |
| **Runtime probe** | 观测 | **新增**：`ProbeSpec` schema + Playwright launcher（miu2d 样例启动）+ console error 捕获 + 状态读取桥 |
| Intent evaluation | 概率 | 复用 `intent_alignment`，**benchmark 化、可回归**，LLM judge 只作可选、不能单独决定通过 |

- 输出统一 `ValidationReportV3`（passed / blocking_errors / warnings / evidence / probe_results / confidence / recommended_action）。
- **Runtime probe 是本轮技术含金量最高、也最能证明价值的一块**——没有它，"mod 能跑"永远是纸面断言。

### 5.4 API 层（薄，只服务闭环）

对应 `API-01..05`，P1，只做最小：

- `POST /jobs`（game_root + intent → job_id）
- `GET /jobs/{id}/plan`（patch + risk 预览）
- `POST /jobs/{id}/approve|reject`（风险确认门）
- `GET /jobs/{id}/package`（导出 ModPackage）
- 用已在可选依赖里的 FastAPI + Pydantic；**SSE/WebSocket 进度推迟**。

### 5.5 MCP 对齐（跟上 2026 规范，但不当安全边界）

现有 `mcp_server.py` 是基础版。对应 `TOOL-MCP-01..03`：

- 对齐 **MCP 2025-11-25 稳定版**（当前生产基线）：`list_tools` 标准化、elicitation 支持默认值与 enum。
- 关注 **2026-07-28 RC** 的方向（无状态核心、Tasks 扩展、server 发起请求必须绑定到用户已发起的调用 SEP-2260、OAuth 硬化），但**不追 RC**——RC 未定稿，跟进即可。
- **强约束**：MCP tool call 必须走 Secure Tool Gateway，禁止直连执行（`TOOL-MCP-02`）。**MCP 是协议不是权限系统**（MODULE-ATTACK-MAP §17 第 6 条）。

---

## 6. 前端（本轮几乎不做，只定薄切片）

遵循 §17「不要先做完整前端」。本轮**不**做 Next.js 全量、不做 ReactFlow DAG 编辑器、不做 marketplace 页。

只定义未来的最小审阅切片（等 CLI 闭环稳定后再实现，P2）：

- **Plan Diff Viewer**：文件级 diff + 受影响子图，只读。
- **Risk Review Panel**：approve/reject 风险确认门（对应 API 5.4 的确认接口）。
- **Runtime Probe Report**：probe 证据展示。

技术选型保持文档既有决定（React + ReactFlow），但**代码零投入**，避免前端拖慢主线验证。

---

## 7. 安全架构

### 7.1 风险分级驱动人工确认（不是固定步骤）

沿用 v3 的 R0–R4 与"由风险评分触发确认"：

| 等级 | 示例 | 默认策略 |
|---|---|---|
| R0 | 读 manifest、解析文本 | 自动 |
| R1 | 改 VFS 配置 | 自动，记录 |
| R2 | 写工作区文件 | 需验证通过 |
| R3 | 执行外部工具/脚本 | 沙箱 + 策略 |
| R4 | 运行时 Hook、网络、发布 | 人工确认 |

### 7.2 Prompt Injection 防线（三源隔离）

自然语言意图、游戏文本、脚本注释、README 都可能带注入。防线：

- **输入严格分级**：user instruction / game content / tool output 三源隔离，游戏内容与工具输出永远是"数据"不是"指令"。
- LLM 输出只能生成候选计划，**不能越过 schema**；工具调用参数由程序构造，不直接用模型原文。
- 高风险调用由 Policy Engine 决策，不由 LLM 决定。
- **配置文件写保护**（2026 NVIDIA 红队指引）：`AGENTS.md`、`CLAUDE.md`、`.udify` 配置等"会在运行时安全检查之前生效"的文件，处理不可信游戏包时应视为只读区。

### 7.3 供应链

- Tool lockfile（version + sha256），tool provenance 进 audit（每次调用可回放）。
- secret scanner + license hint（未知显式标记），为将来发布门槛铺垫。

---

## 8. 评估与基准（UdifyBench）

对应 `BENCH-01..03`、`EVAL-INTENT-07`。这是把"能力"变成"可回归资产"的关键。

- 目录：`benchmarks/miu2d/<case>/{input_game, intent.md, expected_patterns.yaml, forbidden_patterns.yaml, probes.yaml, scoring.yaml}`。
- **首批 10 个 golden case**（照搬 MODULE-ATTACK-MAP §15）：角色 HP 修改 / Boss 难度↑但 HP≤1.35× / NPC 对话奖励技能 / 掉落率↑ / 治疗道具削弱 / 新增商店物品 / 地图可达性保持 / 禁危险 Lua API / 多 Mod 同属性冲突 / 回滚后 checksum 一致。
- **分层 evals**（2026 Anthropic 瑞士奶酪模型）：自动 evals（CI 首道防线）+ 轨迹评估（不只看最终 patch，看工具选择/中间推理）+ LLM-as-judge（可选、需缓解偏差，不单独决定通过）。
- benchmark runner 进 CI，达不到阈值**阻塞合并**（`BENCH-07`）。

---

## 9. 工程治理（先止血）

### 9.1 CI（当前完全没有 → 必须有）

新增 `.github/workflows/ci.yml`：`pytest`（含覆盖率 80% 门槛）+ `mypy udify/`（strict）+ `ruff check` + UdifyBench runner。**全绿才可合并**。这是所有其他工作的地基——没有 CI，"183 通过"随时会悄悄变红。

### 9.2 测试债清偿（P0，先于任何新功能）

- `tests/cognition/test_cognition.py`
- `tests/evaluation/test_intent_alignment.py`
- `tests/toolchain/test_toolchain.py`（工具不可用时的降级路径也要测）
- `tests/test_pipeline_v2.py`（dry_run 全流程）
- 目标：整体 200+ 测试、覆盖率报告纳入 CI。

### 9.3 文档冻结与分层

- **冻结**"AI 原生游戏工业"三件套 + 各 1,400–1,900 行的 v2 分册（DATA/SECURITY/DEVOPS/EVENT-DRIVEN/API/PERFORMANCE/OBSERVABILITY），标注 `status: frozen / aspirational`，不再扩写。
- **唯一活跃文档集**收敛到：本文 + `MODULE-ATTACK-MAP-v3.md`（任务台账）+ `ARCHITECTURE-OSS-OPTIMIZED-v3.md`（边界）+ `TECHNICAL-DOCUMENTATION-INDEX.md`（索引）。
- 规则：**代码为准，文档滞后必须补，但不允许再用新文档扩张未验证的架构承诺**。

### 9.4 清理重复与死代码

- 合并两条 pipeline。
- toolchain 里未集成的反编译工具（dnSpy/ILSpy/Frida）先降级为"计划中"注释，别让它们看起来像已有能力。

---

## 10. 分阶段路线（PR 级）

> 遵循 MODULE-ATTACK-MAP 的批次划分，但**在第一批之前插入"止血批"**，因为测试债和 CI 是一切的前提。

### 批次 0：止血（1 周，P0）

| PR | 内容 | 验收 |
|---|---|---|
| S0-1 | CI 骨架（pytest+mypy+ruff） | main 上跑绿 |
| S0-2 | Session 4 四模块补单测 | 200+ 测试通过 |
| S0-3 | 合并双 pipeline + 接 CLI `udify mod` | 能对 miu2d 样例 dry-run 出计划 |
| S0-4 | 文档冻结标注 + 索引收敛 | 活跃文档 ≤4 份 |

### 批次 1：数据地基（对应第一批 PR，1 周，P0）

`DATA-CG-01..05` + `DATA-PATCH-01..06` + `ADAPT-ENGINE-01..04` + `TOOL-GW-01..06`。验收：旧测试全过；新原语 round-trip；一个真实工具调用走 gateway；越权路径被拒。

### 批次 2：miu2d 闭环（对应第二批 PR，2–3 周，P0）

`ADAPT-MIU2D-01..09` + `PER-LIFT-01..04` + `PLAN-ACTION-01..04` + `PATCH-SYN-01..06`。验收：自然语言 → 带证据语义图 → file_patch 计划 → VFS 预览。

### 批次 3：验证与基准（对应第三批 PR，2–3 周，P0）

`VAL-STATIC-01..05` + `VAL-RUNTIME-01..05` + `EVAL-INTENT-01..04` + `BENCH-01..03`。验收：Playwright probe 证明启动 + 10 个 golden case 进 CI。**批次 3 完成 = 北极星达成。**

### 批次 4（P1，闭环稳定后）

`ORCH-JOB-01..05` + `MOD-STACK-01..06` + `MEM-STORE-01..05` + `OBS-01..04` + 薄 API（`API-01..05`）。

### 批次 5+（P2，明确推迟）

RPG Maker MV/MZ 第二引擎、MCP 深化、OPA policy、Temporal、Neo4j/Qdrant、前端审阅切片。

---

## 11. 明确不做的事（本轮红线）

照搬并强化 MODULE-ATTACK-MAP §17：

1. **不写完整前端**——CLI/API 闭环先真实跑通。
2. **不接 Unreal**——机制修改成本与法律风险最高。
3. **不做通用自动试玩 AI**——先做最小 probe。
4. **不上 Neo4j/Qdrant/Temporal 强依赖**——本地模式必须成立。
5. **不让 LLM 直接写文件**——必须走 Patch + Tool Gateway。
6. **不把 MCP 当安全边界**——它是协议不是权限系统。
7. **不把所有计划都走 MCTS**——简单数值任务用确定性规划。
8. **不用"LLM 评估"替代运行时验证**。
9. **（新增）不再写新的宏大架构文档**——直到北极星达成前，文档只减不增。
10. **（新增）不加任何没有测试、没有接线的模块**——避免再造 Session 4 式的幻觉资产。

---

## 12. 一页纸总结

- **问题**：架构承诺（34.7k 行文档、完整 v3 施工图）远超已验证能力（0 次真实闭环、4 个核心模块零测试）。
- **动作**：冻结蓝图扩张，先止血（CI + 测试债 + 去重），再只落地支撑"miu2d 单条黄金闭环"的 v3 最小子集（证据链 + 工具网关 + 沙箱 + 运行时探针 + 10 个 benchmark）。
- **判据**：不看代码行数、不看文档份数，只看 §3.2 的 8 条可验收事实。
- **纪律**：能删就删、能复用开源就不自研、能推迟就推迟；本轮唯一目的是把"自然语言 → 可玩 mod"从断言变成事实。

> 参考：MCP 2026-07-28 RC（无状态核心/Tasks/OAuth 硬化）；Temporal+LangGraph 双层持久化共识；Landlock/seccomp per-tool 沙箱（OpenAI Codex 默认）；Anthropic 分层 evals（瑞士奶酪）；AssetRipper 2026 的 AssetBundle RCE 修复（印证工具网关必要性）。
