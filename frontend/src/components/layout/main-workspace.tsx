import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

/**
 * Centered workspace column used by chat and content pages.
 */
export function MainWorkspace({
  children,
  width = "default",
  className,
}: {
  children: ReactNode;
  width?: "default" | "wide";
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mx-auto w-full px-6 md:px-10",
        width === "default" ? "max-w-[760px]" : "max-w-[1072px]",
        className,
      )}
    >
      {children}
    </div>
  );
}
