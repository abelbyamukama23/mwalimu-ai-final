"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/button";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Mwalimu App Client Error:", error);
  }, [error]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-canvas p-6 text-center">
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-100 text-red-600 dark:bg-red-950/50 dark:text-red-400">
        <span className="text-20 font-bold" aria-hidden>!</span>
      </div>
      <div className="max-w-md space-y-1.5">
        <h2 className="text-18 font-semibold text-ink">Something went wrong</h2>
        <p className="text-13 text-ink-secondary">
          {error?.message || "An unexpected error occurred while loading this page."}
        </p>
      </div>
      <div className="flex items-center gap-2.5 pt-2">
        <Button onClick={() => reset()} variant="primary">
          Try again
        </Button>
        <Button onClick={() => window.location.reload()} variant="secondary">
          Reload page
        </Button>
      </div>
    </div>
  );
}
