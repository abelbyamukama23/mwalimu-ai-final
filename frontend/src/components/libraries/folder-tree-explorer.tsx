"use client";

import {
  ChevronRight,
  Download,
  FileCode2,
  FileSpreadsheet,
  FileText,
  Folder,
  FolderPlus,
  Grid,
  Home,
  LayoutGrid,
  List,
  Plus,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
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

  const activePathString = currentPath.join("/");

  // Compute folder hierarchy from resource names (e.g. "Physics/Chapter 1/Newton.pdf" or "Unit 1/Notes")
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
        // In subfolder
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

  return (
    <div className="space-y-4">
      {/* Top Toolbar: Breadcrumbs & Controls */}
      <div className="flex flex-col gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between">
        {/* GitHub-style Breadcrumb Navigation */}
        <div className="flex flex-wrap items-center gap-1.5 text-13 text-ink">
          <button
            type="button"
            onClick={() => handleNavigateToBreadcrumb(-1)}
            className="flex items-center gap-1 font-semibold text-ink-secondary hover:text-accent focus-ring rounded px-1.5 py-0.5"
          >
            <Home size={14} className="text-accent" aria-hidden />
            <span>Root</span>
          </button>

          {currentPath.map((seg, idx) => (
            <div key={idx} className="flex items-center gap-1">
              <ChevronRight size={13} className="text-ink-tertiary" />
              <button
                type="button"
                onClick={() => handleNavigateToBreadcrumb(idx)}
                className={`rounded px-1.5 py-0.5 hover:text-accent focus-ring ${
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
            <Search
              size={13}
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
              <LayoutGrid size={14} />
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
              <List size={14} />
            </button>
          </div>

          {canManage && (
            <>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setNewFolderOpen(true)}
              >
                <FolderPlus size={13} aria-hidden /> New folder
              </Button>
              <Button
                size="sm"
                onClick={() => setUploadOpen(true)}
              >
                <Upload size={13} aria-hidden /> Upload
              </Button>
            </>
          )}
        </div>
      </div>

      {/* New Folder Inline Form */}
      {newFolderOpen && (
        <form
          onSubmit={handleCreateFolder}
          className="flex items-center gap-2 rounded-lg border border-accent/40 bg-accent-subtle/20 p-3"
        >
          <Folder size={16} className="text-accent shrink-0" />
          <Input
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="Folder name (e.g. Unit 2 - Dynamics)"
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

      {/* Folder Items (GitHub Style Table Rows) */}
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
                  className="flex w-full items-center justify-between px-4 py-3 text-left transition-colors hover:bg-surface-hover group focus-ring"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex h-8 w-8 items-center justify-center rounded-md bg-accent-subtle/40 text-accent group-hover:bg-accent group-hover:text-white transition-colors">
                      <Folder size={16} />
                    </div>
                    <span className="text-13 font-semibold text-ink group-hover:text-accent transition-colors">
                      {folderName}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <Badge tone="neutral">{count} {count === 1 ? "item" : "items"}</Badge>
                    <ChevronRight size={14} className="text-ink-tertiary" />
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Files Section */}
      {currentFileList.length === 0 && currentFolderList.length === 0 ? (
        <EmptyState
          icon={Folder}
          title={
            currentPath.length > 0
              ? `Folder "${currentPath[currentPath.length - 1]}" is empty`
              : "No resources in library"
          }
          body="Upload documents or create subfolders to organize your course notes and textbooks."
          action={
            canManage ? (
              <Button onClick={() => setUploadOpen(true)}>
                <Upload size={14} aria-hidden /> Upload resource here
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
        /* GitHub Style Table / List View */
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
                      <Download size={14} />
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
        libraryId={libraryId}
        currentFolder={activePathString}
      />
    </div>
  );
}
