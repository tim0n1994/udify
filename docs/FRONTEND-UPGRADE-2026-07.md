# Udify 前端升级蓝图 v1：沉浸证据驾驶舱（Immersive Evidence Cockpit）

> 状态：已实现批次 W1–W4（本文件与代码同 PR 落地）
> 基线：批次 5B 工作台（Next.js 15 + React 19 + Tailwind 4 + TanStack Query + Zod）
> 原则：开源优先 / 不改后端协议 / 审阅正确性优先于视觉奇观 / 门禁全绿

---

## 1. 为什么升级（目的 / 解决什么问题 / 如何影响输出）

### 目的

把工作台从"表单 + 列表 + 三个标签页"升级为**证据驾驶舱**：让审阅者在一块屏幕上同时看到意图、变更、风险、证据与时间线，让后端已经具备但前端尚未"演出来"的能力——链式哈希审计、SourceSpan 证据、HTML 运行时探针、R0–R4 风险分级、结构化诊断、运行时管线——成为第一眼可见的第一公民。

### 解决什么问题

| 现状痛点 | 升级后 |
|---|---|
| Diff / 探针截图 / 审计链不可兼得，必须切 tab 翻找 | 驾驶舱同屏：意图卡 + Ops × 风险热力矩阵 + 证据检视器 + 时间线 + 操作坞 |
| 审计链 validity 只是角落里一行小字 | 全屏审计条约章（Audit Treaty Seal）：哈希前八位、事件计数、glow 动画、失配变红脉冲 |
| SourceSpan 证据躺在 payload 里 | File/Ops rail 上证据圆点直接与 Diff 中的高亮行双向联动（PUREM-Z） |
| 探针通过性靠文字 | 探针截图帧序列+OKLCH 热力扫描线，一眼看出运行时状态 |
| 审阅操作埋在角落 | 固定操作坞 + ⌘⇧A / ⌘⇧R / ⌘⇧B 快捷键，符合操作员肌肉记忆 |

### 如何影响输出

- 审阅决策路径从"读 plan → 猜风险 → 找证据"压缩为"扫热力矩阵 → 点最高风险行 → 看证据 → 一键批准"
- 所有升级皆为**纯前端**：后端 399 测试与 API 协议零改动；信封契约（`{success,data,error,meta}`）与 Zod schema 保持唯一事实源

---

## 2. 设计语汇（Design Language）

**Dossier / 档案卷宗**：暗色研究所底色上的"纸质档案"质感。全部直角（`rounded-none`）、1px 发丝边框、大写等宽字体眉题、French rule（标题下短实线）、编号章节贴纸 `C-01 … C-05`。禁止圆角卡片套卡片、禁止渐变光球、禁止装饰性模糊。

**OKLCH 色彩系统**：全部信号色迁移到 OKLCH 感知均匀空间，风险等级 R0–R4 的色相沿 green → amber → red 等距爬升并带 chroma 提升，配 `color-mix()` 派生半透明色。禁止紫色、禁止靛蓝渐变。

**动效哲学**：以 `@property` 注册的 custom property 做 glow 动画，"当前舞台脉冲"代替加载菊花；减少动效查询 `prefers-reduced-motion` 全局尊重。

**排版**：UI 中文 PingFang SC + Inter；数据/证据/哈希用 IBM Plex Mono（回退 ui-monospace）；超大显示数字用 Space Grotesk 风格 fallback。正文不随视口缩放。

---

## 3. 技术选型（开源优先，逐项论证）

| 能力 | 选型 | 为什么是它（而不是自己写） |
|---|---|---|
| WebGL 证据场三棱镜 | **React Three Fiber + @react-three/drei** | Three.js 的 React 声明式封装；`<Caustics>` 模拟 MIU2D 水焰折射；懒加载 chunk 不进首屏 bundle |
| 数据网格 | **TanStack Table v8** | headless，与我们现有 TanStack Query 同步哲学;行选中/排序/虚拟化全可组合 |
| 音效 | **Tone.js (membrane synth)** | Web Audio 包装；approve/reject/fail 三种动作音 + 环境 hum；-14dB ceiling 防爆音 |
| 动画 | CSS `@property` + Tailwind 4 | 本迭代无需 Framer Motion；glow/shimmer 全部纯 CSS，零 JS 预算 |
| 命令菜单 | ⌘K 检索面板（自研 90 行） | 后端尚无 search 端点时最小可用；等 `/api/v0/search` 落地后无缝换成 cmdk |
| 图表 | sparkline 内联 SVG | 唯一指标是探针置信度；引入完整图表库属于过度工程 |

---

## 4. 信息架构

