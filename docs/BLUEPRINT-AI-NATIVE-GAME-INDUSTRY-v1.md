<!--
status: aspirational
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 愿景/未验证蓝图。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# AI 原生游戏工业技术框架蓝图 v1

> 站在“重塑整个游戏工业”的视角，给出 Udify 长期技术框架。它不是游戏引擎，不是普通 Agent 平台，不是 Mod 托管站，而是连接硬件、引擎、资产、玩法、验证、云和社区生态的内容变换操作系统。

---

## 0. 蓝图总览

AI 原生游戏工业需要一个横跨端、边、云的协同架构：

```text
玩家和创作者意图
  -> Intent OS
  -> Game Semantic IR
  -> Content Transformation Compiler
  -> Tool and Engine Mesh
  -> Validation and Simulation Fabric
  -> Mod/Game Package Supply Chain
  -> Runtime Personalization and LiveOps
  -> Community Feedback Evolution
```

Udify 的长期定位：

```text
Udify Core:      意图到语义 Patch 的编译器
Udify Fabric:    自动验证、仿真、构建、推理的云边端资源层
Udiface:         AI 原生游戏内容和 Mod 的生态层
Udiscipline:     质量、伦理、版权、社区治理和演化方法论
```

---

## 1. 设计原则

### B1. Content Is Program

游戏内容不是静态文件，而是可执行系统：

- 地图影响路径。
- 数值影响经济。
- 对话影响任务。
- 资源影响性能。
- Mod 影响生态。

因此每次内容变换都必须像代码变更一样：

- 可 diff。
- 可测试。
- 可回滚。
- 可审计。
- 可发布。

### B2. Intent Is Source Code

用户意图应成为工业流程的源代码。

```text
"让这个游戏更像魂系，但不要数值膨胀"
```

应被编译为：

- 目标函数。
- 约束。
- 风格参考。
- 影响范围。
- Patch 候选。
- 验收探针。
- 风险报告。

### B3. Hardware Is Capability, Not Assumption

不能假设所有玩家都有同样硬件。每个设备都应暴露能力画像：

```yaml
CapabilityProfile:
  cpu:
    cores: 8
    simd: [avx2]
  gpu:
    api: [vulkan, directx12]
    vram_gb: 12
    ray_tracing: true
    neural_acceleration: true
    video_encode: [av1, h264]
  npu:
    available: true
    tops: 40
  storage:
    ssd: true
    bandwidth_mb_s: 5000
  network:
    latency_region: cn-east
  privacy:
    local_inference_required: false
```

所有 Patch、Probe、ModPackage、Runtime AI 都要声明硬件需求和降级路径。

### B4. Validation Is Product

AI 原生内容最大的问题不是生成，而是证明它能工作。验证本身就是产品能力：

- 玩家相信 Mod，因为它有验证证书。
- 创作者相信模板，因为它有 benchmark。
- 平台相信发布物，因为它有 provenance。
- 引擎团队相信自动修改，因为它可回滚。

### B5. Ecosystem Learns

每个成功 Mod、失败 Patch、崩溃、回滚、评分和评论都应成为生态知识。

---

## 2. 端边云三层协同

### 2.1 端侧：Player/Creator Device Layer

职责：

- 本地游戏扫描。
- 私有偏好建模。
- 轻量意图解释。
- VFS 预览。
- 本地小模型推理。
- 离线 Mod 管理。
- 低风险 runtime personalization。

模块：

| 模块 | 职责 |
|---|---|
| Device Capability Profiler | 采集 CPU/GPU/NPU/存储/网络能力 |
| Local Privacy Vault | 保存玩家偏好、历史、私有数据 |
| Local VFS Overlay | 不破坏原游戏的预览和安装层 |
| Local Probe Runner | 小规模启动、读取状态、截图 |
| Local Model Runtime | 小模型推理、embedding、分类 |
| Mod Safety Guard | 本地策略和风险提示 |

### 2.2 边缘：Edge Game and Inference Layer

职责：

- 低延迟多人服务器。
- 区域化 Mod 分发缓存。
- 轻量实时推理。
- 云游戏就近串流。
- 区域兼容性和性能统计。

模块：

