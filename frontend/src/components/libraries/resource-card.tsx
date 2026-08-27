"use client";

import {
  Download,
  FileCode2,
  FileSpreadsheet,
  FileText,
  Loader2,
  MoreVertical,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { useToast } from "@/components/ui/toast";
import {
  useDeleteLibraryResource,
  useResourceProcessingStatus,
} from "@/lib/hooks/use-libraries";
import type { LibraryResource } from "@/lib/api/libraries";

const BASE_URL =
  process.env.NEXT_PUBLIC_PLATFORM_API_BASE_URL ?? "https://backend.ai-mwalimu.com";

function formatBytes(bytes: number, decimals = 1): string {
  if (!bytes || bytes === 0) return "0 B";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

export function ResourceCard({
  resource,
  libraryId,
  canManage,
}: {
  resource: LibraryResource;
  libraryId: string;
  canManage: boolean;
}) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const deleteMutation = useDeleteLibraryResource(libraryId);
  const toast = useToast();

  const { data: procStatus } = useResourceProcessingStatus(libraryId, resource.id);

  const handleDelete = async () => {
    try {
      await deleteMutation.mutateAsync(resource.id);
      toast("Resource deleted successfully.");
    } catch {
      toast("Failed to delete resource.");
    } finally {
      setConfirmDelete(false);
    }
  };

  // Compute file visual badge tone & icon
  const ext = resource.resource_type?.toLowerCase() || "txt";
  const isPdf = ext === "pdf";
  const isDocx = ext === "docx";

  // Status computation
  const currentStatus = procStatus?.status ?? resource.status;
  const chunksCount = procStatus?.chunks_count ?? 0;
  const isReady = currentStatus === "ready" || currentStatus === "indexed";
  const isProcessing = currentStatus === "processing";
  const isFailed = currentStatus === "failed";

  const downloadUrl = `${BASE_URL}/api/v1/libraries/${libraryId}/resources/${resource.id}/download/`;

  return (
    <div className="group relative flex flex-col justify-between rounded-lg border border-border bg-surface p-5 transition-all duration-150 hover:border-border-strong hover:shadow-sm">
      <div>
        {/* Top bar: Format badge and Actions */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2">
            <div
              className={`flex h-10 w-10 items-center justify-center rounded-lg border text-16 font-semibold ${
                isPdf
                  ? "border-danger-border bg-danger-subtle text-danger"
                  : isDocx
                    ? "border-accent-border bg-accent-subtle text-accent"
                    : "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
              }`}
            >
              {isPdf ? (
                <FileText size={20} aria-hidden />
              ) : isDocx ? (
                <FileSpreadsheet size={20} aria-hidden />
              ) : (
                <FileCode2 size={20} aria-hidden />
              )}
            </div>
            <div>
              <span className="text-11 font-mono uppercase tracking-wider text-ink-tertiary">
                {ext}
              </span>
              <p className="text-11 text-ink-tertiary">
                {formatBytes(resource.size)}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <a
              href={downloadUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-tertiary transition-colors hover:bg-surface-hover hover:text-ink focus-ring"
              title="Download original file"
            >
              <Download size={14} aria-hidden />
            </a>

            {canManage && (
              <button
                type="button"
                onClick={() => setConfirmDelete(!confirmDelete)}
                className="inline-flex h-8 w-8 items-center justify-center rounded-md text-ink-tertiary transition-colors hover:bg-danger-subtle hover:text-danger focus-ring"
                title="Delete resource"
              >
                <Trash2 size={14} aria-hidden />
              </button>
            )}
          </div>
        </div>

        {/* Resource Name and Original Filename */}
        <div className="mt-3.5 space-y-1">
          <h4
            className="text-14 font-semibold text-ink line-clamp-2 leading-snug group-hover:text-accent transition-colors"
            title={resource.name}
          >
            {resource.name}
          </h4>
          <p
            className="text-12 text-ink-secondary truncate font-mono text-11"
            title={resource.original_filename}
          >
            {resource.original_filename}
          </p>
        </div>
      </div>

      {/* Footer: Ingestion status & upload date */}
      <div className="mt-5 pt-3 border-t border-border-subtle flex items-center justify-between gap-2 text-11 text-ink-tertiary">
        <div className="flex items-center gap-1.5">
          {isReady ? (
            <Badge tone="success">
              Ready {chunksCount > 0 ? `· ${chunksCount} chunks` : ""}
            </Badge>
          ) : isProcessing ? (
            <Badge tone="accent">
              <Loader2 size={10} className="mr-1 animate-spin inline" />
              Chunking…
            </Badge>
          ) : isFailed ? (
            <Badge tone="warning">Failed</Badge>
          ) : (
            <Badge tone="neutral">Queued</Badge>
          )}
        </div>

        <span>
          {new Date(resource.created_at).toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
          })}
        </span>
      </div>

      {/* Delete confirmation overlay */}
      {confirmDelete && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 rounded-lg bg-surface/95 p-4 text-center backdrop-blur-sm">
          <p className="text-12 font-medium text-ink">
            Delete this resource from library?
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="primary"
              className="bg-danger hover:bg-danger/90 text-white border-transparent"
              size="sm"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? "Deleting…" : "Confirm Delete"}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setConfirmDelete(false)}
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
