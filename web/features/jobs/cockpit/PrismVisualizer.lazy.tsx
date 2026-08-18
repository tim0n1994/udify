"use client";

import dynamic from "next/dynamic";
import type { Job } from "@/lib/api";

const LazyField = dynamic(
  () => import("./PrismVisualizer").then((mod) => mod.PrismField),
  { ssr: false, loading: () => <PrismFallback /> },
);

export function PrismFallback() {
  return (
    <div
      aria-hidden
      className="flex h-full min-h-[220px] items-center justify-center border border-dashed border-edge bg-bg/40"
    >
      <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-faint">
        Evidence field · 初始化…
      </span>
    </div>
  );
}

/** 懒加载 WebGL 证据场：three.js chunk 不进首屏 bundle；WebGL 不可用时 die 之前已有 fallback。 */
export function PrismVisualizerLazy({
  jobs,
  selected,
}: {
  jobs: Job[];
  selected: { events: number; valid: boolean } | null;
}) {
  return <LazyField jobs={jobs} selected={selected} />;
}
