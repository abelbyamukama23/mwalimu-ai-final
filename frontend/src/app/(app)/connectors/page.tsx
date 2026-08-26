"use client";

import { Cloud, FileCode, Globe, HardDrive, Link2, Server } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/ui/empty-state";
import { useConnectors } from "@/lib/hooks/use-connectors";
import type { ConnectorType } from "@/lib/api/connectors";

export default function ConnectorsPage() {
  const { data: connectors, isLoading } = useConnectors();

  const getConnectorIcon = (type: ConnectorType) => {
    switch (type) {
      case "web_crawler":
        return Globe;
      case "google_drive":
        return Cloud;
      case "notion":
        return FileCode;
      case "s3":
        return HardDrive;
      case "file_system":
        return Server;
      default:
        return Link2;
    }
  };

  return (
    <div className="h-full overflow-y-auto px-6 py-10 md:px-12">
      <div className="mx-auto max-w-[1072px]">
        <div className="mb-2 flex items-center justify-between">
          <div>
            <h1 className="text-22 font-semibold text-ink">Connectors</h1>
            <p className="text-13 text-ink-secondary">
              Platform catalog of external knowledge and data source
              integrations.
            </p>
          </div>
        </div>

        <p className="mb-8 max-w-2xl text-13 text-ink-tertiary">
          Connectors define how Mwalimu reaches external systems. Authorized
          library administrators can link these connectors to individual
          libraries as knowledge connections.
        </p>

        {isLoading ? (
          <div className="py-16 text-center text-13 text-ink-tertiary">
            Loading connector catalog…
          </div>
        ) : !connectors || connectors.length === 0 ? (
          <EmptyState
            icon={Link2}
            title="No connectors available"
            body="No active platform connectors are currently configured on the Platform API."
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
            {connectors.map((connector) => {
              const Icon = getConnectorIcon(connector.connector_type);
              const configPropsCount = Object.keys(
                connector.config_schema?.properties ?? {},
              ).length;
              const authPropsCount = Object.keys(
                connector.auth_schema?.properties ?? {},
              ).length;

              return (
                <div
                  key={connector.id}
                  className="flex flex-col justify-between rounded-lg border border-border bg-surface p-5"
                >
                  <div>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5">
                        <div className="flex h-8 w-8 items-center justify-center rounded-md bg-surface-sunken text-ink">
                          <Icon size={18} aria-hidden />
                        </div>
                        <div>
                          <h3 className="text-14 font-semibold text-ink">
                            {connector.name}
                          </h3>
                          <span className="text-11 font-mono text-ink-tertiary">
                            {connector.connector_type}
                          </span>
                        </div>
                      </div>
                      <Badge
                        tone={connector.is_active ? "success" : "neutral"}
                      >
                        {connector.is_active ? "Active" : "Inactive"}
                      </Badge>
                    </div>

                    <p className="mt-3 line-clamp-2 text-12 text-ink-secondary">
                      {connector.description || "No description provided."}
                    </p>
                  </div>

                  <div className="mt-5 border-t border-border pt-3 space-y-1.5 text-11 text-ink-tertiary">
                    <div className="flex items-center justify-between">
                      <span>Auth Type:</span>
                      <span className="font-medium text-ink capitalize">
                        {connector.auth_type.replace(/_/g, " ")}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Config Fields:</span>
                      <span className="font-medium text-ink">
                        {configPropsCount} parameter
                        {configPropsCount === 1 ? "" : "s"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span>Auth Credentials:</span>
                      <span className="font-medium text-ink">
                        {authPropsCount > 0
                          ? `${authPropsCount} required key${authPropsCount === 1 ? "" : "s"}`
                          : "None"}
                      </span>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
