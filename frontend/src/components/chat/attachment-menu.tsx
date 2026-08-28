"use client";

import { Books, FileText, Image, Plus } from "@phosphor-icons/react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { IconButton } from "@/components/ui/icon-button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Separator } from "@/components/ui/separator";

const ATTACHMENTS = [
  { icon: FileText, label: "Upload a document" },
  { icon: Image, label: "Add an image" },
  { icon: Books, label: "Add a learning resource" },
] as const;


/**
 * Composer "+"/add control. Attachment ingestion is not yet implemented on the
 * backend, so each action is clearly marked unavailable (disabled + "Soon")
 * rather than pretending to work.
 *
 * Knowledge source selection lives in the composer's KnowledgeScopePopover
 * (shown next to the send button) — it is intentionally NOT duplicated here.
 */
export function AttachmentMenu() {
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
        <p className="px-1 text-12 leading-relaxed text-ink-secondary">
          Attachments arrive when content uploads are connected.
        </p>
      </PopoverContent>
    </Popover>
  );
}
