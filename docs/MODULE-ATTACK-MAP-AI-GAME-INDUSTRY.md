<!--
status: aspirational
frozen_at: 2026-07 (ITERATION-PLAN-2026-07.md §9.3 文档冻结)
note: 愿景/未验证蓝图。不再主动维护/扩写；如需解冻须先在 ITERATION-PLAN 获得明确同意。
-->

# AI 原生游戏工业模块攻坚地图

> 本文把 `BLUEPRINT-AI-NATIVE-GAME-INDUSTRY-v1.md` 拆到最细工程模块。它不是单个 Udify 版本的迭代计划，而是面向“AI 原生游戏工业基础设施”的长期模块地图。

---

## 0. 模块命名规则

```text
DOMAIN-SUBSYSTEM-序号
```

领域：

- `HWCAP`：硬件和运行时能力。
- `DEVICE`：端侧运行层。
- `EDGE`：边缘层。
- `CLOUD`：云基础设施。
- `INTENT`：意图操作系统。
- `SEMIR`：游戏语义中间表示。
- `ASSET`：资产系统。
- `MECH`：玩法机制系统。
- `PATCH`：变换编译器。
- `TOOL`：工具和引擎网格。
- `VALID`：验证和仿真。
- `SUPPLY`：供应链和发布。
- `RUNTIME`：运行时个性化。
- `ECO`：Udiface 生态。
- `GOV`：治理、安全、合规。

优先级：

- **A0**：服务 Udify 当前游戏 Mod 使命，必须优先。
- **A1**：支撑多引擎和云验证。
- **A2**：支撑平台化和专业游戏团队。
- **A3**：支撑重塑游戏工业的长期目标。

---

## 1. HWCAP：硬件和运行时能力画像

### HWCAP-CPU

| ID | 优先级 | 模块 | 职责 | 输出 |
|---|---|---|---|---|
| HWCAP-CPU-01 | A0 | CPU Core Detector | 核心数、线程数、频率估计 | `cpu_profile` |
| HWCAP-CPU-02 | A1 | SIMD Detector | AVX2/AVX512/NEON 等 | `simd_features` |
| HWCAP-CPU-03 | A1 | Script VM Budget Estimator | 估算 Lua/C#/GDScript tick 成本 | `script_budget` |
| HWCAP-CPU-04 | A2 | Simulation Capacity Model | 估算自动试玩并行能力 | `sim_capacity` |
| HWCAP-CPU-05 | A2 | Thermal Throttle Monitor | 掌机/移动端热降频观察 | `thermal_status` |

### HWCAP-GPU

| ID | 优先级 | 模块 | 职责 | 输出 |
|---|---|---|---|---|
| HWCAP-GPU-01 | A0 | Graphics API Detector | DirectX/Vulkan/Metal/WebGPU | `gpu_api_profile` |
| HWCAP-GPU-02 | A0 | VRAM Detector | 显存大小和预算 | `vram_budget` |
| HWCAP-GPU-03 | A1 | Ray Tracing Capability | RT 支持和等级 | `rt_capability` |
| HWCAP-GPU-04 | A1 | AI Acceleration Detector | Tensor/Matrix/NPU-like GPU 能力 | `gpu_ai_profile` |
| HWCAP-GPU-05 | A1 | Video Encode Detector | NVENC/AMF/QuickSync/AV1 | `encode_profile` |
| HWCAP-GPU-06 | A1 | Shader Compile Risk Model | shader 编译和 cache 风险 | `shader_risk` |
| HWCAP-GPU-07 | A2 | Neural Rendering Profile | DLSS/FSR/XeSS/MetalFX 等 | `neural_rendering` |
| HWCAP-GPU-08 | A2 | Cloud GPU Partition Profile | MIG/time slicing/vGPU | `gpu_partition` |

### HWCAP-NPU

| ID | 优先级 | 模块 | 职责 | 输出 |
|---|---|---|---|---|
| HWCAP-NPU-01 | A1 | NPU Presence Detector | 是否有 NPU | `npu_available` |
| HWCAP-NPU-02 | A1 | Local Inference Backend Probe | CoreML/ONNX/DirectML 等 | `local_infer_backends` |
| HWCAP-NPU-03 | A2 | Model Fit Estimator | 小模型是否可本地跑 | `model_fit` |
| HWCAP-NPU-04 | A2 | Privacy Mode Planner | 本地/云推理分流 | `privacy_execution_plan` |

