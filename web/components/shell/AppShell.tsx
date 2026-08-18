"use client";

import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { SidebarNav } from "./SidebarNav";
import { TopStatus } from "./TopStatus";
import { useConfig } from "@/lib/config";

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { config } = useConfig();
  return (
    <div
      data-density={config.density}
      className="relative min-h-screen bg-bg"
    >
      <div
        aria-hidden
        className="blueprint-grid pointer-events-none fixed inset-0 opacity-60"
      />
      <TopStatus />
      <div className="relative grid min-h-[calc(100vh-48px)] lg:grid-cols-[196px_minmax(0,1fr)]">
        <SidebarNav pathname={pathname} />
        <main className="min-w-0 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </div>
  );
}
