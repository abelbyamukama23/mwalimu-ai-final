"use client";

import {
  ArrowLeft,
  Building2,
  Calendar,
  FileText,
  FolderOpen,
  History,
  Key,
  Network,
  Plus,
  RefreshCw,
  Settings,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { CreateConnectionModal } from "@/components/connectors/create-connection-modal";
import { SyncJobsDialog } from "@/components/connectors/sync-jobs-dialog";
import { FolderTreeExplorer } from "@/components/libraries/folder-tree-explorer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/toast";
import {
  useDeleteLibraryConnection,
  useLibraryConnections,
  useTriggerConnectionSync,
} from "@/lib/hooks/use-connectors";

import {
  useDeleteLibrary,
  useLibrary,
  useLibraryResources,
  useUpdateLibrary,
} from "@/lib/hooks/use-libraries";
import { useMemberships } from "@/lib/hooks/use-memberships";
import type { Connection } from "@/lib/api/connectors";
import type { LibraryResource, LibraryVisibility } from "@/lib/api/libraries";

export default function LibraryDetailPage() {
  const params = useParams();
  const router = useRouter();
  const libraryId = typeof params?.id === "string" ? params.id : undefined;

  const { data: library, isLoading: loadingLibrary, error: libraryError } =
    useLibrary(libraryId);
  const { data: resources, isLoading: loadingResources } =
    useLibraryResources(libraryId);
  const { data: connections, isLoading: loadingConnections } =
    useLibraryConnections(libraryId);
  const { data: memberships } = useMemberships();

  const updateMutation = useUpdateLibrary(libraryId ?? "");
  const deleteMutation = useDeleteLibrary();
  const deleteConnectionMutation = useDeleteLibraryConnection(libraryId ?? "");
  const syncConnectionMutation = useTriggerConnectionSync(libraryId ?? "");
  const toast = useToast();

  const [createConnOpen, setCreateConnOpen] = useState(false);
  const [selectedConnForSync, setSelectedConnForSync] = useState<{
    id: string;
    name: string;
  } | null>(null);

  // Edit settings form state
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editVisibility, setEditVisibility] =
    useState<LibraryVisibility>("restricted");
  const [isEditing, setIsEditing] = useState(false);

  const isPersonal = library?.scope_type === "personal" || library?.is_personal;

  // Check if current user can manage this library:
  // Personal library: owner has manage rights.
  // Institutional library: user must be an active administrator in that institution.
  const canManage = useMemo(() => {
    if (!library) return false;
    if (library.scope_type === "personal" || library.is_personal) {
      return true;
    }
    if (!library.institution || !memberships) return false;
    return memberships.some(
      (m) =>
        m.institution.id === library.institution?.id &&
        m.role === "administrator" &&
        m.status === "active",
    );
  }, [library, memberships]);

  const handleStartEdit = () => {
    if (!library) return;
    setEditName(library.name);
    setEditDescription(library.description || "");
    setEditVisibility(library.visibility);
    setIsEditing(true);
  };

  const handleSaveSettings = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editName.trim()) return;

    try {
      await updateMutation.mutateAsync({
        name: editName.trim(),
        description: editDescription.trim() || undefined,
        visibility: editVisibility,
      });
      toast("Library updated successfully");
      setIsEditing(false);
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to update library.";
      toast(message);
    }
  };

  const handleDeleteLibrary = async () => {
    if (
      !window.confirm(
        "Are you sure you want to delete this library? This cannot be undone.",
      )
    ) {
      return;
    }

    try {
      await deleteMutation.mutateAsync(libraryId ?? "");
      toast("Library deleted successfully");
      router.push("/libraries");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to delete library.";
      toast(message);
    }
  };

  const handleDeleteConnection = async (conn: Connection) => {
    if (
      !window.confirm(
        `Are you sure you want to delete the connection "${conn.name}"?`,
      )
    ) {
      return;
    }

    try {
      await deleteConnectionMutation.mutateAsync(conn.id);
      toast("Connection deleted successfully");
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to delete connection.";
      toast(message);
    }
  };

  const handleTriggerSync = async (conn: Connection) => {
    try {
      await syncConnectionMutation.mutateAsync(conn.id);
      toast(`Sync job queued for "${conn.name}"`);
      setSelectedConnForSync({ id: conn.id, name: conn.name });
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Failed to trigger sync.";
      toast(message);
    }
  };

  if (loadingLibrary) {
    return (
      <div className="flex h-full items-center justify-center text-14 text-ink-tertiary">
        Loading library details…
      </div>
    );
  }

  if (libraryError || !library) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3">
        <EmptyState
          icon={FolderOpen}
          title="Library not found"
          body="This library does not exist or you do not have permission to view it."
          action={
            <Link href="/libraries">
              <Button variant="secondary">
                <ArrowLeft size={16} aria-hidden /> Back to libraries
              </Button>
            </Link>
          }
        />
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto px-6 py-8 md:px-12">
      <div className="mx-auto max-w-[1072px] space-y-6">
        {/* Back Link */}
        <Link
          href="/libraries"
          className="focus-ring inline-flex items-center gap-1.5 rounded text-12 font-medium text-ink-tertiary hover:text-ink"
        >
          <ArrowLeft size={14} aria-hidden /> Back to libraries
        </Link>

        {/* Library Header */}
        <div className="flex flex-col justify-between gap-4 rounded-lg border border-border bg-surface p-6 sm:flex-row sm:items-center">
          <div>
            <div className="flex items-center gap-2.5">
              <h1 className="text-22 font-semibold text-ink">{library.name}</h1>
              <Badge
                tone={
                  isPersonal
                    ? "neutral"
                    : library.visibility === "discoverable"
                      ? "success"
                      : "neutral"
                }
              >
                {isPersonal ? "Personal" : library.visibility}
              </Badge>
              <Badge tone="neutral">{library.status}</Badge>
            </div>
            <p className="mt-1.5 text-13 text-ink-secondary">
              {library.description || "No description provided."}
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-4 text-12 text-ink-tertiary">
              <span className="flex items-center gap-1 font-medium">
                <Building2 size={13} aria-hidden />
                {isPersonal
                  ? "Personal Knowledge Space"
                  : (library.institution?.name ?? "Institution")}
              </span>
              <span className="flex items-center gap-1">
                <Calendar size={13} aria-hidden />
                Created {new Date(library.created_at).toLocaleDateString()}
              </span>
              <span className="font-mono text-11">slug: {library.slug}</span>
            </div>
          </div>

          {canManage && (
            <div className="flex items-center gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setCreateConnOpen(true)}
              >
                <Plus size={14} aria-hidden /> Add connection
              </Button>
            </div>
          )}
        </div>

        {/* Library Content Tabs */}
        <Tabs defaultValue="resources">
          <TabsList>
            <TabsTrigger value="resources">
              <FileText size={14} aria-hidden className="mr-1.5" />
              Resources ({(resources ?? []).length})
            </TabsTrigger>
            <TabsTrigger value="connections">
              <Network size={14} aria-hidden className="mr-1.5" />
              Connections ({(connections ?? []).length})
            </TabsTrigger>
            {canManage && (
              <TabsTrigger value="settings">
                <Settings size={14} aria-hidden className="mr-1.5" />
                Settings
              </TabsTrigger>
            )}
          </TabsList>

          {/* Tab: Resources (GitHub-style folder explorer and resource cards) */}
          <TabsContent value="resources">
            {loadingResources ? (
              <div className="py-12 text-center text-13 text-ink-tertiary">
                Loading resources…
              </div>
            ) : (
              <FolderTreeExplorer
                libraryId={libraryId ?? ""}
                resources={resources ?? []}
                canManage={canManage}
              />
            )}
          </TabsContent>

          {/* Tab: Connections */}
          <TabsContent value="connections">
            {loadingConnections ? (
              <div className="py-12 text-center text-13 text-ink-tertiary">
                Loading connections…
              </div>
            ) : !connections || connections.length === 0 ? (
              <EmptyState
                icon={Network}
                title="No knowledge connections"
                body="Connect external data sources like web crawlers, object stores, and custom sources to synchronize documents with this library."
                action={
                  canManage ? (
                    <Button
                      variant="secondary"
                      onClick={() => setCreateConnOpen(true)}
                    >
                      <Plus size={14} aria-hidden /> Add connection
                    </Button>
                  ) : undefined
                }
              />
            ) : (
              <div className="space-y-3 pt-2">
                {connections.map((conn) => (
                  <div
                    key={conn.id}
                    className="flex flex-col justify-between gap-4 rounded-lg border border-border bg-surface p-4 sm:flex-row sm:items-center"
                  >
                    <div>
                      <div className="flex items-center gap-2.5">
                        <h4 className="text-14 font-semibold text-ink">
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
                        <span className="text-11 text-ink-tertiary">
                          {conn.connector.name}
                        </span>
                      </div>
                      <div className="mt-2 flex flex-wrap items-center gap-3 text-12 text-ink-tertiary">
                        <span>Sync: {conn.sync_frequency}</span>
                        <span>•</span>
                        <span className="flex items-center gap-1">
                          <Key size={12} aria-hidden />
                          Credentials:{" "}
                          {conn.has_credentials ? "Configured" : "None"}
                        </span>
                        {conn.last_synced_at && (
                          <>
                            <span>•</span>
                            <span>
                              Last sync:{" "}
                              {new Date(conn.last_synced_at).toLocaleString()} (
                              {conn.last_sync_status})
                            </span>
                          </>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-2">
                      {canManage && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleTriggerSync(conn)}
                          disabled={
                            syncConnectionMutation.isPending ||
                            conn.status === "syncing"
                          }
                          title="Sync external knowledge now"
                        >
                          <RefreshCw
                            size={14}
                            className={
                              conn.status === "syncing"
                                ? "animate-spin"
                                : ""
                            }
                            aria-hidden
                          />{" "}
                          Sync
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() =>
                          setSelectedConnForSync({
                            id: conn.id,
                            name: conn.name,
                          })
                        }
                      >
                        <History size={14} aria-hidden /> History
                      </Button>
                      {canManage && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDeleteConnection(conn)}
                          className="text-danger hover:bg-danger-surface"
                        >
                          <Trash2 size={14} aria-hidden />
                        </Button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Tab: Settings */}
          {canManage && (
            <TabsContent value="settings">
              <div className="max-w-xl rounded-lg border border-border bg-surface p-6">
                <h3 className="text-16 font-semibold text-ink">
                  Library Settings
                </h3>
                <p className="mt-1 text-12 text-ink-tertiary">
                  Manage metadata, visibility, and lifecycle for this library.
                </p>

                <form onSubmit={handleSaveSettings} className="mt-6 space-y-4">
                  <div className="space-y-1.5">
                    <label className="text-12 font-medium text-ink">
                      Library Name
                    </label>
                    <Input
                      value={isEditing ? editName : library.name}
                      onChange={(e) => setEditName(e.target.value)}
                      onFocus={() => {
                        if (!isEditing) handleStartEdit();
                      }}
                      required
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-12 font-medium text-ink">
                      Description
                    </label>
                    <Textarea
                      rows={3}
                      value={isEditing ? editDescription : library.description}
                      onChange={(e) => setEditDescription(e.target.value)}
                      onFocus={() => {
                        if (!isEditing) handleStartEdit();
                      }}
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="text-12 font-medium text-ink">
                      Visibility
                    </label>
                    <select
                      value={isEditing ? editVisibility : library.visibility}
                      onChange={(e) => {
                        if (!isEditing) handleStartEdit();
                        setEditVisibility(e.target.value as LibraryVisibility);
                      }}
                      className="focus-ring h-10 w-full rounded-md border border-border bg-surface px-3 text-13 text-ink"
                    >
                      <option value="restricted">
                        Restricted (Explicit access grants only)
                      </option>
                      <option value="discoverable">
                        Discoverable (All institution members)
                      </option>
                    </select>
                  </div>

                  <div className="flex justify-end gap-2.5 pt-4">
                    {isEditing && (
                      <Button
                        type="button"
                        variant="ghost"
                        onClick={() => setIsEditing(false)}
                      >
                        Cancel
                      </Button>
                    )}
                    <Button
                      type="submit"
                      disabled={!isEditing || updateMutation.isPending}
                    >
                      {updateMutation.isPending ? "Saving…" : "Save Changes"}
                    </Button>
                  </div>
                </form>

                <div className="mt-8 border-t border-border pt-6">
                  <h4 className="text-14 font-semibold text-danger">
                    Danger Zone
                  </h4>
                  <p className="mt-1 text-12 text-ink-tertiary">
                    Permanently delete this library, all associated access
                    policies, and external connections.
                  </p>
                  <Button
                    variant="secondary"
                    size="sm"
                    className="mt-3 border-danger/30 text-danger hover:bg-danger-surface"
                    onClick={handleDeleteLibrary}
                    disabled={deleteMutation.isPending}
                  >
                    <Trash2 size={14} aria-hidden /> Delete Library
                  </Button>
                </div>
              </div>
            </TabsContent>
          )}
        </Tabs>
      </div>

      {/* Connection Modal */}
      {libraryId && (
        <CreateConnectionModal
          libraryId={libraryId}
          open={createConnOpen}
          onOpenChange={setCreateConnOpen}
        />
      )}

      {/* Sync Jobs Dialog */}
      {libraryId && (
        <SyncJobsDialog
          libraryId={libraryId}
          connectionId={selectedConnForSync?.id ?? null}
          connectionName={selectedConnForSync?.name}
          open={Boolean(selectedConnForSync)}
          onOpenChange={(open) => {
            if (!open) setSelectedConnForSync(null);
          }}
        />
      )}
    </div>
  );
}

