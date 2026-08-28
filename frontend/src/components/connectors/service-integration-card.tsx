"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Delete02Icon,
  FolderOpenIcon,
  Loading03Icon,
  MoreHorizontalIcon,
  PlusSignIcon,
  RefreshIcon,
} from "hugeicons-react";

import { BrandIcon } from "@/components/ui/brand-icon";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  getOAuthAuthorizeUrl,
  type Connection,
  type Connector,
} from "@/lib/api/connectors";
import {
  useDeleteLibraryConnection,
  useTriggerConnectionSync,
} from "@/lib/hooks/use-connectors";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { RemoteFilePickerDialog } from "./remote-file-picker-dialog";

type ServiceIntegrationCardProps = {
  connector: Connector;
  libraryId: string;
  existingConnection?: Connection;
};

function getAcademicBadge(connectorType: string) {
  switch (connectorType) {
    case "google_drive":
      return { tag: "Cloud Study Drive", scope: "Google Docs, Slides & Handouts" };
    case "notion":
      return { tag: "Study Databases", scope: "Course Databases, Notes & Trackers" };
    case "s3":
      return { tag: "Course Storage", scope: "Textbooks, Media & Archives" };
    case "file_system":
      return { tag: "Local Device", scope: "Offline PDFs & Course Folders" };
    default:
      return { tag: "Academic Resource", scope: "Educational Documents & Syllabi" };
  }
}

export function ServiceIntegrationCard({
  connector,
  libraryId,
  existingConnection,
}: ServiceIntegrationCardProps) {
  const [isAuthorizing, setIsAuthorizing] = useState(false);
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  const queryClient = useQueryClient();
  const syncMutation = useTriggerConnectionSync(libraryId);
  const deleteMutation = useDeleteLibraryConnection(libraryId);
  const toast = useToast();

  const isConnected = Boolean(existingConnection);
  const academicInfo = getAcademicBadge(connector.connector_type);

  useEffect(() => {
    const handleMessage = (event: MessageEvent) => {
      if (event.data?.type === "MWALIMU_OAUTH_SUCCESS") {
        void queryClient.invalidateQueries({
          queryKey: ["libraries", libraryId, "connections"],
        });
        toast(`Successfully connected ${connector.name}!`);
      }
    };
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [libraryId, connector.name, queryClient, toast]);

  const handleOAuthConnect = async () => {
    const width = 600;
    const height = 700;
    const left = window.screen.width / 2 - width / 2;
    const top = window.screen.height / 2 - height / 2;
    const popup = window.open(
      "about:blank",
      `Connect_${connector.id}`,
      `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`,
    );

    try {
      setIsAuthorizing(true);
      const provider =
        connector.connector_type === "google_drive"
          ? "google"
          : connector.connector_type === "notion"
            ? "notion"
            : "google";

      const { authorization_url } = await getOAuthAuthorizeUrl(
        libraryId,
        provider,
      );

      if (popup) {
        popup.location.href = authorization_url;
      }
      setIsAuthorizing(false);
    } catch (err: unknown) {
      if (popup) popup.close();
      const msg =
        err instanceof Error ? err.message : "Failed to initiate authorization.";
      toast(msg);
      setIsAuthorizing(false);
    }
  };

  const handleQuickSync = async () => {
    if (!existingConnection) return;
    try {
      await syncMutation.mutateAsync(existingConnection.id);
      toast(`Sync started for ${existingConnection.name}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sync failed.";
      toast(msg);
    }
  };

  const handleDisconnect = async () => {
    if (!existingConnection) return;
    if (!confirm(`Are you sure you want to disconnect ${existingConnection.name}?`))
      return;
    try {
      await deleteMutation.mutateAsync(existingConnection.id);
      toast(`Disconnected ${existingConnection.name}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to disconnect.";
      toast(msg);
    }
  };

  return (
    <>
      <div className="group flex items-center justify-between gap-4 rounded-xl border border-border bg-surface p-4 transition-all duration-150 hover:border-border-strong hover:bg-surface-elevated hover:shadow-xs">
        {/* Left: Icon and Details */}
        <div className="flex min-w-0 items-center gap-3.5">
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-border/60 bg-surface-muted shadow-2xs">
            <BrandIcon name={connector.connector_type} size={24} />
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3 className="truncate text-14 font-semibold text-ink">
                {connector.name}
              </h3>
              <span className="shrink-0 rounded bg-subtle px-1.5 py-0.5 text-10 font-medium text-ink-secondary">
                {academicInfo.tag}
              </span>
            </div>
            <p className="truncate text-12 text-ink-secondary">
              {academicInfo.scope}
            </p>
          </div>
        </div>

        {/* Right: Actions */}
        <div className="flex shrink-0 items-center gap-2">
          {isConnected ? (
            <div className="flex items-center gap-1.5">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsPickerOpen(true)}
                className="h-8 gap-1.5 rounded-lg px-3 text-12 font-medium"
              >
                <FolderOpenIcon size={15} className="text-accent" />
                Browse
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 rounded-lg p-0 text-ink-secondary hover:text-ink"
                    aria-label="More options"
                  >
                    <MoreHorizontalIcon size={18} />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-36">
                  <DropdownMenuItem
                    disabled={syncMutation.isPending}
                    onClick={handleQuickSync}
                    className="gap-2 text-12 cursor-pointer"
                  >
                    <RefreshIcon
                      size={14}
                      className={syncMutation.isPending ? "animate-spin" : ""}
                    />
                    Sync Now
                  </DropdownMenuItem>
                  <DropdownMenuItem
                    onClick={handleDisconnect}
                    className="gap-2 text-12 text-danger focus:text-danger cursor-pointer"
                  >
                    <Delete02Icon size={14} />
                    Disconnect
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          ) : (
            <Button
              size="sm"
              disabled={isAuthorizing}
              onClick={handleOAuthConnect}
              className="h-8 gap-1 rounded-lg px-3.5 text-12 font-medium shadow-xs"
            >
              {isAuthorizing ? (
                <>
                  <Loading03Icon size={14} className="animate-spin" />
                  Connecting
                </>
              ) : (
                <>
                  <PlusSignIcon size={14} />
                  Connect
                </>
              )}
            </Button>
          )}
        </div>
      </div>

      {/* Remote Picker Dialog */}
      {existingConnection && (
        <RemoteFilePickerDialog
          libraryId={libraryId}
          connectionId={existingConnection.id}
          connectionName={existingConnection.name}
          open={isPickerOpen}
          onOpenChange={setIsPickerOpen}
        />
      )}
    </>
  );
}
