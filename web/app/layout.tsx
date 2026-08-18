import type { Metadata } from "next";
import { IBM_Plex_Mono, Space_Grotesk } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { AppShell } from "@/components/shell/AppShell";
import { BUILD_CONFIG } from "@/lib/config";

export const metadata: Metadata = {
  title: "Udify · 证据驾驶舱",
  description: "意图驱动的 Mod 生产管线 · 本地审阅与证据核对",
};

const spaceGrotesk = Space_Grotesk({
  subsets: ["latin"],
  variable: "--font-space-grotesk",
  display: "swap",
});
const plexMono = IBM_Plex_Mono({
  weight: ["400", "500", "600"],
  subsets: ["latin"],
  variable: "--font-plex-mono",
  display: "swap",
});

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className={`${spaceGrotesk.variable} ${plexMono.variable}`}>
      <body className="font-sans text-ink antialiased">
        <Providers buildConfig={BUILD_CONFIG}>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
