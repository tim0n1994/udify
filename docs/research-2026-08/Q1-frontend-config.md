# Q1：前端可配置渲染架构深度研究

## 项目背景

Udify 是意图驱动的自动化游戏 Mod 平台。当前前端是 Next.js 15 (App Router) + React 19 + TypeScript strict + Tailwind v4 + TanStack Query v5 + Radix primitives + Zod 4 运行时契约。已有两个页面：Job 控制台 (/) 和 Job 审阅台 (/jobs/[id])，后者包含三标签页：Plan Diff Viewer、Risk Review、Report。

当前前端是硬编码的两页面，无法动态配置视图布局、无法插件式扩展审阅组件、无法让用户自定义审阅面板组合。验收标准要求"实现灵活可以配置的前端"。

## 需要深度研究的问题

1. **可配置前端架构模式调研**：研究 2025-2026 年最成熟的开源方案，用于构建"可配置、可扩展、插件式"的前端渲染层。重点对比：
   - 低代码/可视化搭建框架（如：基于 schema 的动态渲染、json-driven layout）
   - 组件注册与动态加载机制（React.lazy、Module Federation、component registry patterns）
   - Dashboard/widget 框架（如可拖拽布局、面板系统）

2. **成熟开源组件库与工具链选型**：针对"工程级审阅工作台"场景，调研并推荐：
   - 布局系统：可拖拽面板/栅格布局（如 react-grid-layout、allotment、dnd-kit-based splitter、Mosaic）
   - 代码/Diff 查看：react-diff-viewer、monaco-editor、codemirror、shiki 高亮
   - 表格与数据网格：TanStack Table v8、ag-grid community
   - 图表与可视化：recharts、visx、nivo
   - 状态与配置持久化

3. **Schema 驱动的视图配置**：如何用 JSON/YAML schema 描述页面布局（面板位置、可见性、数据绑定），运行时渲染并持久化用户偏好。对比现有方案的优劣。

4. **设计系统与组件架构**：如何在不引入 Storybook 的情况下保持组件质量？shadcn/ui vs Radix 直接使用的取舍？暗色工程风审阅台的设计 token 体系。

5. **性能约束**：Next.js 15 App Router 下动态组件加载、流式渲染（React Suspense）、RSC vs Client Component 边界、Bundle 分割策略。审阅台可能加载大 diff（万行级），如何保证不卡顿。

## 交付物

- 开源选型对比表（至少 8 个候选，含 star/活跃度/许可证/兼容性/维护风险）
- 推荐架构方案（含组件关系图、数据流、配置 schema 示例）
- 集成到现有 Next.js 15 + Tailwind v4 项目的具体路径（依赖清单、目录结构、迁移步骤）
- 风险评估（供应链安全、版本锁定、Breaking change 风险）
- 必须给出可运行的代码示例（配置 schema 定义、动态渲染器、面板注册）

## 约束

- 优先使用成熟开源（>1k stars，活跃维护，MIT/Apache 许可）
- 不自研已有成熟方案的能力（如拖拽布局、diff 渲染、数据网格）
- 必须兼容 Next.js 15 App Router + React 19 + Tailwind v4
- 本地单用户模式，不做多用户/认证/云部署
- 现有依赖不可降级（Zod 4、Radix、TanStack Query 5）
