"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Cancel01Icon } from "hugeicons-react";
import type { ComponentProps, ReactNode } from "react";

import { cn } from "@/lib/utils";
import { IconButton } from "./icon-button";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

export function DialogContent({
  className,
  children,
  ...props
}: ComponentProps<typeof DialogPrimitive.Content>) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 animate-fade-in bg-stone-900/40" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 max-h-[88vh] w-[min(480px,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2",
          "animate-scale-in overflow-y-auto rounded-lg bg-surface p-7 shadow-overlay",
          "focus:outline-none",
          className,
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DialogHeader({
  title,
  description,
  onClose,
}: {
  title: string;
  description?: ReactNode;
  onClose?: () => void;
}) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div>
        <DialogPrimitive.Title className="text-17 font-semibold text-ink">
          {title}
        </DialogPrimitive.Title>
        {description ? (
          <DialogPrimitive.Description className="mt-1 text-13 text-ink-secondary">
            {description}
          </DialogPrimitive.Description>
        ) : null}
      </div>
      {onClose ? (
        <DialogPrimitive.Close asChild>
          <IconButton aria-label="Close dialog" size="sm" onClick={onClose}>
            <Cancel01Icon size={16} />
          </IconButton>
        </DialogPrimitive.Close>
      ) : (
        <DialogPrimitive.Close asChild>
          <IconButton aria-label="Close dialog" size="sm">
            <Cancel01Icon size={16} />
          </IconButton>
        </DialogPrimitive.Close>
      )}
    </div>
  );
}

