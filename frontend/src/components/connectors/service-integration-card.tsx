"use client";

import { useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  FolderSearch,
  Globe,
  HardDrive,
  Layers,
  Loader2,
  Lock,
  MoreVertical,
  RefreshCw,
  Trash2,
} from "lucide-react";
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
import { RemoteFilePickerDialog } from "./remote-file-picker-dialog";

type ServiceIntegrationCardProps = {
  connector: Connector;
  libraryId: string;
  existingConnection?: Connection;
  onOpenManualConfig?: (connector: Connector) => void;
};

function getServiceIcon(connectorType: string) {
  switch (connectorType) {
    case "google_drive":
      return <HardDrive className="h-6 w-6 text-[#0F9D58]" />;
    case "notion":
      return <Layers className="h-6 w-6 text-[#000000] dark:text-white" />;
    case "s3":
      return <HardDrive className="h-6 w-6 text-[#FF9900]" />;
    case "web_crawler":
      return <Globe className="h-6 w-6 text-brand" />;
    default:
      return <HardDrive className="h-6 w-6 text-ink-secondary" />;
  }
}

export function ServiceIntegrationCard({
  connector,
  libraryId,
  existingConnection,
  onOpenManualConfig,
}: ServiceIntegrationCardProps) {
  const [isAuthorizing, setIsAuthorizing] = useState(false);
  const [isPickerOpen, setIsPickerOpen] = useState(false);

  const syncMutation = useTriggerConnectionSync(libraryId);
  const deleteMutation = useDeleteLibraryConnection(libraryId);
  const toast = useToast();

  const isConnected = Boolean(existingConnection);

  const handleOAuthConnect = async () => {
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

      // Open OAuth popup window
      const width = 600;
      const height = 700;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      window.open(
        authorization_url,
        `Connect ${connector.name}`,
        `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`,
      );
      setIsAuthorizing(false);
    } catch (err: unknown) {
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
      <div className="flex flex-col justify-between rounded-lg border border-border bg-surface p-5 shadow-xs transition hover:border-border-hover">
        <div>
          {/* Header & Icon */}
          <div className="flex items-start justify-between">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-md border border-border/60 bg-surface-muted">
                {getServiceIcon(connector.connector_type)}
              </div>
              <div>
                <h3 className="text-14 font-semibold text-ink">
                  {connector.name}
                </h3>
                <span className="text-11 capitalize text-ink-tertiary">
                  {connector.auth_type === "oauth2"
                    ? "OAuth 2.0 Direct"
                    : connector.auth_type.replace("_", " ")}
                </span>
              </div>
            </div>

            {isConnected && (
              <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-11 font-medium text-success">
                <CheckCircle2 className="h-3 w-3" />
                Connected
              </span>
            )}
          </div>

          {/* Description */}
          <p className="mt-3 text-12 text-ink-secondary">
            {connector.description ||
              `Sync your ${connector.name} documents and knowledge directly into this library.`}
          </p>
        </div>

        {/* Action Buttons */}
        <div className="mt-5 border-t border-border pt-4">
          {isConnected ? (
            <div className="flex items-center justify-between gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setIsPickerOpen(true)}
                className="gap-1.5 text-12"
              >
                <FolderSearch className="h-3.5 w-3.5" />
                Browse Files
              </Button>

              <div className="flex items-center gap-1.5">
                <Button
                  variant="ghost"
                  size="sm"
                  disabled={syncMutation.isPending}
                  onClick={handleQuickSync}
                  className="h-8 gap-1 text-12 text-ink-secondary"
                  title="Run sync"
                >
                  <RefreshCw
                    className={`h-3.5 w-3.5 ${syncMutation.isPending ? "animate-spin" : ""}`}
                  />
                  Sync
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleDisconnect}
                  className="h-8 px-2 text-danger hover:bg-danger/10"
                  title="Disconnect account"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ) : (
            <div className="flex items-center justify-end gap-2">
              {connector.auth_type === "oauth2" ? (
                <Button
                  size="sm"
                  disabled={isAuthorizing}
                  onClick={handleOAuthConnect}
                  className="w-full gap-1.5"
                >
                  {isAuthorizing ? (
                    <>
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                      Connecting…
                    </>
                  ) : (
                    <>
                      <ExternalLink className="h-3.5 w-3.5" />
                      Connect {connector.name}
                    </>
                  )}
                </Button>
              ) : (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() => onOpenManualConfig?.(connector)}
                  className="w-full"
                >
                  Configure Connection
                </Button>
              )}
            </div>
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