### HWCAP-STORAGE-NET

| ID | 优先级 | 模块 | 职责 | 输出 |
|---|---|---|---|---|
| HWCAP-STO-01 | A0 | Storage Bandwidth Probe | SSD/HDD、吞吐 | `storage_profile` |
| HWCAP-STO-02 | A0 | VFS Overhead Estimator | overlay 对加载影响 | `vfs_cost` |
| HWCAP-STO-03 | A1 | Asset Locality Analyzer | asset bundle/locality 风险 | `asset_io_report` |
| HWCAP-NET-01 | A1 | Region Latency Probe | 到边缘/云区域延迟 | `latency_profile` |
| HWCAP-NET-02 | A2 | Streaming Readiness Probe | 云游戏串流可行性 | `stream_profile` |

---

## 2. DEVICE：端侧运行层

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| DEVICE-PROF-01 | A0 | CapabilityProfile Builder | 汇总 HWCAP 为统一画像 |
| DEVICE-VAULT-01 | A0 | Local Privacy Vault | 存储偏好、历史、私有数据 |
| DEVICE-VFS-01 | A0 | Local VFS Overlay | 本地 Mod 预览和安装 |
| DEVICE-PROBE-01 | A0 | Local Probe Runner | 启动游戏、截图、读取状态 |
| DEVICE-MODEL-01 | A1 | Local Embedding Runtime | 本地语义检索 |
| DEVICE-MODEL-02 | A1 | Local Intent Classifier | 简单意图离线解析 |
| DEVICE-SAFE-01 | A0 | Local Mod Safety Guard | 安装前检查风险 |
| DEVICE-CACHE-01 | A1 | Artifact Cache | 模型、工具、Mod 缓存 |
| DEVICE-SYNC-01 | A2 | Consent Sync Agent | 只同步授权数据 |

---

## 3. EDGE：边缘游戏和推理层

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| EDGE-ROUTE-01 | A2 | Region Router | 按延迟和区域调度 |
| EDGE-MATCH-01 | A2 | Mod-aware Match Router | 按 ModStack 匹配 |
| EDGE-CACHE-01 | A2 | Edge Mod Cache | 热门 Mod/资产缓存 |
| EDGE-INFER-01 | A2 | Lightweight Inference Node | 小模型 NPC/推荐 |
| EDGE-PROBE-01 | A2 | Edge Probe Node | 区域性能验证 |
| EDGE-STREAM-01 | A2 | WebRTC Streaming Gateway | 云试玩和审核 |
| EDGE-POLICY-01 | A2 | Regional Policy Gate | 地区合规策略 |
| EDGE-OBS-01 | A2 | Edge Telemetry Collector | 延迟、崩溃、体验指标 |

---

## 4. CLOUD：GameAI Fabric

### CLOUD-CONTROL：控制面

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| CLOUD-CTRL-01 | A1 | Workload API | 接收 build/probe/infer/server 任务 |
| CLOUD-CTRL-02 | A1 | Capability Scheduler | 按资源和区域调度 |
| CLOUD-CTRL-03 | A1 | Cost Controller | 预算、限流、降级 |
| CLOUD-CTRL-04 | A1 | Policy Controller | 权限、风险、合规 |
| CLOUD-CTRL-05 | A1 | Artifact Registry | 工具、模型、资产、Mod 包 |
| CLOUD-CTRL-06 | A1 | Trace Controller | 跨 job trace |
| CLOUD-CTRL-07 | A2 | Energy-aware Scheduler | 成本和能耗优化 |
| CLOUD-CTRL-08 | A2 | Multi-cloud Placement | 云厂商和自建混合 |

### CLOUD-DATA：数据面

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| CLOUD-DATA-01 | A1 | CPU Build Node | 构建、解析、打包 |
| CLOUD-DATA-02 | A1 | GPU Render Node | 运行时验证、截图、视频 |
| CLOUD-DATA-03 | A1 | GPU Infer Node | LLM/多模态/embedding |
| CLOUD-DATA-04 | A1 | Sandbox Node | 高风险工具执行 |
| CLOUD-DATA-05 | A2 | Game Server Node | 多人服务器 |
| CLOUD-DATA-06 | A2 | Stream Node | 云游戏串流 |
| CLOUD-DATA-07 | A2 | Graph Node | 图查询和推荐 |
| CLOUD-DATA-08 | A2 | Batch Simulation Node | 自动试玩集群 |

