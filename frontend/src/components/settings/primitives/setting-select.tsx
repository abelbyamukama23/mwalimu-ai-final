"use client";

import { cn } from "@/lib/utils";

export type SelectOption<T extends string> = {
  value: T;
  label: string;
};

export function SettingSelect<T extends string>({
  options,
  value,
  onChange,
  disabled,
  className,
  "aria-label": ariaLabel,
}: {
  options: SelectOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  className?: string;
  "aria-label"?: string;
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      disabled={disabled}
      aria-label={ariaLabel}
      className={cn(
        "focus-ring h-9 rounded-md border border-border bg-surface px-3 py-1 text-13 text-ink transition-colors hover:border-ink-tertiary disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
    >
      {options.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
