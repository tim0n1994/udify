"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export function HealthDot() {
  const { data, isError } = useQuery({
    queryKey: ["healthz"],
    queryFn: api.healthz,
    refetchInterval: 5000,
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
      <span className={up ? "text-ok" : "text-err"}>{up ? "API" : "OFFLINE"}</span>
    </span>
  );
}
