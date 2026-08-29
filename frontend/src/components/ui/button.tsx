import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-all duration-150 focus-ring active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:active:scale-100",
  {
    variants: {
      variant: {
        primary: "bg-cta text-cta-fg hover:bg-cta-hover shadow-xs",
        secondary:
          "border border-border bg-surface text-ink hover:bg-subtle shadow-xs",
        ghost: "text-ink-secondary hover:text-ink hover:bg-subtle",
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