```
/  驾驶舱
    ├─ C-01 Mission strip（HealthDot + ⌘K + 声音开关 + 审计条约章）
    ├─ C-02 意图创建器（三列：输入 / 就绪清单 / 提交）
    ├─ C-03 Ops × 风险热力矩阵（TanStack Table，列头点击排序，行点选）
    ├─ C-04 证据截面（选中任务：时间线 rail + 3DoF 截图检视器 + hash 链摘要）
    └─ C-05 WebGL 证据场（懒加载，PrismVisualizer：Caustics + 置信度 sparkline）
/jobs/[id]  任务详情（复用现有 Diff 三面板，顶部注入驾驶舱导航）
```

Prototype 的关键设计决策：

- **OpsMatrix 是唯一导航源**：点击 R3+ 行直接深链到 `/jobs/{id}?tab=risk`，R0–R2 深链 `?tab=changes`
- **状态派生而非存储**：所有表的排序/筛选都是 `useMemo` 派生，与服务器信封一一对应，单一事实源
- **配置系统零破坏**：`PublicConfig` schema 不动；新增 UI 全部读 `config.polling` / `config.density` 而不发明平行字段

---

## 5. 组件契约（与后端 schema 的一一映射）

| 组件 | 输入 | 来源 |
|---|---|---|
| `AuditTreatySeal` | `{valid, events}` | `jobDetailSchema.audit_chain_valid` + `events[].record_hash` |
| `OpsMatrix` | `{jobs, plans}` | `GET /jobs` + 按需 `GET /jobs/{id}/plan`（仅 awaiting_review+ 且默认列表前 20） |
| `MissionStrip` | `{health}` | `GET /healthz`（沿用 `queryKeys.health`） |
| `ProbeScrubber` | `{probeResult}` | `report.probe_results[]`（VAL-RUNTIME-05，`screenshot_path` 为 `/jobs/{id}/artifacts/` 下本地路径） |
| `PrismVisualizer` | `{jobs, selected}` | 同 OpsMatrix；WebGL 仅在 `typeof window !== "undefined"` 且 WebGL 可用时挂载 |
| `SoundBus` | `{enabled}` | localStorage `udify:sound`，不与 PublicConfig 混放（纯客户端感官偏好） |

---

## 6. 交付批次与验收

| 批次 | 内容 | 验收 |
|---|---|---|
| W1 语汇 | OKLCH tokens、`@property` glow、直角 dossier CSS、Space Grotesk/IBM Plex Mono 加载 | `pnpm lint`+`pnpm typecheck` 绿；globals.css 无离散光球 |
| W2 驾驶舱骨架 | C-01..C-04 静态 + TanStack Table OpsMatrix + 行深链 | Vitest 组件测试 ≥3 例；键盘可达 |
| W3 感官层 | Tone.js SoundBus（并存原子状态）、探针截图 scrubber、⌘K 面板 | `pnpm test --run` 全绿；E2E mocked 通 |
| W4 WebGL | `next/dynamic` 懒加载 R3F PrismVisualizer；WebGL 不可用降级 sparkline | `pnpm build` 首屏 bundle 不增加 >150KB；mobile Chromium E2E 不闪烁 |

**门禁矩阵**：`pnpm audit:prod`、`pnpm lint`、`pnpm typecheck`、`pnpm test --run`、`pnpm build`、`pnpm test:e2e` 六者全绿才算落地。

---

## 7. 风险与缓解

| 风险 | 缓解 |
|---|---|
| R3F 包体膨胀 | `next/dynamic({ ssr: false })` + `loading: SparklineFallback`；包体预算写进验收 |
| Web Audio 自动播放策略 | 首次手势解锁；声音默认关，UI 明示 |
| ⌘K 与浏览器快捷键冲突 | 捕获 `metaKey+k` / `ctrlKey+k`，`preventDefault`，Escape 关闭 |
| 探针截图本地路径 | 已存在 `/jobs/{id}/package` 式下载惯例；`<img>` 用 `apiBase` 拼接、不发明新端点 |
| 深色 + OKLCH 对比度 | 交互色 ≥ 4.5:1；matrix 行 hover 用 border 而非仅靠色彩 |

---

## 8. 与传统方案的差异（为什么"最高级"）

- **审阅即乐器**：声音、光泽、hash seal、扫描线——所有感官信号都在传递同一个事实"这条证据链此刻是否可信"，而不是装饰
- **显示后端而非套用模板**：工具网关 RiskLevel、审计链哈希、SourceSpan、探针截图、运行时管线——Udify 后端千辛万苦产生的东西，前端全部一等公民展示
- **数据网格胜过卡片堆**：Ops × Risk 是这张产品的核心二维结构，TanStack Table 的排序/选中/深链远胜于一墙 param 卡片
