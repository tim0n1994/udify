"use client";

import * as AlertDialog from "@radix-ui/react-alert-dialog";
import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

export function ConfirmDialog({
  trigger,
  title,
  description,
  details,
  confirmLabel,
  danger = false,
  pending = false,
  confirmDisabled = false,
  onConfirm,
}: {
  trigger: ReactNode;
  title: string;
  description: string;
  details?: ReactNode;
  confirmLabel: string;
  danger?: boolean;
  pending?: boolean;
  confirmDisabled?: boolean;
  onConfirm: () => void;
}) {
  return (
    <AlertDialog.Root>
      <AlertDialog.Trigger asChild>{trigger}</AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Overlay className="fixed inset-0 z-40 bg-black/70" />
        <AlertDialog.Content className="fixed left-1/2 top-1/2 z-50 w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 border border-edge-strong bg-panel p-5 shadow-2xl">
          <div className="flex items-start gap-3">
            <AlertTriangle className={`mt-0.5 h-5 w-5 ${danger ? "text-err" : "text-accent"}`} aria-hidden />
            <div>
              <AlertDialog.Title className="text-base font-semibold text-ink">
                {title}
              </AlertDialog.Title>
              <AlertDialog.Description className="mt-2 text-sm leading-6 text-muted">
                {description}
              </AlertDialog.Description>
            </div>
          </div>
          {details ? <div className="mt-4 border border-edge bg-bg/60 p-3">{details}</div> : null}
          <div className="mt-5 flex justify-end gap-3">
            <AlertDialog.Cancel asChild>
              <Button type="button" disabled={pending}>取消</Button>
            </AlertDialog.Cancel>
            <AlertDialog.Action asChild>
              <Button
                type="button"
                variant={danger ? "danger" : "primary"}
                disabled={pending || confirmDisabled}
                onClick={onConfirm}
              >
                {pending ? "提交中…" : confirmLabel}
              </Button>
            </AlertDialog.Action>
          </div>
        </AlertDialog.Content>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
