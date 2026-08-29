import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const iconButtonVariants = cva(
  "inline-flex shrink-0 items-center justify-center rounded-full transition-all duration-150 focus-ring active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100",
  {
    variants: {
      variant: {
        primary:
          "bg-[#18181b] text-white hover:bg-[#27272a] active:bg-[#09090b] dark:bg-white dark:text-[#18181b] dark:hover:bg-zinc-100 shadow-sm",
        ghost: "text-ink-tertiary hover:bg-subtle hover:text-ink-secondary",
        accent: "bg-accent text-white hover:bg-accent-hover shadow-xs",
      },
      size: {
        sm: "h-7 w-7",
        md: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "ghost", size: "md" },
  },
);



export type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof iconButtonVariants> & {
    /** Required for accessibility — icon-only buttons must be labelled. */
    "aria-label": string;
  };

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(iconButtonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
IconButton.displayName = "IconButton";
