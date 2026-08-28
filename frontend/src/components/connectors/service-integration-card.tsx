"use client";

import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Delete02Icon,
  FolderOpenIcon,
  Globe02Icon,
  HardDriveIcon,
  Loading03Icon,
  MoreHorizontalIcon,
  PlusSignIcon,
  RefreshIcon,
} from "hugeicons-react";

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

function getServiceIcon(connectorType: string) {
  switch (connectorType) {
    case "google_drive":
      return (
        <svg className="h-6 w-6" viewBox="0 0 87.3 78" fill="none">
          <path d="M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H6.6c-4.4 0-7.3 4.4-4.8 8.2z" fill="#0066DA" />
          <path d="M43.65 25L29.9 1.2c-1.35.8-2.5 1.9-3.3 3.3L1.8 45.7c-2.2 3.8.7 8.6 5.1 8.6h27.5L43.65 25z" fill="#00AC47" />
          <path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.8c2.2-3.8-.7-8.6-5.1-8.6H43.65l13.75 23.8c4.35 0 7.35-4.35 16.15-9.1z" fill="#EA4335" />
          <path d="M43.65 25L57.4 1.2C56.05.4 54.5 0 52.85 0H34.45c-1.65 0-3.2.4-4.55 1.2L43.65 25z" fill="#00832D" />
          <path d="M57.4 1.2L43.65 25l13.75 23.8h27.5c4.4 0 7.3-4.8 5.1-8.6L60.7 4.5c-.8-1.4-1.95-2.5-3.3-3.3z" fill="#FFBA00" />
          <path d="M73.55 76.8H27.5l-13.75-23.8h59.8l13.75 23.8c-.8.8-1.9 1.4-3.1 1.7-.2.2-.4.4-.6.6z" fill="#2684FC" />
        </svg>
      );
    case "notion":
      return (
        <div className="flex h-6 w-6 items-center justify-center font-serif text-16 font-bold text-ink">
          N
        </div>
      );
    case "s3":
      return <HardDriveIcon className="h-6 w-6 text-[#FF9900]" />;
    case "file_system":
      return <HardDriveIcon className="h-6 w-6 text-accent" />;
    case "web_crawler":
      return <Globe02Icon className="h-6 w-6 text-brand" />;
    default:
      return <HardDriveIcon className="h-6 w-6 text-ink-secondary" />;
  }
}

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
            {getServiceIcon(connector.connector_type)}
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