### CLOUD-WORKLOAD：Workload Descriptor

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| CLOUD-WORK-01 | A1 | WorkloadDescriptor Schema | 统一声明资源需求 |
| CLOUD-WORK-02 | A1 | GPU Feature Requirements | Vulkan/DX/NVENC/VRAM |
| CLOUD-WORK-03 | A1 | Sandbox Requirements | 网络/路径/系统调用 |
| CLOUD-WORK-04 | A1 | Determinism Requirements | seed、版本、输入流 |
| CLOUD-WORK-05 | A2 | Placement Scorer | 资源匹配打分 |
| CLOUD-WORK-06 | A2 | Cache-aware Scheduling | asset/model cache 命中 |

---

## 5. INTENT：意图操作系统

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| INTENT-PARSE-01 | A0 | Natural Language Parser | 中英意图解析 |
| INTENT-TYPE-01 | A0 | Intent Type Classifier | 难度、叙事、美术、机制 |
| INTENT-REF-01 | A0 | Reference Mapper | “魂系”等参考映射 |
| INTENT-CON-01 | A0 | Constraint Compiler | hard/soft/negative constraints |
| INTENT-PREF-01 | A1 | Preference Merger | 用户偏好融合 |
| INTENT-AMB-01 | A0 | Ambiguity Detector | 模糊和冲突 |
| INTENT-CLAR-01 | A1 | Clarification Engine | 生成澄清问题 |
| INTENT-PROBE-01 | A0 | Acceptance Probe Planner | 从目标生成验收探针 |
| INTENT-RISK-01 | A0 | Intent Risk Scorer | 判断是否需要人工确认 |
| INTENT-VERSION-01 | A1 | Intent Versioning | 意图迭代和审计 |

---

## 6. SEMIR：Game Semantic IR

### SEMIR-GRAPH

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| SEMIR-GRAPH-01 | A0 | ContentGraph v3 | 文件、资产、配置、脚本 |
| SEMIR-GRAPH-02 | A0 | SourceSpan | 精确来源定位 |
| SEMIR-GRAPH-03 | A0 | Provenance | 工具、版本、hash |
| SEMIR-GRAPH-04 | A0 | Confidence | 语义置信度 |
| SEMIR-GRAPH-05 | A0 | Evidence Ref | 证据链 |
| SEMIR-GRAPH-06 | A1 | RuntimeObservationGraph | 运行时观察 |
| SEMIR-GRAPH-07 | A1 | OverlayGraph | Mod 叠加 |
| SEMIR-GRAPH-08 | A2 | Cross-engine Semantic Mapping | 跨引擎 ontology |

### SEMIR-ONTOLOGY

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| SEMIR-ONT-01 | A0 | Core Game Ontology | Actor/Item/Quest/Map 等 |
| SEMIR-ONT-02 | A0 | Combat Ontology | HP/Skill/Buff/Damage |
| SEMIR-ONT-03 | A0 | Economy Ontology | Drop/Shop/Reward/Sink |
| SEMIR-ONT-04 | A1 | Narrative Ontology | Dialog/Branch/Cutscene |
| SEMIR-ONT-05 | A1 | Map Ontology | Region/Path/Trigger |
| SEMIR-ONT-06 | A2 | Multiplayer Ontology | Session/Authority/Sync |
| SEMIR-ONT-07 | A2 | Rendering Ontology | Material/LOD/Shader |
| SEMIR-ONT-08 | A3 | Emotion/Experience Ontology | Tension/Relief/Fear/Fun |

---

## 7. ASSET：资产系统

### ASSET-PROV：资产 provenance

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| ASSET-PROV-01 | A0 | AssetManifest | 资产清单 |
| ASSET-PROV-02 | A0 | Asset Hashing | 内容 hash |
| ASSET-PROV-03 | A1 | License Hint Detector | 授权线索 |
| ASSET-PROV-04 | A1 | Generated Asset Metadata | prompt、seed、workflow |
| ASSET-PROV-05 | A1 | Asset Transformation History | 变换链 |
| ASSET-PROV-06 | A2 | Creator Attribution Graph | 创作者归属 |
| ASSET-PROV-07 | A2 | Asset Fingerprint | 版权和重复检测 |

