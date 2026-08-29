import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all duration-150 focus-ring active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
  {
    variants: {
      variant: {
        primary:
          "bg-blue-600 text-white hover:bg-blue-700 active:bg-blue-800 dark:bg-blue-600 dark:text-white dark:hover:bg-blue-500 shadow-sm",
        secondary:
          "border border-border bg-surface text-ink hover:bg-subtle shadow-xs",
        ghost: "text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950/30",
        accent: "bg-accent text-white hover:bg-accent-hover shadow-xs",
        terracotta: "bg-terracotta text-white hover:bg-terracotta/90 shadow-xs",
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
  VariantProps<typeof buttonVariants>;

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, type = "button", ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      className={cn(buttonVariants({ variant, size }), className)}
      {...props}
    />
  ),
);
Button.displayName = "Button";

export { buttonVariants };
