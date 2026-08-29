"use client";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Rename dialog for a conversation. Fully controlled: the parent owns the
 * input value so it can pre-fill the current title when opened.
 */
export function RenameConversationDialog({
  open,
  onOpenChange,
  value,
  onChange,
  onSave,
  pending,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  value: string;
  onChange: (value: string) => void;
  onSave: (title: string) => void;
  pending: boolean;
}) {
  const trimmed = value.trim();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (trimmed && !pending) onSave(trimmed);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader
          title="Rename conversation"
          description="Give this conversation a name you’ll recognize later."
        />
        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Conversation title"
            autoFocus
            autoComplete="off"
            maxLength={255}
          />
          <div className="flex justify-end gap-2.5">
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!trimmed || pending}>
              {pending ? "Saving…" : "Save"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/**
 * Confirmation dialog for destructive/non-destructive conversation actions
 * (archive and delete).
 */
export function ConfirmConversationDialog({
  open,
  onOpenChange,
  title,
  description,
  confirmLabel,
  destructive = false,
  pending,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description: string;
  confirmLabel: string;
  destructive?: boolean;
  pending: boolean;
  onConfirm: () => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader title={title} description={description} />
        <div className="flex justify-end gap-2.5">
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            variant={destructive ? "danger" : "primary"}
            loading={pending}
            onClick={onConfirm}
          >
            {pending ? "Working…" : confirmLabel}
          </Button>

        </div>
      </DialogContent>
    </Dialog>
  );
}
