"use client";

import { Folder, Plus } from "lucide-react";
import { useState } from "react";
import { z } from "zod";
import { Button } from "@/components/ui/Button";
import { Input, Textarea } from "@/components/ui/Input";
import { ErrorState } from "@/components/ui/States";
import type { ApiError } from "@/lib/api";

export const createJobSchema = z.object({
  gameRoot: z.string().trim().min(1, "请输入游戏目录").max(1024),
  intent: z.string().trim().min(3, "请至少用 3 个字描述改造意图").max(500),
});

export function CreateJobForm({
  pending,
  apiError,
  onSubmit,
}: {
  pending: boolean;
  apiError: ApiError | null;
  onSubmit: (input: { gameRoot: string; intent: string }) => Promise<void>;
}) {
  const [gameRoot, setGameRoot] = useState("");
  const [intent, setIntent] = useState("");
  const [errors, setErrors] = useState<{ gameRoot?: string; intent?: string }>({});

  return (
    <section className="surface p-4 sm:p-5" aria-labelledby="create-job-title">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 id="create-job-title" className="text-sm font-semibold text-ink">
            创建新任务
          </h2>
          <p className="mt-1 text-xs text-muted">
            只生成带证据的 VFS 修改计划；未批准前不应用，始终不改写原目录。
          </p>
        </div>
      </div>
      <form
        className="grid gap-4 lg:grid-cols-[minmax(260px,0.8fr)_minmax(360px,1.25fr)_150px]"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          const parsed = createJobSchema.safeParse({ gameRoot, intent });
          if (!parsed.success) {
            const next: typeof errors = {};
            for (const issue of parsed.error.issues) {
              if (issue.path[0] === "gameRoot") next.gameRoot = issue.message;
              if (issue.path[0] === "intent") next.intent = issue.message;
            }
            setErrors(next);
            return;
          }
          setErrors({});
          void onSubmit(parsed.data);
        }}
      >
        <label className="block" htmlFor="game-root">
          <span className="control-label mb-1.5 block">游戏目录</span>
          <span className="relative block">
            <Folder className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-faint" aria-hidden />
            <Input
              id="game-root"
              className="pl-9 font-mono"
              value={gameRoot}
              onChange={(event) => setGameRoot(event.target.value)}
              placeholder="/path/to/miu2d-game"
              aria-invalid={Boolean(errors.gameRoot)}
              aria-describedby={errors.gameRoot ? "game-root-error" : undefined}
            />
          </span>
          {errors.gameRoot ? (
            <span id="game-root-error" className="mt-1 block text-xs text-err">
              {errors.gameRoot}
            </span>
          ) : null}
        </label>
        <label className="block" htmlFor="job-intent">
          <span className="control-label mb-1.5 flex justify-between">
            <span>改造意图</span><span>{intent.length}/500</span>
          </span>
          <Textarea
            id="job-intent"
            rows={2}
            value={intent}
            onChange={(event) => setIntent(event.target.value)}
            placeholder="让第一个 Boss 更难，但不要单纯翻倍血量"
            aria-invalid={Boolean(errors.intent)}
            aria-describedby={errors.intent ? "intent-error" : undefined}
          />
          {errors.intent ? (
            <span id="intent-error" className="mt-1 block text-xs text-err">
              {errors.intent}
            </span>
          ) : null}
        </label>
        <div className="flex flex-col justify-end">
          <Button type="submit" variant="primary" size="lg" disabled={pending}>
            <Plus className="h-4 w-4" aria-hidden /> {pending ? "创建中…" : "创建任务"}
          </Button>
        </div>
      </form>
      {apiError ? (
        <div className="mt-4">
          <ErrorState
            title={apiError.record.code}
            message={apiError.record.message}
            action={apiError.record.suggested_action}
          />
        </div>
      ) : null}
    </section>
  );
}
