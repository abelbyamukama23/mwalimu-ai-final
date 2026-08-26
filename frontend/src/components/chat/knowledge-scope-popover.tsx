"use client";

import { Check, ChevronDown, MapPin, Plus } from "lucide-react";
import { useState } from "react";
import { useSettingsModal } from "@/components/settings/settings-modal";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { cn } from "@/lib/utils";

export const SCOPES = [
  {
    id: "relevant",
    label: "Relevant sources",
    description: "Mwalimu chooses from everything you're allowed to access.",
  },
  {
    id: "my",
    label: "My libraries",
    description: "Only libraries you created or manage.",
  },
  {
    id: "institution",
    label: "Institution libraries",
    description: "Libraries shared by your institution.",
  },
  {
    id: "public",
    label: "Public knowledge",
    description: "Open and platform-curated sources.",
  },
] as const;

export type KnowledgeScope = (typeof SCOPES)[number]["id"];

/**
 * Composer knowledge/context control. Maps to what the backend supports today:
 * enabling the knowledge tool for a run. Per-chat library multi-selection is a
 * pending backend capability and is labelled as such.
 */
export function KnowledgeScopePopover({
  scope,
  onScopeChange,
}: {
  scope: KnowledgeScope;
  onScopeChange: (scope: KnowledgeScope) => void;
}) {
  const [open, setOpen] = useState(false);
  const { openSettings } = useSettingsModal();
  const active = SCOPES.find((s) => s.id === scope) ?? SCOPES[0];

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "focus-ring flex items-center gap-1.5 rounded-full bg-subtle px-3 py-1.5",
            "text-12 font-medium text-ink-secondary transition-colors duration-150 hover:bg-border",
          )}
          aria-label={`Knowledge scope: ${active.label}. Change knowledge and context.`}
        >
          Knowledge: {active.label}
          <ChevronDown size={13} aria-hidden />
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="w-80">
        <p className="px-1 pb-2 text-11 font-medium tracking-wide text-ink-tertiary">
          KNOWLEDGE SOURCES
        </p>
        <div className="space-y-0.5" role="radiogroup" aria-label="Knowledge sources">
          {SCOPES.map((s) => (
            <button
              key={s.id}
              role="radio"
              aria-checked={scope === s.id}
              onClick={() => {
                onScopeChange(s.id);
                setOpen(false);
              }}
              className="focus-ring flex w-full items-start gap-2.5 rounded-sm px-2 py-2 text-left transition-colors duration-150 hover:bg-subtle"
            >
              <span
                aria-hidden
                className={cn(
                  "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2",
                  scope === s.id ? "border-accent" : "border-border-strong",
                )}
              >
                {scope === s.id && <Check size={10} className="text-accent" strokeWidth={3} />}
              </span>
              <span>
                <span className="block text-13 font-medium text-ink">{s.label}</span>
                <span className="mt-0.5 block text-12 text-ink-tertiary">{s.description}</span>
              </span>
            </button>
          ))}
        </div>

        {/* Per-chat library multi-selection is not yet supported by the runs API. */}
        <button
          disabled
          className="mt-1 flex w-full cursor-not-allowed items-center gap-1.5 rounded-sm px-2 py-2 text-13 font-medium text-ink-tertiary opacity-60"
        >
          <Plus size={13} aria-hidden /> Select libraries… (coming soon)
        </button>

        <Separator className="my-2" />

        <p className="px-1 pb-1 text-11 font-medium tracking-wide text-ink-tertiary">
          FAMILIAR CONTEXT
        </p>
        <p className="flex items-start gap-1.5 px-1 text-12 leading-relaxed text-ink-secondary">
          <MapPin size={13} aria-hidden className="mt-0.5 shrink-0 text-terracotta" />
          Examples are grounded in your familiar regions first.
        </p>
        <button
          onClick={() => {
            setOpen(false);
            openSettings("familiar-regions");
          }}
          className="focus-ring mt-1.5 block rounded-sm px-1 py-1 text-13 font-medium text-accent hover:underline"
        >
          Manage context →
        </button>
      </PopoverContent>
    </Popover>
  );
}