### ASSET-PIPE：资产处理管线

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| ASSET-PIPE-01 | A0 | Image Processor Adapter | 图像尺寸/格式/压缩 |
| ASSET-PIPE-02 | A1 | Audio Processor Adapter | 音频格式/响度 |
| ASSET-PIPE-03 | A1 | Mesh Processor Adapter | 模型、LOD、碰撞 |
| ASSET-PIPE-04 | A1 | OpenUSD Adapter | 场景资产交换 |
| ASSET-PIPE-05 | A1 | Blender Adapter | DCC 自动化 |
| ASSET-PIPE-06 | A1 | ComfyUI Adapter | 生成式资产工作流 |
| ASSET-PIPE-07 | A2 | MaterialX Adapter | 材质标准化 |
| ASSET-PIPE-08 | A2 | Asset Quality Evaluator | 分辨率、风格、性能 |

---

## 8. MECH：玩法机制系统

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| MECH-GRAPH-01 | A0 | MechanismGraph | 机制节点和关系 |
| MECH-EFFECT-01 | A0 | Effect System IR | 技能、buff、副作用 |
| MECH-QUEST-01 | A0 | Quest Dependency Graph | 任务链 |
| MECH-MAP-01 | A0 | Map Reachability Graph | 地图可达性 |
| MECH-ECON-01 | A1 | Economy Flow Graph | 资源产出和消耗 |
| MECH-DIFF-01 | A0 | Difficulty Curve Model | 难度曲线 |
| MECH-BAL-01 | A1 | Balance Constraint Solver | 平衡性约束 |
| MECH-MULTI-01 | A2 | Determinism Validator | 多人确定性 |
| MECH-AUTH-01 | A2 | Server Authority Policy | 服务器权威策略 |
| MECH-EXP-01 | A3 | Experience Objective Model | 体验目标函数 |

---

## 9. PATCH：变换编译器

### PATCH-COMPILER

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| PATCH-COMP-01 | A0 | Target Selector | 从意图选目标节点 |
| PATCH-COMP-02 | A0 | Action Schema Expander | 生成可行动作 |
| PATCH-COMP-03 | A0 | Constraint Filter | 删除违规动作 |
| PATCH-COMP-04 | A0 | Candidate Plan Search | 搜索计划 |
| PATCH-COMP-05 | A0 | Plan Ranker | 质量/成本/风险打分 |
| PATCH-COMP-06 | A0 | Patch Synthesizer | 生成 Patch |
| PATCH-COMP-07 | A0 | Reverse Patch Builder | 回滚 |
| PATCH-COMP-08 | A0 | Probe Generator | 验证计划 |
| PATCH-COMP-09 | A1 | Semantic Merge Resolver | 三路合并 |
| PATCH-COMP-10 | A2 | Cross-version Migration Planner | 游戏版本迁移 |

### PATCH-TYPES

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| PATCH-TYPE-01 | A0 | NumericPatch | 数值修改 |
| PATCH-TYPE-02 | A0 | ScriptPatch | 脚本插入/替换 |
| PATCH-TYPE-03 | A0 | EventPatch | 事件修改 |
| PATCH-TYPE-04 | A0 | RewardPatch | 奖励修改 |
| PATCH-TYPE-05 | A1 | AssetPatch | 资产替换 |
| PATCH-TYPE-06 | A1 | MapPatch | 地图修改 |
| PATCH-TYPE-07 | A1 | EconomyPatch | 经济系统调整 |
| PATCH-TYPE-08 | A1 | NarrativePatch | 对话/剧情 |
| PATCH-TYPE-09 | A2 | RuntimeHookPatch | 运行时 Hook |
| PATCH-TYPE-10 | A2 | MultiplayerPolicyPatch | 多人策略 |

---

## 10. TOOL：工具和引擎网格

