"use client";

import { Check, FileText, Image as ImageIcon, Library, Plus } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { IconButton } from "@/components/ui/icon-button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";
import { type KnowledgeScope, SCOPES } from "@/components/chat/knowledge-scope-popover";
import { cn } from "@/lib/utils";

const ATTACHMENTS = [
  { icon: FileText, label: "Upload a document" },
  { icon: ImageIcon, label: "Add an image" },
  { icon: Library, label: "Add a learning resource" },
] as const;

/**
 * Composer "+"/add control. Attachment ingestion is not yet implemented on the
 * backend, so each action is clearly marked unavailable (disabled + "Soon")
 * rather than pretending to work.
 *
 * It also exposes and syncs the Mwalimu KnowledgeScope state to provide
 * direct knowledge management alongside file uploads.
 */
export function AttachmentMenu({
  scope,
  onScopeChange,
}: {
  scope: KnowledgeScope;
  onScopeChange: (scope: KnowledgeScope) => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <IconButton
          aria-label="Add attachment"
          className="text-ink-secondary hover:text-ink"
        >
          <Plus size={18} />
        </IconButton>
      </PopoverTrigger>
      <PopoverContent align="start" side="top" className="w-64">
        <p className="px-1 pb-2 text-11 font-medium tracking-wide text-ink-tertiary">
          ADD TO CONVERSATION
        </p>
        <div className="space-y-0.5">
          {ATTACHMENTS.map((item) => (
            <button
              key={item.label}
              disabled
              className="flex w-full cursor-not-allowed items-center gap-2.5 rounded-sm px-2 py-2 text-left text-13 text-ink-tertiary opacity-60"
            >
              <item.icon size={15} aria-hidden className="shrink-0" />
              <span className="flex-1">{item.label}</span>
              <Badge tone="warning">Soon</Badge>
            </button>
          ))}
        </div>
        <Separator className="my-2" />
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
              className="focus-ring flex w-full items-center gap-2.5 rounded-sm px-2 py-1.5 text-left transition-colors duration-150 hover:bg-subtle"
            >
              <span
                aria-hidden
                className={cn(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2",
                  scope === s.id ? "border-accent" : "border-border-strong",
                )}
              >
                {scope === s.id && <Check size={10} className="text-accent" strokeWidth={3} />}
              </span>
              <span className="text-13 font-medium text-ink">{s.label}</span>
            </button>
          ))}
        </div>
        <Separator className="my-2" />
        <p className="px-1 text-12 leading-relaxed text-ink-secondary">
          Attachments arrive when content uploads are connected.
        </p>
      </PopoverContent>
    </Popover>
  );
}
