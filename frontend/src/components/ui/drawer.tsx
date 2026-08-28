"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Cancel01Icon } from "hugeicons-react";
import type { ComponentProps, ReactNode } from "react";


import { cn } from "@/lib/utils";
import { IconButton } from "./icon-button";

/**
 * Drawer — right-anchored side panel built on Radix Dialog
 * (same accessibility guarantees: focus trap, Esc, scrim).
 */
export const Drawer = DialogPrimitive.Root;
export const DrawerClose = DialogPrimitive.Close;

export function DrawerContent({
  className,
  children,
  side = "right",
  ...props
}: ComponentProps<typeof DialogPrimitive.Content> & { side?: "left" | "right" }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 animate-fade-in bg-stone-900/40" />
      <DialogPrimitive.Content
        className={cn(
          "fixed inset-y-0 z-50 h-full w-[min(420px,100vw)]",
          side === "right"
            ? "right-0 animate-slide-in-right"
            : "left-0 animate-[slide-in-left_200ms_ease-out]",
          "overflow-y-auto bg-surface p-7 shadow-overlay focus:outline-none",
          className,
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}

export function DrawerHeader({
  title,
  description,
}: {
  title: string;
  description?: ReactNode;
}) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
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
      <DialogPrimitive.Close asChild>
        <IconButton aria-label="Close panel" size="sm">
          <Cancel01Icon size={16} />
        </IconButton>
      </DialogPrimitive.Close>

    </div>
  );
}
