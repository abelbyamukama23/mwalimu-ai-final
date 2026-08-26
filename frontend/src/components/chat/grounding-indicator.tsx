"use client";

import { Sparkles } from "lucide-react";
import type { Citation } from "@/lib/chat/chat-api";
import { cn } from "@/lib/utils";

interface GroundingIndicatorProps {
  citations?: Citation[];
  className?: string;
}

/**
 * Subtle indicator showing that the assistant response was grounded
 * in retrieved authoritative knowledge.
 *
 * Invariant: Renders ONLY when actual runtime citation evidence exists.
 * Never renders merely because a scope was selected or configured.
 */
export function GroundingIndicator({ citations, className }: GroundingIndicatorProps) {
  if (!citations || citations.length === 0) {
    return null;
  }

  const count = citations.length;
  const label =
    count === 1
      ? "Grounded in your study notes"
      : `Grounded in ${count} study resources`;

  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full bg-accent/8 px-2.5 py-0.5 text-11 font-medium text-accent mb-2",
        className,
      )}
    >
      <Sparkles className="h-3 w-3 text-accent shrink-0" aria-hidden="true" />
      <span>{label}</span>
    </div>
  );
}
