"use client";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function SettingRow({
  label,
  description,
  badge,
  children,
  className,
}: {
  label: string;
  description?: string;
  badge?: { label: string; tone?: "neutral" | "info" | "success" | "warning" };
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col justify-between gap-3 py-4 sm:flex-row sm:items-center",
        className,
      )}
    >
      <div className="max-w-md space-y-1">
        <div className="flex items-center gap-2">
          <span className="text-14 font-medium text-ink">{label}</span>
          {badge && <Badge tone={badge.tone ?? "neutral"}>{badge.label}</Badge>}
        </div>
        {description && (
          <p className="text-12 text-ink-secondary leading-relaxed">
            {description}
          </p>
        )}
      </div>
      {children && <div className="shrink-0">{children}</div>}
    </div>
  );
}
