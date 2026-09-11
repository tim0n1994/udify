"use client";

import { useState } from "react";
import { Check } from "lucide-react";
import { clarificationSchema } from "@/lib/api/schema";
import { Button } from "@/components/ui/Button";

interface ClarificationFormProps {
  clarification: unknown;
  pending: boolean;
  onSubmit: (ids: string[]) => void;
}

export function ClarificationForm({ clarification, pending, onSubmit }: ClarificationFormProps): React.JSX.Element {
  const parsed = clarificationSchema.safeParse(clarification);
  const [selected, setSelected] = useState<string[]>([]);
  if (!parsed.success || parsed.data.candidates.length === 0) {
    return <p role="alert" className="border-y border-err py-4 text-sm text-err">目标候选不可用，请刷新任务状态。</p>;
  }
  const candidates = parsed.data.candidates;
  const validSelection = selected.filter((id) => candidates.some((candidate) => candidate.node_id === id));
  return (
    <form className="border-y border-edge py-5" onSubmit={(event) => {
      event.preventDefault();
      if (validSelection.length > 0 && !pending) onSubmit(validSelection);
    }}>
      <fieldset disabled={pending}>
        <legend className="text-base font-semibold text-ink">{parsed.data.question}</legend>
        <p className="mt-2 text-sm text-muted">{parsed.data.reason}</p>
        <div className="my-4 grid gap-2 sm:grid-cols-2">
          {candidates.map((candidate) => (
            <label key={candidate.node_id} className="flex cursor-pointer items-start gap-3 border border-edge px-3 py-3 text-sm text-ink">
              <input type="checkbox" className="mt-1 accent-current" checked={validSelection.includes(candidate.node_id)} onChange={(event) => {
                setSelected((prev) => event.target.checked ? [...prev, candidate.node_id] : prev.filter((id) => id !== candidate.node_id));
              }} />
              <span className="min-w-0 break-words">{candidate.display_name}<span className="mt-1 block break-all font-mono text-xs text-faint">{candidate.node_id}</span></span>
            </label>
          ))}
        </div>
        <Button type="submit" variant="primary" disabled={pending || validSelection.length === 0}>
          <Check className="h-4 w-4" aria-hidden /> {pending ? "提交中…" : "确认目标并继续"}
        </Button>
      </fieldset>
    </form>
  );
}
