"use client";

import { useQuery } from "@tanstack/react-query";
import { api, queryKeys } from "@/lib/api";
import { useConfig } from "@/lib/config";

export function HealthDot() {
  const { config } = useConfig();
  const { data, isError } = useQuery({
    queryKey: queryKeys.health,
    queryFn: api.healthz,
    refetchInterval: config.polling.healthMs,
  });
  const up = Boolean(data) && !isError;
  return (
    <span
      className="flex items-center gap-1.5 font-mono text-[10px] uppercase tracking-widest"
      title={up ? `后端在线 v${data?.version}` : "后端离线：请运行 udify serve"}
    >
      <span
        className={`h-2 w-2 rounded-full ${up ? "bg-ok" : "bg-err"}`}
        aria-hidden
      />
      <span className={up ? "text-ink" : "text-err"}>{up ? "API 在线" : "API 离线"}</span>
    </span>
  );
}
