import type { ComponentType, ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Standardized empty state: 40px icon well, one short explanation, one clear action.
 */
export function EmptyState({
  icon: Icon,
  title,
  body,
  action,
  className,
}: {
  icon: ComponentType<{ size?: number; weight?: "regular" | "bold" | "duotone" | "fill" | "light" | "thin"; className?: string; "aria-hidden"?: boolean }>;
  title: string;
  body: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto flex max-w-sm flex-col items-center px-6 py-16 text-center",
        className,
      )}
    >
      <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl bg-subtle">
        <Icon size={22} weight="duotone" className="text-ink-tertiary" aria-hidden />
      </div>
      <p className="mb-1.5 text-15 font-semibold text-ink">{title}</p>
      <p className="mb-5 text-13 leading-relaxed text-ink-secondary">{body}</p>
      {action}
    </div>
  );
}
