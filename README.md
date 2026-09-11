# Udify — 魔改一切的创作操作系统

> **意图驱动的内容演化系统** | Intent-Driven Content Evolution System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

---

## 这是什么？

Udify 是一个通用的内容编译器（Content Compiler）。

你有一个游戏、一首歌、一段视频、一部小说——你对它有一个模糊的改造想法（"我想让这个游戏更难，像魂系那样""我想把这首歌改成爵士版""我想把这个小说做成互动视觉小说"）。

Udify 会：
1. **感知** —— 理解原始内容的结构、机制、风格
2. **识别** —— 将你的自然语言愿望转化为精确的改造目标
3. **规划** —— 将目标拆解为可执行的原子操作序列
4. **执行** —— 全自动完成所有改造步骤
5. **评估** —— 检查改造质量，确保可运行、可体验
6. **学习** —— 记住你的偏好，下次改造更懂你

然后，你的魔改作品会被发布到 **Udiface** —— 一个类似 HuggingFace 的魔改内容运行与分发平台，每个项目都能形成自己的创作者生态。

---

## 核心理念

### 三个根本性洞见

1. **创作是变换，不是生成** —— 所有创作都是将已有信息从一种形式转化为另一种形式。Udify 将这种变换自动化。
2. **意图比技术更重要** —— 用户关心的是"我想让这个角色更悲情"，不是"如何用 Maya 调整骨骼权重"。
3. **生态即产品** —— 单个工具价值有限，但创作-分发-演化的完整闭环具有网络效应。

### 多学科根基

Udify 的根基深植于多个学科：

- **生物进化论** —— 魔改是变异，用户偏好是选择压力，Udiface 是数字生态学
- **统计物理** —— 内容作为复杂系统，存在相变与临界点，熵调控审美
- **数学** —— 范畴论定义合法变换，拓扑导航内容空间，图论生成执行计划
- **哲学** —— 过程本体论视内容为永恒的生成，实用主义认识论指导 LLM 的使用
- **社会学** —— 文化资本民主化，参与式文化的自动化升级
- **控制论** —— 多层反馈循环，层级控制，抗脆弱性设计
- **信息哲学** —— 信息作为基本存在范畴，塑造信息环境的责任

---

## 项目文档

| 文档 | 内容 | 阅读顺序 |
|------|------|---------|
| **[VISION.md](docs/VISION.md)** | 项目愿景、多学科深度推演、核心命题、项目意义 | **第一** |
| **[PLAN.md](docs/PLAN.md)** | 四阶段路线图、模块拆解、技术栈、里程碑、风险 | **第二** |
| **[ARCHITECTURE.md](docs/ARCHITECTURE.md)** | 系统架构、组件设计、数据模型、接口协议 | **第三** |
| **[TECHNICAL-DOCUMENTATION-INDEX.md](docs/TECHNICAL-DOCUMENTATION-INDEX.md)** | v3 技术文档索引、阅读顺序、维护规则 | **工程入口** |
| **[RESEARCH-OSS-INTEGRATION-2026.md](docs/RESEARCH-OSS-INTEGRATION-2026.md)** | 开源生态调研、可集成框架、自研算法突破点 | **v3 调研** |
| **[ARCHITECTURE-OSS-OPTIMIZED-v3.md](docs/ARCHITECTURE-OSS-OPTIMIZED-v3.md)** | 开源优先的 v3 优化架构 | **v3 架构** |
| **[MODULE-ATTACK-MAP-v3.md](docs/MODULE-ATTACK-MAP-v3.md)** | 细化到模块和任务 ID 的攻坚地图 | **v3 执行** |
| **[RESEARCH-AI-NATIVE-GAME-INDUSTRY-STACK-2026.md](docs/RESEARCH-AI-NATIVE-GAME-INDUSTRY-STACK-2026.md)** | 从芯片、主机、游戏软件栈到云基础设施的 AI 原生游戏工业调研 | **工业调研** |
| **[BLUEPRINT-AI-NATIVE-GAME-INDUSTRY-v1.md](docs/BLUEPRINT-AI-NATIVE-GAME-INDUSTRY-v1.md)** | AI 原生游戏工业技术框架蓝图 | **工业蓝图** |
| **[MODULE-ATTACK-MAP-AI-GAME-INDUSTRY.md](docs/MODULE-ATTACK-MAP-AI-GAME-INDUSTRY.md)** | 宏大蓝图拆解到最细模块的攻坚地图 | **工业执行** |
| **[DEEP-TECHNICAL-MODULE-SPEC-AI-GAME-v1.md](docs/DEEP-TECHNICAL-MODULE-SPEC-AI-GAME-v1.md)** | 底层模块 schema、状态、失败模式、指标、测试夹具 | **深层规格** |
| **[INTERFACE-CONTRACTS-AI-GAME-INDUSTRY-v1.md](docs/INTERFACE-CONTRACTS-AI-GAME-INDUSTRY-v1.md)** | 模块间接口契约、数据所有权、确认矩阵、错误码 | **接口契约** |
| **[EXECUTION-PATHS-AI-GAME-INDUSTRY-v1.md](docs/EXECUTION-PATHS-AI-GAME-INDUSTRY-v1.md)** | 端到端执行路径和测试矩阵 | **执行路径** |
| **[SYSTEM-FUNCTIONAL-DESIGN-GUIDE-v1.md](docs/SYSTEM-FUNCTIONAL-DESIGN-GUIDE-v1.md)** | 从整体到局部的系统功能域、子模块、验收和实施顺序 | **功能设计** |
| **[PROJECT-RESTRUCTURING-IMPLEMENTATION-MAP-v1.md](docs/PROJECT-RESTRUCTURING-IMPLEMENTATION-MAP-v1.md)** | 目标目录、现有代码迁移、Wave 计划和第一阶段任务卡 | **重拆实施** |

