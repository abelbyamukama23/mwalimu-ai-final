"use client";

import {
  ArrowRight01Icon,
  Cancel01Icon,
  Download01Icon,
  FileUploadIcon,
  Folder01Icon,
  FolderAddIcon,
  Grid02Icon,
  Home01Icon,
  ListViewIcon,
  Loading03Icon,
  Search01Icon,
} from "hugeicons-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { useToast } from "@/components/ui/toast";
import { useUploadLibraryResource } from "@/lib/hooks/use-libraries";
import { DocumentIcon } from "./document-icon";
import { ResourceCard } from "./resource-card";
import { ResourceUploadModal } from "./resource-upload-modal";
import type { LibraryResource } from "@/lib/api/libraries";

const BASE_URL =
  process.env.NEXT_PUBLIC_PLATFORM_API_BASE_URL ?? "https://backend.ai-mwalimu.com";

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export type UploadingQueueItem = {
  id: string;
  name: string;
  original_filename: string;
  size: number;
  resource_type: "pdf" | "docx" | "txt";
  targetFolder: string;
  progress: number;
  status: "uploading" | "indexing" | "error";
  error?: string;
};

export function FolderTreeExplorer({
  libraryId,
  resources,
  canManage,
}: {
  libraryId: string;
  resources: LibraryResource[];
  canManage: boolean;
}) {
  const [currentPath, setCurrentPath] = useState<string[]>([]);
  const [viewMode, setViewMode] = useState<"table" | "grid">("grid");
  const [searchFilter, setSearchFilter] = useState("");
  const [uploadOpen, setUploadOpen] = useState(false);
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");
  const [customFolders, setCustomFolders] = useState<string[]>([]);
  const [uploadingQueue, setUploadingQueue] = useState<UploadingQueueItem[]>([]);

  const uploadMutation = useUploadLibraryResource(libraryId);
  const toast = useToast();

  const activePathString = currentPath.join("/");

  // Uploading items scoped to the currently opened folder
  const currentUploadingItems = useMemo(() => {
    return uploadingQueue.filter(
      (item) => item.targetFolder === activePathString,
    );
  }, [uploadingQueue, activePathString]);

  // Compute folder hierarchy from resource names
  const { currentFolderList, currentFileList } = useMemo(() => {
    const foldersSet = new Set<string>();
    const files: (LibraryResource & { displayName: string })[] = [];

    // Add locally created empty folders that match current path
    for (const cf of customFolders) {
      if (activePathString) {
        if (cf.startsWith(activePathString + "/")) {
          const remainder = cf.slice(activePathString.length + 1);
          const nextSegment = remainder.split("/")[0];
          if (nextSegment) foldersSet.add(nextSegment);
        }
      } else {
        const firstSegment = cf.split("/")[0];
        if (firstSegment) foldersSet.add(firstSegment);
      }
    }

    for (const res of resources) {
      const name = res.name || res.original_filename;
      const parts = name.split("/").filter(Boolean);

      if (currentPath.length === 0) {
        if (parts.length > 1) {
          foldersSet.add(parts[0]);
        } else {
          files.push({ ...res, displayName: parts[0] || name });
        }
      } else {
        const startsWithCurrent = parts
          .slice(0, currentPath.length)
          .every((p, idx) => p.toLowerCase() === currentPath[idx].toLowerCase());

        if (startsWithCurrent) {
          const remainingParts = parts.slice(currentPath.length);
          if (remainingParts.length > 1) {
            foldersSet.add(remainingParts[0]);
          } else if (remainingParts.length === 1) {
            files.push({ ...res, displayName: remainingParts[0] });
          }
        }
      }
    }

    // Filter by search query if any
    let filteredFiles = files;
    if (searchFilter.trim()) {
      const q = searchFilter.toLowerCase().trim();
      filteredFiles = files.filter(
        (f) =>
          f.name.toLowerCase().includes(q) ||
          f.original_filename.toLowerCase().includes(q),
      );
    }

    return {
      currentFolderList: Array.from(foldersSet).sort(),
      currentFileList: filteredFiles,
    };
  }, [resources, currentPath, activePathString, customFolders, searchFilter]);

  const handleEnterFolder = (folderName: string) => {
    setCurrentPath((prev) => [...prev, folderName]);
  };

  const handleNavigateToBreadcrumb = (index: number) => {
    if (index === -1) {
      setCurrentPath([]);
    } else {
      setCurrentPath((prev) => prev.slice(0, index + 1));
    }
  };

  const handleCreateFolder = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newFolderName.trim()) return;
    const pathToAdd = activePathString
      ? `${activePathString}/${newFolderName.trim()}`
      : newFolderName.trim();

    setCustomFolders((prev) => Array.from(new Set([...prev, pathToAdd])));
    setNewFolderName("");
    setNewFolderOpen(false);
  };

  const handleStartUpload = async ({
    file,
    name,
    resourceType,
    targetFolder,
  }: {
    file: File;
    name: string;
    resourceType: "pdf" | "docx" | "txt";
    targetFolder: string;
  }) => {
    const uploadId = `upload_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
    const finalName = targetFolder
      ? `${targetFolder}/${name}`
      : name;

    const newItem: UploadingQueueItem = {
      id: uploadId,
      name: finalName,
      original_filename: file.name,
      size: file.size,
      resource_type: resourceType,
      targetFolder,
      progress: 20,
      status: "uploading",
    };

    setUploadingQueue((prev) => [newItem, ...prev]);

    // Simulated progress tick while upload transfers
    const progressInterval = setInterval(() => {
      setUploadingQueue((prev) =>
        prev.map((item) => {
          if (item.id === uploadId && item.status === "uploading") {
            const nextProgress = Math.min(item.progress + 15, 85);
            return {
              ...item,
              progress: nextProgress,
              status: nextProgress >= 70 ? "indexing" : "uploading",
            };
          }
          return item;
        }),
      );
    }, 400);

    const formData = new FormData();
    formData.append("file", file);
    formData.append("name", finalName);
    formData.append("resource_type", resourceType);

    try {
      await uploadMutation.mutateAsync(formData);
      clearInterval(progressInterval);

      // Transition to completed
      setUploadingQueue((prev) =>
        prev.map((item) =>
          item.id === uploadId ? { ...item, progress: 100, status: "indexing" } : item,
        ),
      );

      toast(`"${file.name}" uploaded successfully`);

      // Clear from queue after a short delay so user sees 100% completion
      setTimeout(() => {
        setUploadingQueue((prev) => prev.filter((item) => item.id !== uploadId));
      }, 1000);
    } catch (err: unknown) {
      clearInterval(progressInterval);
      const message =
        err instanceof Error ? err.message : "Failed to upload file.";
      setUploadingQueue((prev) =>
        prev.map((item) =>
          item.id === uploadId
            ? { ...item, status: "error", error: message }
            : item,
        ),
      );
      toast(message);
    }
  };

  const handleDismissUploadError = (id: string) => {
    setUploadingQueue((prev) => prev.filter((item) => item.id !== id));
  };

  return (
    <div className="space-y-4">
      {/* Top Toolbar: Breadcrumbs & Controls */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
        {/* Breadcrumb Navigation */}
        <div className="flex flex-wrap items-center gap-1.5 text-13 text-ink">
          <button
            type="button"
            onClick={() => handleNavigateToBreadcrumb(-1)}
            className="flex items-center gap-1.5 font-semibold text-ink-secondary hover:text-accent focus-ring rounded px-1.5 py-0.5 transition-colors"
          >
            <Home01Icon size={16} className="text-accent" aria-hidden />
            <span>Root</span>
          </button>

          {currentPath.map((seg, idx) => (
            <div key={idx} className="flex items-center gap-1">
              <ArrowRight01Icon size={12} className="text-ink-tertiary" />
              <button
                type="button"
                onClick={() => handleNavigateToBreadcrumb(idx)}
                className={`rounded px-1.5 py-0.5 hover:text-accent focus-ring transition-colors ${
                  idx === currentPath.length - 1
                    ? "font-semibold text-ink"
                    : "text-ink-secondary"
                }`}
              >
                {seg}
              </button>
            </div>
          ))}
        </div>

        {/* Action Buttons & View Toggles */}
        <div className="flex items-center gap-2">
          {/* Search within folder */}
          <div className="relative">
            <Search01Icon
              size={14}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-tertiary"
            />
            <input
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              placeholder="Filter files…"
              className="h-8 w-36 sm:w-44 rounded-md border border-border bg-surface-sunken pl-8 pr-2 text-12 text-ink placeholder:text-ink-tertiary focus-ring"
            />
          </div>

          {/* Grid / Table View toggle */}
          <div className="flex items-center rounded-md border border-border bg-surface-sunken p-0.5">
            <button
              type="button"
              onClick={() => setViewMode("grid")}
              className={`rounded p-1 text-ink-secondary transition-colors ${
                viewMode === "grid"
                  ? "bg-surface text-ink shadow-xs"
                  : "hover:text-ink"
              }`}
              title="Grid card view"
            >
              <Grid02Icon size={16} />
            </button>
            <button
              type="button"
              onClick={() => setViewMode("table")}
              className={`rounded p-1 text-ink-secondary transition-colors ${
                viewMode === "table"
                  ? "bg-surface text-ink shadow-xs"
                  : "hover:text-ink"
              }`}
              title="Table list view"
            >
              <ListViewIcon size={16} />
            </button>
          </div>

          {canManage && (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setNewFolderOpen(true)}
              >
                <FolderAddIcon size={15} className="text-amber-500" aria-hidden /> New folder
              </Button>
              <Button
                size="sm"
                onClick={() => setUploadOpen(true)}
              >
                <FileUploadIcon size={15} aria-hidden /> Upload here
              </Button>
            </>
          )}
        </div>
      </div>

      {/* New Folder Inline Form */}
      {newFolderOpen && (
        <form
          onSubmit={handleCreateFolder}
          className="flex items-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 p-3"
        >
          <Folder01Icon size={18} className="text-amber-500 fill-amber-400/20 shrink-0" />
          <Input
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="Folder name (e.g. Biology, Unit 2 - Dynamics)"
            className="h-8 text-13"
            autoFocus
          />
          <Button type="submit" size="sm">
            Create
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => setNewFolderOpen(false)}
          >
            Cancel
          </Button>
        </form>
      )}

      {/* Folder Items (Golden Amber Folder Styling) */}
      {currentFolderList.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-border bg-surface">
          <div className="bg-surface-sunken px-4 py-2 text-11 font-semibold uppercase tracking-wider text-ink-tertiary border-b border-border">
            Folders ({currentFolderList.length})
          </div>
          <div className="divide-y divide-border">
            {currentFolderList.map((folderName) => {
              const fullFolderPath = activePathString
                ? `${activePathString}/${folderName}`
                : folderName;
              const count = resources.filter((r) =>
                r.name.startsWith(fullFolderPath + "/"),
              ).length;

              return (
                <button
                  key={folderName}
                  type="button"
                  onClick={() => handleEnterFolder(folderName)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-surface-hover group focus-ring cursor-pointer"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-amber-500/10 text-amber-600 dark:text-amber-400 group-hover:bg-amber-500/20 transition-colors">
                      <Folder01Icon size={18} className="fill-amber-400/30" />
                    </div>
                    <span className="text-13 font-semibold text-ink group-hover:text-amber-700 dark:group-hover:text-amber-300 transition-colors">
                      {folderName}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <Badge tone="neutral">{count} {count === 1 ? "item" : "items"}</Badge>
                    <ArrowRight01Icon size={14} className="text-ink-tertiary" />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Uploading Queue Progress Cards (Non-blocking with Blue Progress Bar) */}
      {currentUploadingItems.length > 0 && (
        <div className="space-y-2">
          {currentUploadingItems.map((item) => (
            <div
              key={item.id}
              className="flex flex-col gap-2 rounded-lg border border-blue-200 bg-blue-50/50 p-3.5 shadow-2xs dark:border-blue-900/50 dark:bg-blue-950/20"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2.5 min-w-0">
                  <DocumentIcon filenameOrType={item.original_filename} size="sm" />
                  <div className="truncate">
                    <p className="text-13 font-medium text-ink truncate">
                      {item.name.split("/").pop()}
                    </p>
                    <p className="text-11 text-ink-tertiary">
                      {formatBytes(item.size)} · {item.resource_type.toUpperCase()}
                    </p>
                  </div>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  {item.status === "error" ? (
                    <>
                      <span className="text-11 font-medium text-red-600">Upload failed</span>
                      <button
                        type="button"
                        onClick={() => handleDismissUploadError(item.id)}
                        className="text-ink-tertiary hover:text-ink focus-ring rounded p-1"
                        aria-label="Dismiss error"
                      >
                        <Cancel01Icon size={14} />
                      </button>
                    </>
                  ) : (
                    <div className="flex items-center gap-1.5 text-12 font-medium text-blue-700 dark:text-blue-400">
                      <Loading03Icon size={13} className="animate-spin" />
                      <span>{item.status === "uploading" ? "Uploading…" : "Chunking…"}</span>
                      <span className="font-mono text-11">({item.progress}%)</span>
                    </div>
                  )}
                </div>
              </div>

              {/* Blue Progress Bar */}
              <div className="h-1.5 w-full overflow-hidden rounded-full bg-blue-200/60 dark:bg-blue-900/40">
                <div
                  className={`h-full transition-all duration-300 ${
                    item.status === "error" ? "bg-red-500" : "bg-blue-600"
                  }`}
                  style={{ width: `${item.progress}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Files Section */}
      {currentFileList.length === 0 && currentFolderList.length === 0 && currentUploadingItems.length === 0 ? (
        <EmptyState
          icon={Folder01Icon}
          title={
            currentPath.length > 0
              ? `Folder "${currentPath[currentPath.length - 1]}" is empty`
              : "No resources in library"
          }
          body="Upload documents or create subfolders to organize your course notes and textbooks."
          action={
            canManage ? (
              <Button onClick={() => setUploadOpen(true)}>
                <FileUploadIcon size={14} aria-hidden /> Upload resource here
              </Button>
            ) : undefined
          }
        />
      ) : currentFileList.length > 0 && viewMode === "grid" ? (
        /* Grid Display Cards */
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {currentFileList.map((resource) => (
            <ResourceCard
              key={resource.id}
              resource={resource}
              libraryId={libraryId}
              canManage={canManage}
            />
          ))}
        </div>
      ) : currentFileList.length > 0 && viewMode === "table" ? (
        /* Table / List View */
        <div className="overflow-hidden rounded-lg border border-border bg-surface">
          <div className="bg-surface-sunken px-4 py-2 text-11 font-semibold uppercase tracking-wider text-ink-tertiary border-b border-border flex items-center justify-between">
            <span>Files ({currentFileList.length})</span>
            <span>Size · Status · Actions</span>
          </div>
          <div className="divide-y divide-border">
            {currentFileList.map((resource) => {
              const downloadUrl = `${BASE_URL}/api/v1/libraries/${libraryId}/resources/${resource.id}/download/`;
              const fileIdentifier = resource.original_filename || resource.name || resource.resource_type;

              return (
                <div
                  key={resource.id}
                  className="flex items-center justify-between px-4 py-3 hover:bg-surface-hover transition-colors"
                >
                  <div className="flex items-center gap-3 min-w-0 pr-4">
                    <DocumentIcon filenameOrType={fileIdentifier} size="sm" />
                    <div className="min-w-0">
                      <p className="text-13 font-semibold text-ink truncate">
                        {resource.displayName}
                      </p>
                      <p className="text-11 font-mono text-ink-tertiary truncate">
                        {resource.original_filename}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-3 shrink-0 text-12 text-ink-tertiary">
                    <span>{formatBytes(resource.size)}</span>
                    <Badge
                      tone={
                        resource.status === "indexed" ||
                        (resource.status as string) === "ready"
                          ? "success"
                          : "neutral"
                      }
                    >
                      {resource.status}
                    </Badge>
                    <a
                      href={downloadUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-tertiary hover:bg-surface hover:text-ink focus-ring"
                      title="Download"
                    >
                      <Download01Icon size={16} />
                    </a>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ) : null}

      {/* Upload Modal */}
      <ResourceUploadModal
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        currentFolder={activePathString}
        onStartUpload={handleStartUpload}
      />
    </div>
  );
}

