# AGENTS.md — Udify web/

> web/ 前端门禁与运行时契约。本文件自根 AGENTS.md 移入，内容逐字保留。

### Web 门禁

```bash
cd web
pnpm install --frozen-lockfile
pnpm audit:prod
pnpm lint
pnpm typecheck
pnpm test --run
pnpm build
pnpm test:e2e
```

iter8 真实产品验收：`pnpm exec playwright test -c playwright.real.config.ts`。默认独占 13180/18765，使用隔离临时合成游戏和状态目录，不复用已有服务。`REAL_E2E_WEB_MODE=production` 使用已构建的前端；构建时 `NEXT_PUBLIC_UDIFY_API` 必须与 `REAL_E2E_API_PORT` 一致。生产构建与 dev 验收不能同时写 `.next`。真实 API 测试为根目录 `tests/e2e/test_product_workflow.py`，与 mock UI 验收分开记录。

默认 mock 配置排除 `real-workflow.spec.ts`，以 BrowserContext 路由拦截所有 `/api/` 请求，不依赖编译进前端的 API 端口。含 WebGL 的浏览器验收固定单 worker，避免本地 GPU 并发资源争用；输出放在仓库 `.ai-bridge/playwright-mock-results`，不覆盖已跟踪的历史报告。端口占用时使用 `E2E_PORT` 指定空闲端口。

Playwright E2E 通过 route interception 使用明确的 mock API；真实本地验收需要另启 `udify serve`。公开配置来自 `NEXT_PUBLIC_UDIFY_CONFIG` 与无凭据、根级回环 `NEXT_PUBLIC_UDIFY_API`，必须经过 Zod 运行时解码；localStorage 异常必须保留内存安全配置与可见诊断。

供应链约束：Node.js ≥20.9（CI 22）；`pnpm.overrides` 将 Next 的 `sharp` 固定到 0.35.3、`postcss` 固定到 8.5.25，并把 `postcss>nanoid` 固定到 3.3.18（pnpm 10 拒绝三级选择器，无法直接写 `next>postcss>nanoid`），覆盖经 Next→postcss 传递的 GHSA-2v37-7h3g-55p8。原因是 Next 15.5.22 已是当前 15.5 最新 patch，但其声明范围仍会解析到受 GHSA-f88m-g3jw-g9cj / GHSA-6g55-p6wh-862q / GHSA-r28c-9q8g-f849 影响的版本。不得删除 override 而不同时证明 production audit、build 与 E2E。
