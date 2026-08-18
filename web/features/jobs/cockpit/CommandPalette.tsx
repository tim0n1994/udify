"use client";

import { Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Job, JobStatus } from "@/lib/api";
import { STATUS_META } from "@/lib/ui";

interface CommandItem {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

const FILTERABLE: readonly JobStatus[] = [
  "awaiting_review",
  "completed",
  "failed",
  "validating",
  "rolled_back",
];

/** ⌘K 命令面板：任务检索 + 状态筛选 + 动作动词。90 行自研，后端落地 /search 后替换数据源。 */
export function CommandPalette({
  open,
  jobs,
  onClose,
}: {
  open: boolean;
  jobs: Job[] | undefined;
  onClose: () => void;
}) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    }
  }, [open]);

  const items = useMemo<CommandItem[]>(() => {
    if (!open) return [];
    const needle = query.trim().toLowerCase();
    const verbs: CommandItem[] = [
      { id: "goto-console", label: "回到任务控制台", hint: "导航", run: () => router.push("/") },
      ...FILTERABLE.map((status) => ({
        id: `filter-${status}`,
        label: `筛选：${STATUS_META[status].label}`,
        hint: "控制台",
        run: () => router.push(`/?status=${status}`),
      })),
    ];
    const jobItems: CommandItem[] = (jobs ?? [])
      .filter(
        (job) =>
          needle.length === 0 ||
          job.intent.toLowerCase().includes(needle) ||
          job.job_id.toLowerCase().includes(needle),
      )
      .slice(0, 8)
      .map((job) => ({
        id: job.job_id,
        label: job.intent,
        hint: `${STATUS_META[job.status].label} · ${job.job_id}`,
        run: () =>
          router.push(
            job.status === "awaiting_review" ? `/jobs/${job.job_id}?tab=risk` : `/jobs/${job.job_id}`,
          ),
      }));
    const verbMatches = verbs.filter((verb) => verb.label.toLowerCase().includes(needle));
    return [...jobItems, ...verbMatches];
  }, [open, jobs, query, router]);

  useEffect(() => {
    setIndex(0);
  }, [query]);

  if (!open) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="命令面板"
      className="fixed inset-0 z-50 flex items-start justify-center bg-bg/70 px-4 pt-[16vh] backdrop-blur-sm"
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
        if (event.key === "ArrowDown") {
          event.preventDefault();
          setIndex((prev) => Math.min(prev + 1, items.length - 1));
        }
        if (event.key === "ArrowUp") {
          event.preventDefault();
          setIndex((prev) => Math.max(prev - 1, 0));
        }
        if (event.key === "Enter" && items[index]) {
          items[index].run();
          onClose();
        }
      }}
    >
      <div className="dossier w-full max-w-xl">
        <div className="flex items-center gap-2 border-b border-edge px-4 py-3">
          <Search className="h-4 w-4 text-faint" aria-hidden />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="检索任务意图 / Job ID / 动作…"
            aria-label="检索命令"
            className="w-full bg-transparent font-mono text-sm text-ink placeholder:text-faint focus:outline-none"
          />
          <kbd className="border border-edge px-1.5 py-0.5 font-mono text-[9px] text-faint">ESC</kbd>
        </div>
        <ul role="listbox" aria-label="命令结果" className="max-h-80 overflow-y-auto p-1.5 data-scroll">
          {items.length === 0 ? (
            <li className="px-3 py-6 text-center font-mono text-xs text-faint">无匹配结果</li>
          ) : (
            items.map((item, itemIndex) => (
              <li key={item.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={itemIndex === index}
                  onClick={() => {
                    item.run();
                    onClose();
                  }}
                  onMouseEnter={() => setIndex(itemIndex)}
                  className={`flex w-full items-baseline gap-3 px-3 py-2.5 text-left ${
                    itemIndex === index ? "bg-panel-3 text-ink" : "text-muted"
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate text-[13px]">{item.label}</span>
                  {item.hint ? (
                    <span className="shrink-0 font-mono text-[10px] text-faint">{item.hint}</span>
                  ) : null}
                </button>
              </li>
            ))
          )}
        </ul>
      </div>
    </div>
  );
}