### TOOL-ENGINE

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| TOOL-ENG-01 | A0 | EngineAdapter Protocol | 统一引擎适配接口 |
| TOOL-ENG-02 | A0 | miu2d Adapter | 首攻深度适配 |
| TOOL-ENG-03 | A0 | RPG Maker Adapter | 第二结构化引擎 |
| TOOL-ENG-04 | A1 | Unity Adapter | Asset + runtime hook |
| TOOL-ENG-05 | A1 | Godot Adapter | scene/resource/autoload |
| TOOL-ENG-06 | A2 | Unreal Adapter | asset graph/data table |
| TOOL-ENG-07 | A2 | GameMaker Adapter | UndertaleModTool 路线 |
| TOOL-ENG-08 | A2 | Web Game Adapter | JS/WebAssembly/WebGPU |

### TOOL-EXTERNAL

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| TOOL-EXT-01 | A0 | Tree-sitter Adapter | AST |
| TOOL-EXT-02 | A1 | Roslyn/LSP Adapter | C# 语义 |
| TOOL-EXT-03 | A1 | AssetRipper Adapter | Unity 资源 |
| TOOL-EXT-04 | A1 | QuickBMS Adapter | 归档 |
| TOOL-EXT-05 | A2 | FModel/CUE4Parse Adapter | Unreal |
| TOOL-EXT-06 | A1 | Playwright Adapter | 运行时验证 |
| TOOL-EXT-07 | A1 | Semgrep Adapter | 静态扫描 |
| TOOL-EXT-08 | A1 | FFmpeg Adapter | 视频证据 |
| TOOL-EXT-09 | A2 | Blender Adapter | 资产处理 |
| TOOL-EXT-10 | A2 | OpenUSD Adapter | 场景交换 |

### TOOL-GATEWAY

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| TOOL-GW-01 | A0 | Tool Manifest | 能力声明 |
| TOOL-GW-02 | A0 | Schema Validator | 参数校验 |
| TOOL-GW-03 | A0 | Policy Decision | 允许/拒绝 |
| TOOL-GW-04 | A0 | Path Sandbox | 路径隔离 |
| TOOL-GW-05 | A0 | Resource Quota | CPU/GPU/内存/时间 |
| TOOL-GW-06 | A0 | Output Sanitizer | 输出净化 |
| TOOL-GW-07 | A0 | Audit Recorder | 审计 |
| TOOL-GW-08 | A1 | Tool Lockfile | 版本和 hash |
| TOOL-GW-09 | A1 | Signature Verification | 签名 |
| TOOL-GW-10 | A2 | MCP/FastMCP Bridge | 标准工具协议 |

---

## 11. VALID：验证、仿真和自动试玩

### VALID-STATIC

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| VALID-STATIC-01 | A0 | Schema Validator | 格式 |
| VALID-STATIC-02 | A0 | Reference Validator | 引用 |
| VALID-STATIC-03 | A0 | Numeric Range Validator | 数值范围 |
| VALID-STATIC-04 | A0 | Script Safety Validator | 危险 API |
| VALID-STATIC-05 | A0 | Reparse Validator | 修改后重新解析 |
| VALID-STATIC-06 | A1 | Semantic Invariant Validator | 机制不变量 |
| VALID-STATIC-07 | A1 | License Validator | 授权 |
| VALID-STATIC-08 | A2 | Multiplayer Compatibility Validator | 多人兼容 |

### VALID-RUNTIME

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| VALID-RUN-01 | A0 | ProbeSpec Schema | 探针描述 |
| VALID-RUN-02 | A0 | Game Launcher | 启动游戏 |
| VALID-RUN-03 | A0 | State Read Bridge | 读取状态 |
| VALID-RUN-04 | A0 | Screenshot Capture | 截图证据 |
| VALID-RUN-05 | A0 | Console Log Capture | 日志 |
| VALID-RUN-06 | A1 | Video Capture | 视频证据 |
| VALID-RUN-07 | A1 | Probe Flake Manager | 重试和稳定性 |
| VALID-RUN-08 | A1 | Hardware Profile Matrix | 多硬件验证 |
| VALID-RUN-09 | A2 | Cloud Probe Executor | 云端并行 |

### VALID-PLAYTEST

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| VALID-PLAY-01 | A1 | Input Recorder/Replayer | 输入流复现 |
| VALID-PLAY-02 | A1 | Goal-directed Probe Agent | 目标探针 |
| VALID-PLAY-03 | A2 | Combat Simulator | 战斗仿真 |
| VALID-PLAY-04 | A2 | Quest Completion Agent | 任务测试 |
| VALID-PLAY-05 | A2 | Map Navigation Agent | 路径测试 |
| VALID-PLAY-06 | A3 | Experience Evaluator | 体验评估 |
| VALID-PLAY-07 | A3 | Population Simulator | 玩家群体仿真 |

