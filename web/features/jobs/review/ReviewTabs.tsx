"use client";

import * as Tabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";
import type { JobTab } from "@/lib/config";

const TAB_LABELS: readonly [JobTab, string][] = [
  ["changes", "修改计划"],
  ["risk", "风险审阅"],
  ["report", "验证报告"],
];

export function ReviewTabs({
  value,
  onValueChange,
  changes,
  risk,
  report,
}: {
  value: JobTab;
  onValueChange: (value: JobTab) => void;
  changes: ReactNode;
  risk: ReactNode;
  report: ReactNode;
}) {
  const content = { changes, risk, report };
  return (
    <Tabs.Root value={value} onValueChange={(next) => onValueChange(next as JobTab)}>
      <Tabs.List aria-label="任务审阅视图" className="flex gap-6 border-b border-edge px-1">
        {TAB_LABELS.map(([key, label]) => (
          <Tabs.Trigger
            key={key}
            value={key}
            className="border-b-2 border-transparent px-2 py-2.5 font-mono text-xs text-muted transition hover:text-ink data-[state=active]:border-accent data-[state=active]:text-accent"
          >
            {label}
          </Tabs.Trigger>
        ))}
      </Tabs.List>
      {TAB_LABELS.map(([key]) => (
        <Tabs.Content key={key} value={key} className="pt-4 focus:outline-none">
          {content[key]}
        </Tabs.Content>
      ))}
    </Tabs.Root>
  );
}
