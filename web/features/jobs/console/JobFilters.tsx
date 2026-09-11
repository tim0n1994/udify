"use client";

import { Search, X } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import type { JobFilter } from "./filters";

const OPTIONS: readonly [JobFilter, string][] = [
  ["all", "全部状态"],
  ["awaiting_clarification", "待确认目标"],
  ["awaiting_review", "待审阅"],
  ["active", "进行中"],
  ["completed", "已完成"],
  ["failed", "失败"],
];

export function JobFilters({
  search,
  filter,
  onSearch,
  onFilter,
  onClear,
}: {
  search: string;
  filter: JobFilter;
  onSearch: (value: string) => void;
  onFilter: (value: JobFilter) => void;
  onClear: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-3 border-b border-edge bg-panel-2/40 px-4 py-3 sm:px-5">
      <label className="relative min-w-[220px] flex-1 sm:max-w-sm">
        <span className="sr-only">搜索意图或目录</span>
        <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-faint" aria-hidden />
        <Input
          className="pl-9"
          value={search}
          onChange={(event) => onSearch(event.target.value)}
          placeholder="搜索意图、目录或 Job ID"
        />
      </label>
      <label>
        <span className="sr-only">任务状态</span>
        <select
          value={filter}
          onChange={(event) => onFilter(event.target.value as JobFilter)}
          className="min-h-9 rounded-sm border border-edge-strong bg-bg px-3 font-mono text-xs text-ink"
        >
          {OPTIONS.map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </select>
      </label>
      {(search || filter !== "all") ? (
        <Button type="button" size="sm" variant="ghost" onClick={onClear}>
          <X className="h-3.5 w-3.5" aria-hidden /> 清空筛选
        </Button>
      ) : null}
    </div>
  );
}