### VALID-BENCH

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| VALID-BENCH-01 | A0 | UdifyBench Schema | benchmark 格式 |
| VALID-BENCH-02 | A0 | Golden Case Runner | 回归运行 |
| VALID-BENCH-03 | A0 | Failure Snapshot | 失败快照 |
| VALID-BENCH-04 | A1 | Score Aggregator | 评分 |
| VALID-BENCH-05 | A1 | Regression Gate | CI 阈值 |
| VALID-BENCH-06 | A2 | Public Benchmark Registry | 公开数据集 |

---

## 12. SUPPLY：供应链和发布

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| SUPPLY-PKG-01 | A0 | ModManifest | 包元数据 |
| SUPPLY-PKG-02 | A0 | ModPackage Builder | 打包 |
| SUPPLY-PKG-03 | A0 | Reverse Package | 回滚 |
| SUPPLY-PKG-04 | A1 | Validation Certificate | 验证证书 |
| SUPPLY-PKG-05 | A1 | SBOM Generator | 物料清单 |
| SUPPLY-PKG-06 | A1 | Signature Service | 签名 |
| SUPPLY-PKG-07 | A1 | License Report | 授权报告 |
| SUPPLY-PKG-08 | A2 | CDN Publisher | 分发 |
| SUPPLY-PKG-09 | A2 | Compatibility Certificate | 兼容证书 |
| SUPPLY-PKG-10 | A3 | Creator Revenue Ledger | 分成账本 |

---

## 13. RUNTIME：运行时个性化和 LiveOps

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| RUNTIME-PERS-01 | A1 | Session Preference Model | 会话偏好 |
| RUNTIME-PERS-02 | A1 | Startup Config Selector | 启动前配置 |
| RUNTIME-PERS-03 | A2 | Runtime Dialog Personalizer | 对话微调 |
| RUNTIME-PERS-04 | A2 | NPC Memory Bridge | NPC 记忆 |
| RUNTIME-PERS-05 | A2 | Dynamic Difficulty Policy | 动态难度 |
| RUNTIME-PERS-06 | A2 | Server Authority Guard | 多人权限 |
| RUNTIME-LIVE-01 | A2 | LiveOps Patch Candidate | 运营补丁候选 |
| RUNTIME-LIVE-02 | A2 | A/B Assignment | 分桶 |
| RUNTIME-LIVE-03 | A2 | Rollback Controller | 回滚 |
| RUNTIME-LIVE-04 | A3 | Real-time World Mutation | 实时世界变换 |

---

## 14. ECO：Udiface 生态

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| ECO-MARKET-01 | A1 | Mod Listing | Mod 页面 |
| ECO-MARKET-02 | A1 | Semantic Search | 意图搜索 |
| ECO-MARKET-03 | A1 | Quality Score | 质量评分 |
| ECO-MARKET-04 | A1 | Compatibility Matrix | 兼容矩阵 |
| ECO-MARKET-05 | A2 | Template Library | 模板库 |
| ECO-MARKET-06 | A2 | Fork and Remix Graph | 分叉图 |
| ECO-MARKET-07 | A2 | Creator Attribution | 归因 |
| ECO-MARKET-08 | A2 | Review and Moderation | 审核 |
| ECO-MARKET-09 | A3 | Bounty System | 悬赏 |
| ECO-MARKET-10 | A3 | Creator Economy | 收益分成 |

---

## 15. GOV：治理、安全和合规

### GOV-SEC

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| GOV-SEC-01 | A0 | Risk Taxonomy | R0-R4 风险等级 |
| GOV-SEC-02 | A0 | Prompt Injection Guard | 输入/工具输出隔离 |
| GOV-SEC-03 | A0 | Secret Scanner | secret 检测 |
| GOV-SEC-04 | A0 | Dangerous Tool Policy | 高危工具策略 |
| GOV-SEC-05 | A1 | RBAC | 权限 |
| GOV-SEC-06 | A1 | Audit Chain | 链式审计 |
| GOV-SEC-07 | A1 | OPA Policy Adapter | 策略引擎 |
| GOV-SEC-08 | A2 | Sandbox Runtime | gVisor/Firecracker |

