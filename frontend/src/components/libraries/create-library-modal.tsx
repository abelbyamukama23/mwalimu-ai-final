"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import { useCreateLibrary } from "@/lib/hooks/use-libraries";

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <span className="block text-11 font-medium uppercase tracking-wide text-ink-tertiary">
        {label}
      </span>
      {children}
    </div>
  );
}

function slugify(text: string): string {
  return text
    .toLowerCase()
    .trim()
    .replace(/[^\w\s-]/g, "")
    .replace(/[\s_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function CreateLibraryModal({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const createMutation = useCreateLibrary();
  const toast = useToast();

  const [name, setName] = useState("");
  const [slug, setSlug] = useState("");
  const [isSlugEdited, setIsSlugEdited] = useState(false);
  const [description, setDescription] = useState("");
  const [formError, setFormError] = useState<string | null>(null);

  const handleNameChange = (val: string) => {
    setName(val);
    if (!isSlugEdited) {
      setSlug(slugify(val));
    }
  };

  const resetForm = () => {
    setName("");
    setSlug("");
    setIsSlugEdited(false);
    setDescription("");
    setFormError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setFormError("Library name is required.");
      return;
    }

    const finalSlug = slug.trim() || slugify(name);
    if (!finalSlug) {
      setFormError("Library slug is required.");
      return;
    }

    setFormError(null);

    try {
      await createMutation.mutateAsync({
        name: name.trim(),
        slug: finalSlug,
        description: description.trim() || undefined,
      });

      toast("Personal library created successfully");
      resetForm();
      onOpenChange(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error
          ? err.message
          : "Failed to create library. Please verify the name and slug.";
      setFormError(message);
    }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) resetForm();
        onOpenChange(next);
      }}
    >
      <DialogContent>
        <DialogHeader
          title="Create a personal library"
          description="Personal libraries are private knowledge spaces for your study notes, uploaded files, and personal connectors."
        />

        <form onSubmit={handleSubmit} className="space-y-4">
          {formError && (
            <div className="rounded-md border border-danger/30 bg-danger-surface p-3 text-12 text-danger">
              {formError}
            </div>
          )}

          <Field label="Name">
            <Input
              value={name}
              onChange={(e) => handleNameChange(e.target.value)}
              placeholder="e.g. My Biology Notes"
              required
              autoFocus
            />
          </Field>

          <Field label="Slug (URL identifier)">
            <Input
              value={slug}
              onChange={(e) => {
                setSlug(e.target.value);
                setIsSlugEdited(true);
              }}
              placeholder="e.g. my-biology-notes"
              required
            />
          </Field>

          <Field label="Description">
            <Textarea
              rows={2}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What is this knowledge space for?"
            />
          </Field>

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending}>
              {createMutation.isPending ? "Creating…" : "Create library"}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