| 模块 | 职责 |
|---|---|
| Edge Match Router | 按地区、ModStack、延迟匹配 |
| Edge Mod Cache | 热门 Mod 和资产包缓存 |
| Edge Inference Node | 轻量 NPC、审核、推荐推理 |
| Edge Probe Node | 区域硬件/网络验证 |
| Edge Streaming Gateway | WebRTC/Pixel Streaming |

### 2.3 云侧：Game AI Fabric

职责：

- 大模型规划和评估。
- 大规模资产编译。
- 多版本兼容性测试。
- 自动试玩和仿真。
- ModPackage 签名发布。
- 知识图谱和向量检索。

模块：

| 模块 | 职责 |
|---|---|
| BuildCloud | 构建、打包、资产转换 |
| SimCloud | Runtime Probe、Playtest Agent、批量 QA |
| InferCloud | LLM、多模态、embedding、评估模型 |
| GraphCloud | Game Semantic Graph、Mod 兼容图 |
| PackageCloud | ModPackage、签名、SBOM、分发 |
| TelemetryCloud | 指标、日志、视频证据、反馈 |

---

## 3. 全栈架构图

```text
┌──────────────────────────────────────────────────────────────┐
│ User and Community Layer                                      │
│ Intent, feedback, review, marketplace, creator economy         │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Intent OS                                                     │
│ intent compiler, preference model, policy, clarification       │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Game Semantic IR                                              │
│ content graph, mechanism graph, asset provenance, runtime obs  │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Transformation Compiler                                       │
│ planner, patch synthesizer, risk scorer, merge resolver        │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Tool and Engine Mesh                                          │
│ Unreal, Unity, Godot, RPG Maker, miu2d, DCC tools, MCP tools   │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Validation and Simulation Fabric                              │
│ static validation, runtime probe, playtest, compatibility CI   │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Supply Chain and Distribution                                 │
│ VFS, package, signature, license, marketplace, CDN, edge cache │
└──────────────────────────────┬───────────────────────────────┘
                               │
┌──────────────────────────────▼───────────────────────────────┐
│ Hardware and Cloud Capability Layer                           │
│ CPU, GPU, NPU, storage, video encode, game servers, inference  │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. 核心系统蓝图

### 4.1 Intent OS

目标：把人类愿望变成可执行工程目标。

子系统：

| 子系统 | 输入 | 输出 |
|---|---|---|
| Intent Parser | 自然语言 | 初始意图类型 |
| Reference Mapper | “魂系”“塞尔达”“肉鸽” | 机制特征 |
| Constraint Compiler | “不要太难”“不要改剧情” | hard/soft constraints |
| Preference Merger | 用户历史和反馈 | 个性化权重 |
| Clarification Engine | 不确定点 | 澄清问题或默认策略 |
| Acceptance Probe Planner | 目标和约束 | 验收探针 |

### 4.2 Game Semantic IR

目标：用统一语义表达不同引擎和游戏。

核心图：

| 图 | 表达 |
|---|---|
| ContentGraph | 文件、资产、脚本、配置、资源关系 |
| MechanismGraph | 战斗、经济、任务、地图、叙事机制 |
| AssetProvenanceGraph | 资产来源、生成、授权、修改历史 |
| RuntimeObservationGraph | 实际运行中观测到的状态 |
| ModCompatibilityGraph | Mod 间冲突、依赖、加载顺序 |
| PlayerPreferenceGraph | 玩家偏好和反馈 |

Game Semantic IR 最小 ontology：

```text
Actor, Enemy, Boss, NPC, Item, Skill, Buff, Quest, Dialog,
Map, Region, Encounter, DropTable, EconomySink, EconomySource,
Trigger, Switch, Variable, Cutscene, Asset, Script, RuntimeHook
```

### 4.3 Transformation Compiler

目标：从 `StructuredIntent + Game Semantic IR` 生成 Patch。

编译阶段：

```text
Intent lowering
  -> target selection
  -> action schema expansion
  -> constraint solving
  -> candidate plan search
  -> risk and cost scoring
  -> patch synthesis
  -> reverse patch generation
  -> validation plan generation
