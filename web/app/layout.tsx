import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";
import { HealthDot } from "@/components/HealthDot";
import Link from "next/link";

export const metadata: Metadata = {
  title: "Udify 工作台",
  description: "意图驱动的 Mod 生产管线 · 本地审阅工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body className="font-sans text-ink antialiased">
        <Providers>
          <header className="sticky top-0 z-10 border-b border-edge bg-bg/80 backdrop-blur">
            <div className="mx-auto flex h-14 max-w-6xl items-center gap-4 px-6">
              <Link href="/" className="group flex items-baseline gap-2">
                <span className="font-mono text-lg font-bold tracking-[0.25em] text-ink">
                  UDIFY
                </span>
                <span className="font-mono text-xs text-accent">/</span>
                <span className="text-xs tracking-widest text-muted group-hover:text-ink">
                  MOD 工作台
                </span>
              </Link>
              <div className="ml-auto flex items-center gap-3">
                <span className="font-mono text-[10px] uppercase tracking-widest text-faint">
                  local · single-user
                </span>
                <HealthDot />
              </div>
            </div>
          </header>
          <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
        </Providers>
      </body>
    </html>
  );
}
