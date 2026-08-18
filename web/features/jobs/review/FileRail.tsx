"use client";

import { FileCode2, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { Input } from "@/components/ui/Input";
import type { FileDiff, PatchOp } from "@/lib/api";
import { cn } from "@/lib/cn";

export function FileRail({
  diffs,
  operations,
  selectedPath,
  onSelect,
}: {
  diffs: FileDiff[];
  operations: PatchOp[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
}) {
  const [search, setSearch] = useState("");
  const visible = useMemo(
    () => diffs.filter((diff) => diff.path.toLowerCase().includes(search.trim().toLowerCase())),
    [diffs, search],
  );
  return (
    <section className="border-b border-edge bg-panel xl:border-b-0 xl:border-r" aria-label="文件变更">
      <div className="border-b border-edge p-3">
        <h2 className="mb-2 text-sm font-semibold text-ink">文件变更</h2>
        <label className="relative block">
          <span className="sr-only">搜索文件路径</span>
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-faint" aria-hidden />
          <Input className="h-8 pl-8 text-xs" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索文件路径" />
        </label>
        <p className="mt-2 font-mono text-[10px] text-faint">{diffs.length} 个文件 · {operations.length} 个操作</p>
      </div>
      <div className="data-scroll max-h-52 overflow-y-auto xl:max-h-[400px]">
        {visible.map((diff) => {
          const count = operations.filter((operation) => operation.source_span?.file_path === diff.path).length;
          const selected = selectedPath === diff.path;
          return (
            <button
              type="button"
              key={diff.path}
              onClick={() => onSelect(diff.path)}
              className={cn(
                "flex w-full items-center gap-2 border-b border-edge px-3 py-3 text-left transition",
                selected ? "bg-accent/8 text-accent shadow-[inset_2px_0_0_var(--color-accent)]" : "text-muted hover:bg-panel-2 hover:text-ink",
              )}
            >
              <FileCode2 className="h-3.5 w-3.5 shrink-0" aria-hidden />
              <span className="min-w-0 flex-1 truncate font-mono text-[11px]">{diff.path}</span>
              <span className="font-mono text-[10px] text-faint">{count || "—"}</span>
            </button>
          );
        })}
        {visible.length === 0 ? <p className="p-4 text-xs text-faint">没有匹配文件。</p> : null}
      </div>
    </section>
  );
}
