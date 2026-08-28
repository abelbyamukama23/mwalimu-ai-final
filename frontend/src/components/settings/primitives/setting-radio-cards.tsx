"use client";

import { Check, type Icon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export type RadioCardOption<T extends string> = {
  value: T;
  label: string;
  description?: string;
  icon?: Icon;
};


export function SettingRadioCards<T extends string>({
  options,
  value,
  onChange,
  disabled,
  columns = 3,
}: {
  options: RadioCardOption<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  columns?: 2 | 3 | 4;
}) {
  const gridCols =
    columns === 2
      ? "grid-cols-1 sm:grid-cols-2"
      : columns === 4
        ? "grid-cols-1 sm:grid-cols-2 lg:grid-cols-4"
        : "grid-cols-1 sm:grid-cols-3";

  return (
    <div className={cn("grid gap-3", gridCols)} role="radiogroup">
      {options.map((opt) => {
        const Icon = opt.icon;
        const selected = opt.value === value;

        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChange(opt.value)}
            className={cn(
              "focus-ring group relative flex flex-col justify-between rounded-lg border p-4 text-left transition-all",
              selected
                ? "border-accent bg-accent/5 ring-1 ring-accent/30"
                : "border-border bg-surface hover:border-ink-tertiary/50 hover:bg-surface-hover",
              disabled && "cursor-not-allowed opacity-60",
            )}
          >
            <div>
              <div className="flex items-center justify-between gap-2">
                {Icon && (
                  <Icon
                    size={18}
                    aria-hidden
                    className={cn(
                      "transition-colors",
                      selected ? "text-accent" : "text-ink-tertiary",
                    )}
                  />
                )}
                {selected && (
                  <div className="flex h-4 w-4 items-center justify-center rounded-full bg-accent text-accent-ink">
                    <Check size={10} strokeWidth={3} />
                  </div>
                )}
              </div>
              <p
                className={cn(
                  "mt-2 text-13 font-semibold",
                  selected ? "text-accent" : "text-ink",
                )}
              >
                {opt.label}
              </p>
              {opt.description && (
                <p className="mt-1 text-11 leading-normal text-ink-tertiary">
                  {opt.description}
                </p>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
