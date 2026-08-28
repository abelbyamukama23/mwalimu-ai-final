"use client";

import { useMemo, useState } from "react";
import {
  ChevronRight,
  File,
  FileCode,
  FileText,
  Folder,
  FolderOpen,
  Loader2,
  RefreshCw,
  Search,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import {
  useBrowseConnection,
  useTriggerConnectionSync,
} from "@/lib/hooks/use-connectors";
import type { RemoteFileItem } from "@/lib/api/connectors";

type RemoteFilePickerDialogProps = {
  libraryId: string;
  connectionId: string;
  connectionName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

function formatBytes(bytes?: number): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

function getFileIcon(item: RemoteFileItem) {
  if (item.type === "folder") {
    return <Folder className="h-4 w-4 text-brand" />;
  }
  const mime = item.mime_type || "";
  const name = item.name.toLowerCase();
  if (mime.includes("pdf") || name.endsWith(".pdf")) {
    return <FileText className="h-4 w-4 text-danger" />;
  }
  if (
    mime.includes("document") ||
    mime.includes("text") ||
    name.endsWith(".docx") ||
    name.endsWith(".txt")
  ) {
    return <FileText className="h-4 w-4 text-info" />;
  }
  if (name.endsWith(".py") || name.endsWith(".ts") || name.endsWith(".js")) {
    return <FileCode className="h-4 w-4 text-warning" />;
  }
  return <File className="h-4 w-4 text-ink-tertiary" />;
}

export function RemoteFilePickerDialog({
  libraryId,
  connectionId,
  connectionName,
  open,
  onOpenChange,
}: RemoteFilePickerDialogProps) {
  const [currentFolderId, setCurrentFolderId] = useState<string>("root");
  const [breadcrumbs, setBreadcrumbs] = useState<
    { id: string; name: string }[]
  >([{ id: "root", name: "Home" }]);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const { data, isLoading, isError, refetch } = useBrowseConnection(
    libraryId,
    connectionId,
    currentFolderId,
    searchQuery || undefined,
  );

  const syncMutation = useTriggerConnectionSync(libraryId);
  const toast = useToast();

  const items = useMemo(() => data?.items ?? [], [data]);

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const selectAllInView = () => {
    const fileItems = items.filter((it) => it.type === "file");
    if (selectedIds.size >= fileItems.length && fileItems.length > 0) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(fileItems.map((it) => it.id)));
    }
  };

  const navigateToFolder = (folderId: string, folderName: string) => {
    setCurrentFolderId(folderId);
    setSearchQuery("");
    setBreadcrumbs((prev) => [...prev, { id: folderId, name: folderName }]);
  };

  const navigateToBreadcrumb = (index: number) => {
    const target = breadcrumbs[index];
    setBreadcrumbs((prev) => prev.slice(0, index + 1));
    setCurrentFolderId(target.id);
    setSearchQuery("");
  };

  const handleSyncSelected = async () => {
    try {
      await syncMutation.mutateAsync(connectionId);
      toast(`Sync initiated for ${connectionName}. Resources will be indexed shortly.`);
      onOpenChange(false);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sync trigger failed.";
      toast(msg);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-2xl flex-col p-6">
        <DialogHeader
          title="Browse & Sync Files"
          description={
            <span>
              Select documents from{" "}
              <strong className="text-ink">{connectionName}</strong> to ingest
              into this library.
            </span>
          }
          onClose={() => onOpenChange(false)}
        />

        {/* Search bar & Refresh */}
        <div className="flex items-center gap-2 border-b border-border pb-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-tertiary" />
            <Input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search remote documents..."
              className="pl-8 text-12"
            />
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => void refetch()}
            className="h-9 gap-1.5 text-12 text-ink-secondary"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>

        {/* Breadcrumbs navigation */}
        {!searchQuery && (
          <div className="my-2 flex items-center gap-1 text-11 text-ink-secondary">
            {breadcrumbs.map((crumb, idx) => (
              <div key={crumb.id} className="flex items-center gap-1">
                {idx > 0 && <ChevronRight className="h-3 w-3 text-ink-tertiary" />}
                <button
                  type="button"
                  onClick={() => navigateToBreadcrumb(idx)}
                  className={`hover:underline ${idx === breadcrumbs.length - 1 ? "font-semibold text-ink" : "text-ink-secondary"}`}
                >
                  {crumb.name}
                </button>
              </div>
            ))}
          </div>
        )}

        {/* File & Folder List Area */}
        <div className="flex-1 overflow-y-auto p-2">
          {isLoading ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 text-ink-tertiary">
              <Loader2 className="h-5 w-5 animate-spin text-brand" />
              <span className="text-12">Loading remote files…</span>
            </div>
          ) : isError || data?.error ? (
            <div className="flex h-48 flex-col items-center justify-center gap-2 p-6 text-center text-danger">
              <span className="text-13 font-medium">Failed to load files</span>
              <p className="text-11 text-danger/80">
                {data?.error || "Could not connect to the remote service. Check your credentials or permissions."}
              </p>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => void refetch()}
                className="mt-2 text-12"
              >
                Try Again
              </Button>
            </div>
          ) : items.length === 0 ? (
            <div className="flex h-48 flex-col items-center justify-center gap-1.5 text-center text-ink-tertiary">
              <FolderOpen className="h-8 w-8 stroke-1" />
              <p className="text-13 font-medium text-ink">No files found</p>
              <p className="text-11">This folder appears to be empty or has no matching documents.</p>
            </div>
          ) : (
            <div className="divide-y divide-border/50">
              {items.map((item) => {
                const isSelected = selectedIds.has(item.id);
                return (
                  <div
                    key={item.id}
                    className={`flex items-center justify-between gap-3 rounded-md px-3 py-2 text-12 transition hover:bg-surface-hover ${
                      isSelected ? "bg-brand-surface/40" : ""
                    }`}
                  >
                    <div className="flex min-w-0 flex-1 items-center gap-2.5">
                      {item.type === "file" ? (
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(item.id)}
                          className="h-4 w-4 rounded border-border text-brand focus:ring-brand"
                        />
                      ) : (
                        <span className="h-4 w-4" />
                      )}

                      <div className="flex min-w-0 flex-1 items-center gap-2">
                        {getFileIcon(item)}
                        {item.type === "folder" ? (
                          <button
                            type="button"
                            onClick={() => navigateToFolder(item.id, item.name)}
                            className="truncate text-left font-medium text-ink hover:text-brand hover:underline"
                          >
                            {item.name}
                          </button>
                        ) : (
                          <span className="truncate text-ink">{item.name}</span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-3 text-11 text-ink-tertiary">
                      {item.size ? <span>{formatBytes(item.size)}</span> : null}
                      {item.type === "folder" && (
                        <span className="rounded bg-surface-muted px-1.5 py-0.5 text-10">
                          Folder
                        </span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer Actions */}
        <div className="flex items-center justify-between border-t border-border bg-surface-muted/50 p-4">
          <div className="flex items-center gap-3 text-12 text-ink-secondary">
            <span>
              {selectedIds.size} {selectedIds.size === 1 ? "file" : "files"} selected
            </span>
            {items.some((it) => it.type === "file") && (
              <button
                type="button"
                onClick={selectAllInView}
                className="text-11 font-medium text-brand hover:underline"
              >
                {selectedIds.size > 0 ? "Deselect all" : "Select all in folder"}
              </button>
            )}
          </div>

          <div className="flex gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={syncMutation.isPending}
              onClick={handleSyncSelected}
              className="gap-1.5"
            >
              {syncMutation.isPending ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Syncing…
                </>
              ) : (
                "Sync Now"
              )}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
