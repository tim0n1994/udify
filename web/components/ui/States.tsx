import { AlertTriangle, Inbox, RotateCw } from "lucide-react";
import { Button } from "./Button";

export function Skeleton({ className = "h-10" }: { className?: string }) {
  return <div aria-hidden className={`animate-pulse rounded-sm bg-panel-3 ${className}`} />;
}

export function EmptyState({
  title,
  description,
}: {
  title: string;
  description?: string;
}) {
  return (
    <div className="flex min-h-40 flex-col items-center justify-center border border-dashed border-edge p-6 text-center">
      <Inbox className="mb-3 h-5 w-5 text-faint" aria-hidden />
      <p className="text-sm text-muted">{title}</p>
      {description ? <p className="mt-1 max-w-md text-xs text-faint">{description}</p> : null}
    </div>
  );
}

export function ErrorState({
  title = "请求失败",
  message,
  action,
  onRetry,
}: {
  title?: string;
  message: string;
  action?: string;
  onRetry?: () => void;
}) {
  return (
    <div role="alert" className="border border-err/50 bg-err/10 p-4">
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-err" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="font-mono text-xs font-semibold text-err">{title}</p>
          <p className="mt-1 text-sm text-ink">{message}</p>
          {action ? <p className="mt-1 text-xs text-muted">建议：{action}</p> : null}
        </div>
        {onRetry ? (
          <Button type="button" size="sm" onClick={onRetry}>
            <RotateCw className="h-3.5 w-3.5" aria-hidden /> 重试
          </Button>
        ) : null}
      </div>
    </div>
  );
}
