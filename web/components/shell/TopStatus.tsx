"use client";

import { Settings } from "lucide-react";
import Link from "next/link";
import { HealthDot } from "@/components/HealthDot";
import { useConfig } from "@/lib/config";

export function TopStatus() {
  const {
    config,
    diagnostics,
    resetPreferences,
    setDefaultJobTab,
    setDensity,
  } = useConfig();
  return (
    <header className="sticky top-0 z-30 flex h-12 items-center border-b border-edge-strong bg-bench/95 px-4 backdrop-blur sm:px-6">
      <Link href="/" className="flex items-baseline gap-2">
        <span className="font-[family-name:var(--font-display)] text-lg font-bold tracking-[0.14em] text-accent">
          {config.brand.name}
        </span>
        <span className="text-faint">/</span>
        <span className="font-mono text-[10px] uppercase tracking-[0.22em] text-muted">
          {config.brand.product} · 证据舱
        </span>
      </Link>
      <div className="ml-auto flex items-center gap-4">
        <span className="hidden font-mono text-[10px] text-muted sm:inline">local · single-user</span>
        <span className="h-5 w-px bg-edge" aria-hidden />
        <HealthDot />
        <details className="group relative">
          <summary
            className={`flex cursor-pointer list-none items-center gap-1.5 font-mono text-[10px] ${diagnostics.length > 0 ? "text-err" : "text-muted"}`}
            aria-label="显示设置"
          >
            <Settings className="h-4 w-4" aria-hidden />
            <span className="hidden sm:inline">设置</span>
          </summary>
          <div className="absolute right-0 top-8 z-40 w-72 border border-edge-strong bg-panel p-4 shadow-2xl">
            <h2 className="text-sm font-semibold text-ink">显示设置</h2>
            <label className="control-label mt-3 block">
              界面密度
              <select
                value={config.density}
                onChange={(event) => setDensity(event.target.value as "comfortable" | "compact")}
                className="mt-1.5 min-h-9 w-full border border-edge-strong bg-bg px-2 text-xs text-ink"
              >
                <option value="comfortable">舒适</option>
                <option value="compact">紧凑</option>
              </select>
            </label>
            <label className="control-label mt-3 block">
              默认 Job 标签页
              <select
                value={config.defaultJobTab}
                onChange={(event) => setDefaultJobTab(event.target.value as "changes" | "risk" | "report")}
                className="mt-1.5 min-h-9 w-full border border-edge-strong bg-bg px-2 text-xs text-ink"
              >
                <option value="changes">修改计划</option>
                <option value="risk">风险审阅</option>
                <option value="report">验证报告</option>
              </select>
            </label>
            {config.features.showConfigDiagnostics && diagnostics.length > 0 ? (
              <div role="status" className="mt-3 border border-err/40 bg-err/10 p-2 text-[11px] text-err">
                {diagnostics.map((diagnostic) => (
                  <p key={`${diagnostic.source}-${diagnostic.code}`}>{diagnostic.code}: {diagnostic.message}</p>
                ))}
              </div>
            ) : null}
            <button type="button" onClick={resetPreferences} className="mt-3 font-mono text-[11px] text-muted underline hover:text-ink">
              重置本地显示偏好
            </button>
          </div>
        </details>
      </div>
    </header>
  );
}
