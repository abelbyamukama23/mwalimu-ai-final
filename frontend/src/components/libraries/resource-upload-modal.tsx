"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { CloudArrowUp, FileText, SpinnerGap, X } from "@phosphor-icons/react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { useUploadLibraryResource } from "@/lib/hooks/use-libraries";

function detectResourceType(filename: string): "pdf" | "docx" | "txt" {
  const ext = filename.split(".").pop()?.toLowerCase();
  if (ext === "pdf") return "pdf";
  if (ext === "docx" || ext === "doc") return "docx";
  return "txt";
}

export function ResourceUploadModal({
  open,
  onOpenChange,
  libraryId,
  currentFolder,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  libraryId: string;
  currentFolder?: string;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [name, setName] = useState("");
  const [resourceType, setResourceType] = useState<"pdf" | "docx" | "txt">("pdf");
  const [folderPrefix, setFolderPrefix] = useState(currentFolder || "");
  const [dragOver, setDragOver] = useState(false);

  const uploadMutation = useUploadLibraryResource(libraryId);
  const toast = useToast();

  const handleFileChange = (selectedFile: File) => {
    setFile(selectedFile);
    const inferredType = detectResourceType(selectedFile.name);
    setResourceType(inferredType);
    if (!name) {
      // Clean extension for human title
      const baseName = selectedFile.name.replace(/\.[^/.]+$/, "");
      setName(baseName);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) {
      toast("Please select a file to upload.");
      return;
    }

    const finalName = folderPrefix.trim()
      ? `${folderPrefix.trim().replace(/\/+$/, "")}/${name.trim() || file.name}`
      : name.trim() || file.name;

    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", finalName);
    formData.append("resource_type", resourceType);

    try {
      await uploadMutation.mutateAsync(formData);
      toast(`"${finalName}" uploaded successfully. Chunking initiated.`);
      onOpenChange(false);
      // Reset form
      setFile(null);
      setName("");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to upload resource.";
      toast(message);
    }
  };

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs animate-in fade-in" />
        <DialogPrimitive.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl animate-in zoom-in-95">
          <div className="flex items-center justify-between pb-4 border-b border-border">
            <div>
              <DialogPrimitive.Title className="text-18 font-semibold text-ink">
                Upload Resource
              </DialogPrimitive.Title>
              <DialogPrimitive.Description className="text-12 text-ink-secondary mt-0.5">
                Upload notes, textbooks, or course files (PDF, DOCX, TXT) to this library.
              </DialogPrimitive.Description>
            </div>
            <DialogPrimitive.Close asChild>
              <IconButton
                variant="ghost"
                size="sm"
                aria-label="Close upload modal"
              >
                <X size={16} />
              </IconButton>
            </DialogPrimitive.Close>
          </div>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            {/* File Dropzone */}
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                if (e.dataTransfer.files?.[0]) {
                  handleFileChange(e.dataTransfer.files[0]);
                }
              }}
              className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                dragOver
                  ? "border-accent bg-accent-subtle/30"
                  : file
                    ? "border-emerald-500/40 bg-emerald-500/5"
                    : "border-border hover:border-border-strong bg-surface-sunken"
              }`}
            >
              {file ? (
                <div className="flex items-center gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                    <FileText size={20} weight="duotone" />
                  </div>
                  <div className="text-left">
                    <p className="text-13 font-semibold text-ink truncate max-w-[260px]">
                      {file.name}
                    </p>
                    <p className="text-11 text-ink-tertiary">
                      {(file.size / 1024).toFixed(1)} KB · {resourceType.toUpperCase()}
                    </p>
                  </div>
                </div>
              ) : (
                <>
                  <CloudArrowUp size={36} weight="duotone" className="text-ink-tertiary mb-2" />
                  <p className="text-13 font-medium text-ink">
                    Drag and drop file here, or browse
                  </p>
                  <p className="text-11 text-ink-tertiary mt-1">
                    Supports PDF, DOCX, or TXT documents up to 50MB
                  </p>
                </>
              )}

              <input
                type="file"
                accept=".pdf,.docx,.doc,.txt"
                onChange={(e) => {
                  if (e.target.files?.[0]) {
                    handleFileChange(e.target.files[0]);
                  }
                }}
                className="mt-3 text-12 text-ink-secondary file:mr-3 file:rounded-md file:border-0 file:bg-surface file:px-3 file:py-1 file:text-12 file:font-semibold file:text-ink file:shadow-xs hover:file:bg-surface-hover cursor-pointer"
              />
            </div>

            {/* Resource Title Input */}
            <div className="space-y-1.5">
              <label className="text-12 font-medium text-ink">
                Resource Name / Title
              </label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Chapter 3: Mechanical Equilibrium Notes"
                required
              />
            </div>

            {/* Folder / Category (Optional) */}
            <div className="space-y-1.5">
              <label className="text-12 font-medium text-ink flex items-center justify-between">
                <span>Folder / Subcategory (Optional)</span>
                <span className="text-11 text-ink-tertiary">e.g. Unit 1/Mechanics</span>
              </label>
              <Input
                value={folderPrefix}
                onChange={(e) => setFolderPrefix(e.target.value)}
                placeholder="Leave blank for library root"
              />
            </div>

            {/* Modal Actions */}
            <div className="flex items-center justify-end gap-2 pt-3 border-t border-border">
              <Button
                type="button"
                variant="secondary"
                onClick={() => onOpenChange(false)}
                disabled={uploadMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!file || uploadMutation.isPending}
              >
                {uploadMutation.isPending ? (
                  <>
                    <SpinnerGap size={14} className="mr-1.5 animate-spin" />
                    Uploading to R2…
                  </>
                ) : (
                  "Upload & Chunk"
                )}
              </Button>
            </div>
          </form>

        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
