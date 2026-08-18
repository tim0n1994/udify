"use client";

import { Box, ClipboardList, Settings } from "lucide-react";
import Link from "next/link";
import { useConfig } from "@/lib/config";
import { cn } from "@/lib/cn";

const ICONS = { tasks: ClipboardList, mods: Box, system: Settings } as const;
const STAMPS: Record<string, { index: string; code: string }> = {
  tasks: { index: "01", code: "OPS" },
  mods: { index: "02", code: "PKG" },
  system: { index: "03", code: "SYS" },
};

export function SidebarNav({ pathname }: { pathname: string }) {
  const { config } = useConfig();
  return (
    <aside className="border-b border-edge bg-panel/60 md:border-b-0 md:border-r">
      <nav
        aria-label="主导航"
        className="flex gap-1 overflow-x-auto p-2 md:block md:space-y-1 md:p-3"
      >
        {config.navigation.map((item) => {
          const Icon = ICONS[item.id];
          const stamp = STAMPS[item.id] ?? { index: "--", code: "---" };
          const active = item.id === "tasks" && (pathname === "/" || pathname.startsWith("/jobs/"));
          if (!item.enabled) {
            return (
              <span
                key={item.id}
                aria-disabled="true"
                title="尚未开放"
                className="flex min-w-max items-center gap-3 border border-transparent px-3 py-3 text-[13px] text-faint md:w-full"
              >
                <Icon className="h-4 w-4" aria-hidden /> {item.label}
                <span className="ml-auto hidden font-mono text-[9px] md:inline">SOON</span>
              </span>
            );
          }
          return (
            <Link
              key={item.id}
              href={item.href}
              aria-current={active ? "page" : undefined}
              className={cn(
                "group relative flex min-w-max items-center gap-3 border px-3 py-2.5 text-[13px] transition md:w-full",
                active
                  ? "border-accent/40 bg-accent/5 text-accent"
                  : "border-transparent text-muted hover:border-edge hover:bg-panel-2 hover:text-ink",
              )}
            >
              <span className="font-mono text-[9px] tracking-widest text-faint">
                {stamp.index}
              </span>
              <Icon className="h-4 w-4" aria-hidden />
              <span className="flex-1">{item.label}</span>
              <span className="hidden font-mono text-[9px] tracking-[0.18em] text-faint group-hover:text-accent-dim lg:inline">
                {stamp.code}
              </span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
