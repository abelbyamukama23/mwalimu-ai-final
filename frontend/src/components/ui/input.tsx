import { forwardRef, type InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface InputProps
  extends InputHTMLAttributes<HTMLInputElement> {
  error?: boolean;
}


export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, error, ...props }, ref) => (
    <input
      ref={ref}
      aria-invalid={error ? "true" : undefined}
      className={cn(
        "h-11 w-full rounded-md border border-[#e4e4e7] bg-surface px-3.5 text-14 text-ink transition-colors duration-150",
        "placeholder:text-ink-tertiary",
        "hover:border-[#a1a1aa]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0d7a68]/25 focus-visible:border-[#0d7a68]",
        error && "border-red-500 hover:border-red-600 focus-visible:ring-red-500/25 focus-visible:border-red-500",
        "disabled:cursor-not-allowed disabled:bg-[#f4f4f5] disabled:text-[#a1a1aa] disabled:opacity-75",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";