### GOV-CONTENT

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| GOV-CONT-01 | A1 | Content Policy Classifier | 内容政策 |
| GOV-CONT-02 | A1 | Copyright Risk Detector | 版权风险 |
| GOV-CONT-03 | A1 | Age Rating Hint | 分级提示 |
| GOV-CONT-04 | A2 | Human Review Queue | 人工复审 |
| GOV-CONT-05 | A2 | Appeal Workflow | 申诉 |
| GOV-CONT-06 | A3 | Regional Compliance Rules | 地区规则 |

### GOV-PRIVACY

| ID | 优先级 | 模块 | 职责 |
|---|---|---|---|
| GOV-PRI-01 | A0 | Data Minimization Policy | 最小化 |
| GOV-PRI-02 | A0 | Local-first Preference Store | 本地优先 |
| GOV-PRI-03 | A1 | Consent Manager | 授权 |
| GOV-PRI-04 | A1 | Deletion Workflow | 删除 |
| GOV-PRI-05 | A2 | Anonymization Pipeline | 匿名化 |
| GOV-PRI-06 | A2 | Training Data Firewall | 训练隔离 |

---

## 16. 最小切入顺序

### Track 1：服务当前 Udify Core

第一批：

- HWCAP-CPU-01
- HWCAP-GPU-01
- HWCAP-GPU-02
- DEVICE-PROF-01
- SEMIR-GRAPH-01 到 SEMIR-GRAPH-05
- PATCH-COMP-01 到 PATCH-COMP-08
- VALID-STATIC-01 到 VALID-STATIC-05
- VALID-RUN-01 到 VALID-RUN-05

第二批：

- TOOL-ENG-02
- TOOL-ENG-03
- TOOL-EXT-01
- TOOL-EXT-06
- TOOL-GW-01 到 TOOL-GW-08
- VALID-BENCH-01 到 VALID-BENCH-05

### Track 2：服务云验证

第一批：

- CLOUD-WORK-01 到 CLOUD-WORK-04
- CLOUD-CTRL-01 到 CLOUD-CTRL-06
- CLOUD-DATA-01 到 CLOUD-DATA-04
- VALID-RUN-09

### Track 3：服务生态

第一批：

- SUPPLY-PKG-01 到 SUPPLY-PKG-07
- ECO-MARKET-01 到 ECO-MARKET-04
- GOV-SEC-01 到 GOV-SEC-06

---

## 17. 模块间关键依赖

```text
HWCAP -> DEVICE -> VALID-RUNTIME
HWCAP -> CLOUD-WORK -> CLOUD-CTRL -> CLOUD-DATA
INTENT -> SEMIR -> PATCH -> VALID -> SUPPLY -> ECO
TOOL -> SEMIR
TOOL -> PATCH
TOOL -> VALID
GOV -> TOOL
GOV -> SUPPLY
GOV -> ECO
MECH -> PATCH
MECH -> VALID
ASSET -> SEMIR
ASSET -> SUPPLY
```

最关键的 5 条主线：

1. **Intent to Patch**：INTENT -> SEMIR -> PATCH。
2. **Patch to Trust**：PATCH -> VALID -> SUPPLY。
3. **Tool to Evidence**：TOOL -> SEMIR -> Evidence。
4. **Hardware to Scheduling**：HWCAP -> CLOUD-WORK -> CLOUD。
5. **Feedback to Evolution**：ECO -> INTENT/MECH/PATCH。

---

## 18. 长期成功判据

模块完成不等于工业重塑。真正成功要看：

1. 一个普通玩家能用自然语言安全生成 Mod。
2. 一个 Mod 能自动获得兼容性和验证证书。
3. 一个成功 Mod 模板能跨游戏复用。
4. 一个开发团队能用自动仿真替代大量重复 QA。
5. 一个游戏发布后能根据社区反馈生成可审查 LiveOps Patch。
6. 一个新硬件能力出现后，系统能通过 CapabilityProfile 自动利用或降级。
7. 一个开源工具变化后，Tool Lockfile 和 contract test 能捕捉影响。
8. 一个生态中的创作者能被正确归因、分成和保护。
