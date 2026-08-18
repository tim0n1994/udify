"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ConfigProvider, type ConfigResolution } from "@/lib/config";
import { SoundProvider } from "@/lib/sound";

export function Providers({
  children,
  buildConfig,
}: {
  children: React.ReactNode;
  buildConfig: ConfigResolution;
}) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: 1,
            refetchOnWindowFocus: true,
            refetchIntervalInBackground: false,
          },
        },
      }),
  );
  return (
    <ConfigProvider build={buildConfig}>
      <QueryClientProvider client={client}>
        <SoundProvider>{children}</SoundProvider>
      </QueryClientProvider>
    </ConfigProvider>
  );
}