```

Patch 类型：

| 类型 | 示例 |
|---|---|
| NumericPatch | HP、ATK、drop rate |
| ScriptPatch | 插入 Lua/DSL/GDScript |
| EventPatch | RPG Maker event page |
| AssetPatch | 替换贴图、音频、模型 |
| RuntimeHookPatch | Harmony/BepInEx hook |
| MapPatch | tile、障碍、触发器 |
| EconomyPatch | 商店、奖励、消耗 |
| NarrativePatch | 对话、任务分支 |
| PackagingPatch | manifest、依赖、加载顺序 |

### 4.4 Tool and Engine Mesh

目标：把引擎和工具变成安全可编排能力。

Engine Adapter：

- miu2d。
- RPG Maker MV/MZ。
- Unity。
- Godot。
- Unreal。
- GameMaker。
- Web games。

Tool Adapter：

- Tree-sitter。
- Roslyn/LSP。
- AssetRipper。
- FModel/CUE4Parse。
- QuickBMS。
- Blender/OpenUSD。
- FFmpeg。
- ComfyUI。
- Playwright。
- Semgrep。

每个 adapter 必须声明：

```yaml
capabilities:
  read:
    - asset_manifest
    - script_ast
  write:
    - config_patch
    - package_overlay
risk:
  level: R2
resources:
  cpu: 2
  memory_gb: 4
  gpu: false
sandbox:
  network: false
  writable_paths: [workspace_cache]
```

### 4.5 Validation and Simulation Fabric

目标：证明内容变换有效。

验证层：

| 层 | 工具 | 输出 |
|---|---|---|
| Static | schema/parser/rules | 格式和引用正确 |
| Semantic | knowledge graph/invariants | 机制不破坏 |
| Runtime | Playwright/engine runner | 启动和状态可验证 |
| Simulation | Playtest Agent/RL | 可玩性和路径 |
| Compatibility | pairwise matrix | Mod 组合安全 |
| Experience | metrics + feedback | 是否符合意图 |

Validation Certificate：

```yaml
certificate_id: cert_xxx
mod_package: mod_xxx
game_version: 1.0.3
hardware_profiles:
  - pc_mid_gpu
  - steam_deck
checks:
  static: passed
  runtime_probe: passed
  compatibility: warning
  intent_alignment: 0.86
evidence:
  logs: ...
  screenshots: ...
  video: ...
  graph_diff: ...
```

### 4.6 Supply Chain and Distribution

目标：让 AI 生成和 Mod 发布像软件供应链一样可信。

组成：

- Tool Lockfile。
- Asset provenance。
- Patch provenance。
- SBOM。
- 签名。
- license hint。
- moderation report。
- compatibility certificate。
- rollback package。

发布物：

```text
ModPackage
  manifest.yaml
  patches/
  assets/
  reverse/
  validation/
  provenance/
  signatures/
```

### 4.7 Runtime Personalization

目标：从“离线魔改”走向“安全的个性化运行时”。

分级：

| 等级 | 能力 | 风险 |
|---|---|---|
| L0 | 离线 Patch | 低 |
| L1 | 启动前配置选择 | 低 |
| L2 | 会话间个性化 | 中 |
| L3 | 运行时 NPC/对话微调 | 中高 |
| L4 | 实时机制调整 | 高 |

原则：

- 多人游戏默认服务器权威。
- 实时调整必须可解释、可关闭、可回滚。
- 本地个性化数据默认不上传。

---

## 5. 云基础设施蓝图

### 5.1 GameAI Fabric 控制面

模块：

| 模块 | 职责 |
|---|---|
| Workload API | 接收 build/probe/infer/server/stream 任务 |
| Capability Scheduler | 按 GPU/NPU/CPU/地域调度 |
| Policy Controller | 权限、预算、风险 |
| Artifact Registry | 存储 ModPackage、工具、模型、资产 |
| Trace Controller | 贯穿 job、patch、probe、package |
| Cost Controller | 预算、计费、降级 |

### 5.2 GameAI Fabric 数据面

节点类型：

| 节点 | 资源 | 工作负载 |
|---|---|---|
| CPU Build Node | CPU/SSD | 构建、打包、解析 |
| GPU Render Node | GPU/NVENC | 截图、视频、运行时验证 |
| GPU Infer Node | GPU/HBM | LLM、多模态、embedding |
| Edge Game Node | CPU/network | 多人服务器 |
| Edge Stream Node | GPU/video encode | 云游戏串流 |
| Sandbox Node | gVisor/Firecracker | 高风险工具 |

### 5.3 资源调度目标

调度函数：

```text
placement_score =
  capability_match * 0.35
  + region_latency * 0.20
  + cache_hit * 0.15
  + cost_efficiency * 0.15
  + queue_time * 0.10
  + energy_policy * 0.05
  - risk_penalty
