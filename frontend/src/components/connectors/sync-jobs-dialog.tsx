"use client";

import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
} from "@/components/ui/dialog";
import { useConnectionSyncJobs } from "@/lib/hooks/use-connectors";
import type { SyncJobStatus } from "@/lib/api/connectors";

type SyncJobsDialogProps = {
  libraryId: string;
  connectionId: string | null;
  connectionName?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function SyncJobsDialog({
  libraryId,
  connectionId,
  connectionName,
  open,
  onOpenChange,
}: SyncJobsDialogProps) {
  const { data: syncJobs, isLoading } = useConnectionSyncJobs(
    libraryId,
    connectionId ?? undefined,
  );

  const getStatusTone = (status: SyncJobStatus) => {
    switch (status) {
      case "completed":
        return "success" as const;
      case "running":
      case "queued":
        return "neutral" as const;
      case "failed":
      case "cancelled":
        return "warning" as const;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-xl overflow-y-auto">
        <DialogHeader
          title={
            connectionName
              ? `Sync History: ${connectionName}`
              : "Sync Job History"
          }
          description="Historical synchronization runs and resource discovery ledgers."
        />

        {isLoading ? (
          <div className="py-8 text-center text-13 text-ink-tertiary">
            Loading synchronization history…
          </div>
        ) : !syncJobs || syncJobs.length === 0 ? (
          <div className="py-8 text-center text-13 text-ink-tertiary">
            No synchronization runs recorded yet.
          </div>
        ) : (
          <div className="divide-y divide-border pt-2">
            {syncJobs.map((job) => (
              <div key={job.id} className="py-3.5 space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Badge tone={getStatusTone(job.status)}>
                      {job.status}
                    </Badge>
                    <span className="text-12 text-ink-tertiary">
                      {new Date(job.created_at).toLocaleString()}
                    </span>
                  </div>
                  {job.finished_at && (
                    <span className="text-11 text-ink-tertiary">
                      Finished: {new Date(job.finished_at).toLocaleTimeString()}
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-4 gap-2 rounded-md bg-surface-sunken p-2.5 text-center text-11">
                  <div>
                    <span className="block text-ink-tertiary">Discovered</span>
                    <span className="font-semibold text-ink">
                      {job.resources_discovered}
                    </span>
                  </div>
                  <div>
                    <span className="block text-ink-tertiary">Created</span>
                    <span className="font-semibold text-ink">
                      {job.resources_created}
                    </span>
                  </div>
                  <div>
                    <span className="block text-ink-tertiary">Updated</span>
                    <span className="font-semibold text-ink">
                      {job.resources_updated}
                    </span>
                  </div>
                  <div>
                    <span className="block text-ink-tertiary">Deleted</span>
                    <span className="font-semibold text-ink">
                      {job.resources_deleted}
                    </span>
                  </div>
                </div>

                {job.error_message && (
                  <div className="rounded border border-danger/30 bg-danger-surface p-2 text-11 text-danger">
                    {job.error_code && (
                      <span className="font-semibold">[{job.error_code}] </span>
                    )}
                    {job.error_message}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
