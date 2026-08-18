import type { PublicConfig } from "@/lib/config/schema";

/** Versioned, audited defaults. Frontend flags never change backend policy. */
export const DEFAULT_PUBLIC_CONFIG: PublicConfig = {
  version: 1,
  brand: {
    name: "UDIFY",
    product: "MOD 工作台",
  },
  navigation: [
    { id: "tasks", label: "任务", href: "/", enabled: true },
    { id: "mods", label: "Mods", href: "/", enabled: false },
    { id: "system", label: "系统", href: "/", enabled: false },
  ],
  features: {
    showJobInspector: true,
    showConfigDiagnostics: true,
  },
  polling: {
    activeMs: 1_000,
    idleMs: 5_000,
    healthMs: 10_000,
  },
  density: "comfortable",
  defaultJobTab: "changes",
  apiBase: "http://127.0.0.1:8765",
};