---

## 路线图

### Phase 1: 单点突破 (M1-M6, 2026)
游戏 Mod 自动化。证明非技术用户能用自然语言产出可玩 Mod。

### Phase 2: 多媒介扩展 (M7-M12, 2026)
扩展到音乐、视频、小说。实现跨媒介转换。

### Phase 3: 平台与生态 (M13-M24, 2027)
Udiface 上线。创作者经济、社区治理、开放 API。

### Phase 4: 操作系统化 (M25-M48, 2028-2029)
实时魔改、多智能体协作、自演化系统、通用内容协议。

---

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.12+, FastAPI, sqlite3 WAL + 文件工件（本地模式） |
| 前端 | Next.js 15, React 19, TypeScript strict, Tailwind 4, TanStack Query, Zod |
| 交互/差异 | Radix UI primitives, jsdiff, Lucide |
| 测试 | pytest, Ruff, MyPy 子集门禁；Vitest/Testing Library/MSW；Playwright Chromium |
| 预留而非当前依赖 | PostgreSQL/Redis、Docker/Kubernetes、云部署、多租户认证 |

---

## 快速开始（5 分钟）

> 当前产品入口：miu2d 的明确数值意图 → 目标澄清或带证据计划 → 人工批准 → 静态检查 → ModPackage（本地单用户）。生成包不会安装或改写原游戏；撤销包会禁用后续下载，不会收回用户已另存的 ZIP。真实游戏运行、LLM 意图增强与其他引擎的浏览器支持仍在后续路线中。

```bash
# 1. 安装（Python 3.12+）
pip install -e ".[dev]"

# 2. 跑后端测试（使用安装项目依赖的虚拟环境）
python3 -m pytest tests/ -q

# 3a. 命令行方式：直接对游戏目录下达意图（VFS 预览，不碰原文件）
udify --game-root /path/to/miu2d-game mod "把Boss的血量翻倍"

# 3b. 产品方式：启动后端 + 前端工作台
udify serve                               # API: http://127.0.0.1:8765/api/docs
cd web && pnpm install --frozen-lockfile
pnpm dev                                  # 工作台: http://localhost:3000

# 4. Web 阻塞门禁（生产 build 后 Playwright 会启动 next start）
pnpm audit:prod                           # high/critical production advisory 阻塞
pnpm lint && pnpm typecheck && pnpm test --run
pnpm build && pnpm test:e2e
```

工作台流程：填游戏目录 + 明确意图（例如“把第一个 Boss 的攻击力翻倍”）→ 有歧义时选择候选 → 看文件 DIFF / 操作证据 / 风险档位 → 批准 → 静态产物检查 → 下载或撤销 ModPackage。序数依据相对 INI 文件路径及文件内 section 顺序，不代表游戏剧情出场顺序；目标排除、多个不同选择器等未支持语句会明确要求重新描述，不猜测修改。

可使用仓库内合成资产 `tests/fixtures/miu2d/product` 试用。API 的 `--state-dir` 必须在游戏目录外；审阅计划、原文件与下载包均有摘要校验，源文件发生变化时需重新创建任务。澄清与审阅等待状态可以在刷新和后端重启后继续。

公开配置使用 `NEXT_PUBLIC_UDIFY_CONFIG`（v1 JSON）与 `NEXT_PUBLIC_UDIFY_API`（仅接受无凭据、根级回环 HTTP URL，可带端口）；非法值或不可用 localStorage 会回退到内存安全配置并在设置面板显示诊断。`pnpm test:e2e` 使用 mock API；`pnpm exec playwright test -c playwright.real.config.ts` 另起真实 FastAPI 与前端，使用隔离的合成游戏和状态目录，验证下载包字节、澄清、历史与撤销。默认真实验收端口为 13180/18765，可以通过 `REAL_E2E_PORT`/`REAL_E2E_API_PORT` 覆盖；不复用已有服务。

Web 要求 Node.js ≥20.9（CI 使用 Node 22）。Next 15.5.22 当前上游仍声明易受新公告影响的 `sharp ^0.34.3` 与 `postcss 8.4.31`，因此 lockfile 通过定向 pnpm override 固定 Next 的传递依赖为 `sharp 0.35.3`、`postcss 8.5.25`；修改 override 后必须重新运行 frozen install、`pnpm audit:prod`、build 和 E2E。

---

## 贡献

我们欢迎跨学科的贡献——不仅是代码，还包括：

- 理论框架的完善（哲学、美学、社会学视角）
- 新媒介类型的解析器与生成器
- 原子操作的实现
- 社区治理机制的设计
- 文档与教程

请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)（即将添加）。

---

## 许可

MIT License — 详见 [LICENSE](LICENSE) 文件。

---

> **"我们不是要让机器取代创作者，而是要让每个人都成为创作者。"**
>
> —— Udify 宣言