```

### 5.4 数据分层

| 数据 | 热度 | 存储 |
|---|---|---|
| active VFS overlay | 热 | 本地 SSD/Redis |
| runtime logs | 热 | object store + index |
| validation videos | 温 | object store |
| asset artifacts | 温 | object store/CDN |
| graph snapshots | 温 | graph db + object |
| old ModPackage | 冷 | archive storage |
| anonymized benchmark | 长期 | dataset registry |

---

## 6. AI 原生生产流程

### 6.1 玩家 Mod 流程

```text
玩家输入意图
  -> 本地扫描游戏
  -> 云/本地构建语义图
  -> 生成候选计划
  -> 玩家确认
  -> VFS 预览
  -> 自动验证
  -> 安装或导出 ModPackage
  -> 反馈进入记忆
```

### 6.2 专业开发流程

```text
策划输入设计目标
  -> 生成多个机制变体
  -> 自动构建 playable prototype
  -> SimCloud 批量测试
  -> 设计师挑选方向
  -> QA benchmark 固化
  -> 进入主线开发
```

### 6.3 LiveOps 流程

```text
玩家数据和社区反馈
  -> 异常体验检测
  -> 平衡性 Patch 候选
  -> 仿真验证
  -> A/B 分桶
  -> 灰度发布
  -> 回滚或推广
```

### 6.4 UGC 生态流程

```text
创作者发布意图模板
  -> 社区复用和分叉
  -> 自动兼容性测试
  -> 质量评分
  -> 推荐和变现
  -> 成功模板进入公共库
```

---

## 7. 模块域划分

后续攻坚按 12 个域组织：

1. **HWCAP**：硬件和运行时能力画像。
2. **INTENT**：意图操作系统。
3. **SEMIR**：游戏语义中间表示。
4. **ASSET**：资产 provenance 和生成管线。
5. **MECH**：玩法机制图和约束。
6. **PATCH**：内容变换编译器。
7. **TOOLMESH**：工具和引擎适配网格。
8. **VALID**：验证、仿真和自动试玩。
9. **CLOUD**：GameAI Fabric。
10. **SUPPLY**：ModPackage 供应链。
11. **RUNTIME**：运行时个性化和 live ops。
12. **ECO**：Udiface 生态、市场、治理。

细粒度模块见 `MODULE-ATTACK-MAP-AI-GAME-INDUSTRY.md`。

---

## 8. 阶段路线图

### Phase A：Udify Core 进化为语义 Patch 编译器

目标：

- miu2d/RPG Maker 闭环。
- ContentGraph v3。
- Runtime Probe。
- UdifyBench。

### Phase B：GameAI Fabric 原型

目标：

- BuildCloud。
- SimCloud。
- GPU/CPU workload descriptor。
- Artifact registry。
- Validation certificate。

### Phase C：多引擎 Tool Mesh

目标：

- Unity runtime hook。
- Godot adapter。
- Unreal asset graph。
- OpenUSD asset provenance。

### Phase D：Udiface 生态

目标：

- ModPackage marketplace。
- Compatibility matrix。
- Creator attribution。
- Template economy。

### Phase E：AI 原生开发平台

目标：

- 专业游戏团队接入。
- 自动玩法变体。
- 云端仿真。
- LiveOps Patch。

---

## 9. 最小验证路径

不要一开始试图重塑 AAA 工业。最小路径：

1. miu2d：证明语义 Patch、VFS、运行时验证。
2. RPG Maker：证明跨引擎语义 IR。
3. Unity/BepInEx：证明 runtime hook Patch。
4. GameAI Fabric：证明云端批量验证。
5. Udiface：证明模板和兼容性生态。

每一步都必须反哺最初使命：

> 非技术用户表达意图，系统完成可验证内容变换。

---

## 10. 成功判据

长期成功不是“生成一个游戏”，而是：

1. 非技术用户能稳定生成可玩的 Mod。
2. 每个 Mod 有证据、验证、回滚和兼容性报告。
3. 成功变换能沉淀成模板并跨游戏复用。
4. 游戏团队能用 Udify 缩短设计、测试和 live ops 周期。
5. 玩家、创作者和开发者围绕语义 Patch 形成生态。
6. 硬件、云、引擎和 AI 模型被统一调度为内容演化基础设施。
