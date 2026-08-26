"use client";

/**
 * Prompt starters on the new-chat landing. Client-side only — no backend call.
 */
export function SuggestionChips({
  suggestions,
  onSelect,
}: {
  suggestions: readonly string[];
  onSelect: (suggestion: string) => void;
}) {
  return (
    <div className="flex flex-wrap justify-center gap-2">
      {suggestions.map((s) => (
        <button
          key={s}
          onClick={() => onSelect(s)}
          className="focus-ring rounded-full border border-border bg-surface px-3.5 py-2 text-13 font-medium text-ink-secondary transition-colors duration-150 hover:bg-subtle hover:text-ink"
        >
          {s}
        </button>
      ))}
    </div>
  );
}
