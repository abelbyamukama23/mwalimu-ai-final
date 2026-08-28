"use client";

import { useState } from "react";
import {
  BookOpen,
  Books,
  CaretDown,
  CaretUp,
  FileText,
} from "@phosphor-icons/react";
import type { Citation } from "@/lib/chat/chat-api";
import { cn } from "@/lib/utils";

interface CitationChipsProps {
  citations?: Citation[];
  className?: string;
}

/**
 * Normalizes citation display title from available backend metadata.
 */
function getDisplayTitle(citation: Citation): string {
  if (citation.resource_name && citation.resource_name.trim()) {
    return citation.resource_name.trim();
  }
  if (citation.title && citation.title.trim()) {
    return citation.title.trim();
  }
  return "Document";
}

/**
 * Normalizes citation section / location label if present.
 */
function getLocationLabel(citation: Citation): string | null {
  if (citation.section && citation.section.trim()) {
    return citation.section.trim();
  }
  if (citation.page_start != null) {
    if (citation.page_end != null && citation.page_end !== citation.page_start) {
      return `pp. ${citation.page_start}–${citation.page_end}`;
    }
    return `p. ${citation.page_start}`;
  }
  return null;
}

/**
 * Provenance Chip with expandable safe metadata details.
 * Learner-facing UI: Shows Library, Document, Section/Page.
 * Strictly omits technical scores, raw hashes, or tokens.
 */
function CitationItem({ citation }: { citation: Citation }) {
  const [open, setOpen] = useState(false);

  const title = getDisplayTitle(citation);
  const location = getLocationLabel(citation);
  const libraryName = citation.library_name?.trim() || "Personal Library";

  return (
    <div className="inline-flex flex-col">
      <button
        type="button"
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-12 font-medium transition-colors",
          "border-border bg-subtle text-ink-secondary hover:border-accent hover:text-ink focus-ring",
          open && "border-accent/40 bg-accent/5 text-ink",
        )}
      >
        <BookOpen size={14} weight="duotone" className="text-accent shrink-0" aria-hidden="true" />
        <span className="truncate max-w-[200px] sm:max-w-[280px]">
          {title}
        </span>
        {location && (
          <span className="text-ink-muted text-11 shrink-0 font-normal">
            · {location}
          </span>
        )}
        {open ? (
          <CaretUp size={12} weight="bold" className="text-ink-muted shrink-0" aria-hidden="true" />
        ) : (
          <CaretDown size={12} weight="bold" className="text-ink-muted shrink-0" aria-hidden="true" />
        )}
      </button>

      {open && (
        <div
          role="region"
          aria-label={`Source metadata for ${title}`}
          className="mt-1.5 w-full max-w-[340px] rounded-lg border border-border bg-surface p-3 text-12 text-ink shadow-sm"
        >
          <div className="flex items-start gap-2 mb-2">
            <FileText size={16} weight="duotone" className="text-accent shrink-0 mt-0.5" aria-hidden="true" />
            <div className="min-w-0 flex-1">
              <div className="font-semibold text-13 truncate">{title}</div>
              {location && (
                <div className="text-11 text-ink-muted mt-0.5">{location}</div>
              )}
            </div>
          </div>

          <div className="flex items-center gap-1.5 pt-2 border-t border-border/60 text-11 text-ink-secondary">
            <Books size={14} weight="duotone" className="text-ink-muted shrink-0" aria-hidden="true" />
            <span className="truncate">{libraryName}</span>
          </div>
        </div>
      )}
    </div>
  );
}


/**
 * Compact provenance list rendered beneath assistant responses.
 * Renders NOTHING if citations are empty or absent (honest absence).
 */
export function CitationChips({ citations, className }: CitationChipsProps) {
  if (!citations || citations.length === 0) {
    return null;
  }

  return (
    <div
      className={cn("mt-3 pt-3 border-t border-border/40", className)}
      aria-label="Authoritative source provenance"
    >
      <div className="mb-1.5 flex items-center gap-1.5 text-11 font-medium text-ink-muted uppercase tracking-wider">
        <span>Grounded in Sources</span>
        <span className="rounded-full bg-accent/10 px-1.5 py-0.2 text-10 font-semibold text-accent">
          {citations.length}
        </span>
      </div>

      <div className="flex flex-wrap items-start gap-2">
        {citations.map((citation, index) => (
          <CitationItem
            key={citation.chunk_id || `${citation.resource_id}-${citation.sequence ?? index}`}
            citation={citation}
          />
        ))}
      </div>
    </div>
  );
}
