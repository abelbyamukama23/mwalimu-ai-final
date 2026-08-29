import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all duration-150 focus-ring active:scale-[0.98] disabled:cursor-not-allowed disabled:active:scale-100",
  {
    variants: {
      variant: {
        primary:
          "bg-[#0d7a68] !text-white hover:bg-[#0a6657] active:bg-[#075246] shadow-xs disabled:!bg-[#f4f4f5] disabled:!text-[#a1a1aa] disabled:!border disabled:!border-[#e4e4e7] disabled:shadow-none dark:disabled:!bg-[#27272a] dark:disabled:!text-[#71717a] dark:disabled:!border-[#3f3f46]",
        secondary:
          "border border-border bg-surface text-ink hover:bg-subtle shadow-xs disabled:!bg-[#f4f4f5] disabled:!text-[#a1a1aa] disabled:!border-[#e4e4e7]",
        ghost:
          "text-[#0d7a68] hover:bg-[#e6efec] dark:text-[#4fa89b] dark:hover:bg-[#24332f] disabled:!text-[#a1a1aa] disabled:hover:bg-transparent",
        accent:
          "bg-[#0d7a68] !text-white hover:bg-[#0a6657] shadow-xs disabled:!bg-[#f4f4f5] disabled:!text-[#a1a1aa]",
        terracotta:
          "bg-terracotta !text-white hover:bg-terracotta/90 shadow-xs disabled:!bg-[#f4f4f5] disabled:!text-[#a1a1aa]",
      },
      size: {
        sm: "h-8 px-3 text-13",
        md: "h-10 px-4 text-14",
        lg: "h-12 px-5 text-15",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants> & {
    loading?: boolean;
  };

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    {
      className,
      variant = "primary",
      size,
      type = "button",
      loading = false,
      disabled,
      style,
      children,
      ...props
    },
    ref,
  ) => {
    const isWhiteTextVariant =
      variant === "primary" || variant === "accent" || variant === "terracotta";
    const isDisabled = disabled || loading;

    return (
      <button
        ref={ref}
        type={type}
        disabled={isDisabled}
        aria-busy={loading ? "true" : undefined}
        style={{
          ...(isWhiteTextVariant && !isDisabled ? { color: "#ffffff" } : {}),
          ...style,
        }}
        className={cn(buttonVariants({ variant, size }), className)}
        {...props}
      >
        {loading && (
          <svg
            className="h-4 w-4 animate-spin shrink-0 !text-white"
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="3.5"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        )}
        <span
          className={cn(
            isWhiteTextVariant && !isDisabled && "!text-white text-white",
          )}
          style={isWhiteTextVariant && !isDisabled ? { color: "#ffffff" } : undefined}
        >
          {children}
        </span>
      </button>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };


