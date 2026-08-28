"use client";

import { useState } from "react";
import Link from "next/link";
import {
  FolderSync,
  Plus,
  ArrowRight,
  BookOpen,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { useConnectors } from "@/lib/hooks/use-connectors";
import { useLibraries } from "@/lib/hooks/use-libraries";
import { ServiceIntegrationCard } from "@/components/connectors/service-integration-card";
import { CreateConnectionModal } from "@/components/connectors/create-connection-modal";
import { useLibraryConnections } from "@/lib/hooks/use-connectors";

export default function ConnectionsPage() {
  const { data: connectors, isLoading: loadingConnectors } = useConnectors();
  const { data: libraries, isLoading: loadingLibraries } = useLibraries();

  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(null);
  const [createModalOpen, setCreateModalOpen] = useState(false);

  // Default to the first library if none selected
  const activeLibrary =
    libraries?.find((l) => l.id === selectedLibraryId) ?? libraries?.[0] ?? null;
  const currentLibraryId = activeLibrary?.id ?? "";

  const { data: connections, isLoading: loadingConnections } =
    useLibraryConnections(currentLibraryId || undefined);

  return (
    <div className="h-full overflow-y-auto px-6 py-10 md:px-12">
      <div className="mx-auto max-w-[1072px] space-y-8">
        {/* Header */}
        <div className="flex flex-col justify-between gap-4 border-b border-border pb-6 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-accent/10 px-2 py-0.5 text-11 font-semibold text-accent">
                Academic Integrations
              </span>
            </div>
            <h1 className="mt-1 text-24 font-bold text-ink">Connections</h1>
            <p className="mt-1 text-13 text-ink-secondary">
              Link your personal cloud study drives, class lecture notebooks, and course document databases to ground AI tutors in your learning materials.
            </p>
          </div>

          {activeLibrary && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setCreateModalOpen(true)}
              className="self-start sm:self-auto"
            >
              <Plus size={14} aria-hidden className="mr-1" /> Add Custom Connection
            </Button>
          )}
        </div>

        {/* Library Context Selector */}
        {loadingLibraries ? (
          <div className="py-8 text-center text-13 text-ink-tertiary">
            Loading your study libraries…
          </div>
        ) : !libraries || libraries.length === 0 ? (
          <div className="rounded-lg border border-border bg-surface p-8 text-center">
            <BookOpen className="mx-auto h-10 w-10 text-ink-tertiary" />
            <h3 className="mt-3 text-15 font-semibold text-ink">
              Create a study library first
            </h3>
            <p className="mx-auto mt-1 max-w-md text-13 text-ink-secondary">
              Connections synchronize course documents and lecture notes directly into a library. Create your first library to get started.
            </p>
            <div className="mt-5">
              <Link
                href="/libraries"
                className="inline-flex h-9 items-center justify-center rounded-md bg-accent px-4 py-2 text-13 font-medium text-white shadow-xs hover:bg-accent-hover"
              >
                Go to Libraries
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Library Selector Tabs */}
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-12 font-medium text-ink-secondary">
                Target Library:
              </span>
              {libraries.map((lib) => {
                const isSelected = lib.id === (activeLibrary?.id ?? "");
                return (
                  <button
                    key={lib.id}
                    onClick={() => setSelectedLibraryId(lib.id)}
                    className={`focus-ring inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-12 font-medium transition-colors ${
                      isSelected
                        ? "bg-accent text-white"
                        : "bg-surface border border-border text-ink-secondary hover:bg-subtle hover:text-ink"
                    }`}
                  >
                    <BookOpen size={12} aria-hidden />
                    {lib.name}
                  </button>
                );
              })}
            </div>

            {/* Academic Workspaces Grid */}
            <div className="space-y-4">
              <div>
                <h3 className="text-15 font-semibold text-ink">
                  Personal Academic Workspaces
                </h3>
                <p className="text-12 text-ink-secondary">
                  Connect your student or educator accounts to automatically sync lecture slides, PDFs, and notes into <strong>{activeLibrary?.name}</strong>.
                </p>
              </div>

              {loadingConnectors || loadingConnections ? (
                <div className="py-12 text-center text-13 text-ink-tertiary">
                  Loading available workspace connections…
                </div>
              ) : (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                  {(connectors ?? [])
                    .filter((c) => c.is_active)
                    .map((connector) => {
                      const existing = (connections ?? []).find(
                        (conn) => conn.connector.id === connector.id,
                      );
                      return (
                        <ServiceIntegrationCard
                          key={connector.id}
                          connector={connector}
                          libraryId={currentLibraryId}
                          existingConnection={existing}
                          onOpenManualConfig={() => setCreateModalOpen(true)}
                        />
                      );
                    })}
                </div>
              )}
            </div>

            {/* Active Connections Summary */}
            {connections && connections.length > 0 && (
              <div className="border-t border-border pt-6">
                <div className="mb-3 flex items-center justify-between">
                  <h3 className="text-14 font-semibold text-ink">
                    Active Sync Links in {activeLibrary?.name} ({connections.length})
                  </h3>
                  <Link
                    href={`/libraries/${currentLibraryId}`}
                    className="focus-ring inline-flex items-center gap-1 text-12 font-medium text-accent hover:underline"
                  >
                    View library resources <ArrowRight size={12} />
                  </Link>
                </div>

                <div className="space-y-3">
                  {connections.map((conn) => (
                    <div
                      key={conn.id}
                      className="flex flex-col justify-between gap-3 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center"
                    >
                      <div className="flex items-center gap-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-md border border-border/60 bg-surface-muted text-ink">
                          <FolderSync size={18} />
                        </div>
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="text-13 font-semibold text-ink">
                              {conn.name}
                            </h4>
                            <Badge
                              tone={
                                conn.status === "active"
                                  ? "success"
                                  : conn.status === "error"
                                    ? "warning"
                                    : "neutral"
                              }
                            >
                              {conn.status}
                            </Badge>
                          </div>
                          <p className="text-11 text-ink-tertiary">
                            Connector: {conn.connector.name} • Frequency:{" "}
                            {conn.sync_frequency}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2">
                        <Link
                          href={`/libraries/${currentLibraryId}`}
                          className="inline-flex h-8 items-center justify-center rounded-md border border-border bg-surface px-3 text-12 font-medium text-ink hover:bg-subtle"
                        >
                          Manage in Library
                        </Link>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Manual Config Modal */}
        {activeLibrary && (
          <CreateConnectionModal
            open={createModalOpen}
            onOpenChange={setCreateModalOpen}
            libraryId={currentLibraryId}
          />
        )}
      </div>
    </div>
  );
}
