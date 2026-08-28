"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowRight01Icon,
  Book02Icon,
  HardDriveIcon,
  Search01Icon,
} from "hugeicons-react";

import { Input } from "@/components/ui/input";
import { useConnectors } from "@/lib/hooks/use-connectors";
import { useLibraries } from "@/lib/hooks/use-libraries";
import { useLibraryConnections } from "@/lib/hooks/use-connectors";
import { ServiceIntegrationCard } from "@/components/connectors/service-integration-card";

export default function ConnectionsPage() {
  const { data: connectors, isLoading: loadingConnectors } = useConnectors();
  const { data: libraries, isLoading: loadingLibraries } = useLibraries();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedLibraryId, setSelectedLibraryId] = useState<string | null>(null);

  // Default to the first library if none selected
  const activeLibrary =
    libraries?.find((l) => l.id === selectedLibraryId) ?? libraries?.[0] ?? null;
  const currentLibraryId = activeLibrary?.id ?? "";

  const { data: connections, isLoading: loadingConnections } =
    useLibraryConnections(currentLibraryId || undefined);

  // Filter connectors based on search
  const filteredConnectors = useMemo(() => {
    if (!connectors) return [];
    return connectors.filter((c) => {
      if (!c.is_active) return false;
      const q = searchQuery.toLowerCase().trim();
      if (!q) return true;
      return (
        c.name.toLowerCase().includes(q) ||
        c.description?.toLowerCase().includes(q) ||
        c.connector_type.toLowerCase().includes(q)
      );
    });
  }, [connectors, searchQuery]);

  // Group into Academic Categories
  const cloudDrives = filteredConnectors.filter(
    (c) => c.connector_type === "google_drive" || c.connector_type === "notion",
  );
  const localAndStorage = filteredConnectors.filter(
    (c) => c.connector_type !== "google_drive" && c.connector_type !== "notion",
  );

  return (
    <div className="h-full overflow-y-auto px-6 py-8 md:px-12">
      <div className="mx-auto max-w-[980px] space-y-8">
        {/* Top Header & Search Bar */}
        <div className="flex flex-col justify-between gap-4 border-b border-border pb-6 sm:flex-row sm:items-end">
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-accent/10 px-2.5 py-0.5 text-11 font-medium text-accent">
                Personal Academic Workspaces
              </span>
            </div>
            <h1 className="mt-1 text-26 font-bold tracking-tight text-ink">
              Connections
            </h1>
            <p className="mt-1 max-w-xl text-13 text-ink-secondary">
              Discover and link personal study drives, class lecture notebooks, and course document databases to ground AI tutors in your learning materials.
            </p>
          </div>

          {/* Search Input */}
          <div className="relative w-full sm:w-64">
            <Search01Icon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-tertiary" />
            <Input
              type="search"
              placeholder="Search connections…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="h-9 pl-9 text-13"
            />
          </div>
        </div>

        {/* Top App Icons Strip (ChatGPT-style) */}
        <div className="flex items-center gap-3 overflow-x-auto rounded-xl border border-border/60 bg-surface p-3 shadow-2xs">
          <span className="text-11 font-medium text-ink-tertiary px-2 shrink-0">
            Available Workspaces:
          </span>
          <div className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-border/60 bg-surface-muted p-1.5" title="Google Drive">
              <svg className="h-full w-full" viewBox="0 0 87.3 78" fill="none">
                <path d="M6.6 66.85l3.85 6.65c.8 1.4 1.95 2.5 3.3 3.3l13.75-23.8H6.6c-4.4 0-7.3 4.4-4.8 8.2z" fill="#0066DA" />
                <path d="M43.65 25L29.9 1.2c-1.35.8-2.5 1.9-3.3 3.3L1.8 45.7c-2.2 3.8.7 8.6 5.1 8.6h27.5L43.65 25z" fill="#00AC47" />
                <path d="M73.55 76.8c1.35-.8 2.5-1.9 3.3-3.3l1.6-2.8c2.2-3.8-.7-8.6-5.1-8.6H43.65l13.75 23.8c4.35 0 7.35-4.35 16.15-9.1z" fill="#EA4335" />
                <path d="M43.65 25L57.4 1.2C56.05.4 54.5 0 52.85 0H34.45c-1.65 0-3.2.4-4.55 1.2L43.65 25z" fill="#00832D" />
                <path d="M57.4 1.2L43.65 25l13.75 23.8h27.5c4.4 0 7.3-4.8 5.1-8.6L60.7 4.5c-.8-1.4-1.95-2.5-3.3-3.3z" fill="#FFBA00" />
                <path d="M73.55 76.8H27.5l-13.75-23.8h59.8l13.75 23.8c-.8.8-1.9 1.4-3.1 1.7-.2.2-.4.4-.6.6z" fill="#2684FC" />
              </svg>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-border/60 bg-surface-muted font-serif text-14 font-bold text-ink" title="Notion">
              N
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-border/60 bg-surface-muted text-[#FF9900]" title="Amazon S3">
              <HardDriveIcon size={16} />
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-lg border border-border/60 bg-surface-muted text-accent" title="Local Academic Storage">
              <HardDriveIcon size={16} />
            </div>
          </div>
        </div>

        {/* Library Context Selector */}
        {loadingLibraries ? (
          <div className="py-8 text-center text-13 text-ink-tertiary">
            Loading your study libraries…
          </div>
        ) : !libraries || libraries.length === 0 ? (
          <div className="rounded-xl border border-border bg-surface p-8 text-center">
            <Book02Icon className="mx-auto h-10 w-10 text-ink-tertiary" />
            <h3 className="mt-3 text-15 font-semibold text-ink">
              Create a study library first
            </h3>
            <p className="mx-auto mt-1 max-w-md text-13 text-ink-secondary">
              Connections synchronize course documents and lecture notes directly into a library. Create your first library to get started.
            </p>
            <div className="mt-5">
              <Link
                href="/libraries"
                className="inline-flex h-9 items-center justify-center rounded-lg bg-accent px-4 py-2 text-13 font-medium text-white shadow-xs hover:bg-accent-hover"
              >
                Go to Libraries
              </Link>
            </div>
          </div>
        ) : (
          <div className="space-y-8">
            {/* Target Library Pills */}
            <div className="flex items-center justify-between">
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
                      <Book02Icon size={14} aria-hidden />
                      {lib.name}
                    </button>
                  );
                })}
              </div>

              <Link
                href={`/libraries/${currentLibraryId}`}
                className="focus-ring inline-flex items-center gap-1 text-12 font-medium text-accent hover:underline"
              >
                View library files <ArrowRight01Icon size={12} />
              </Link>
            </div>

            {/* Category 1: Cloud Study Drives & Notes */}
            {cloudDrives.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-13 font-semibold uppercase tracking-wider text-ink-tertiary">
                    Cloud Study Drives & Notes
                  </h3>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {cloudDrives.map((connector) => {
                    const existing = (connections ?? []).find(
                      (conn) => conn.connector.id === connector.id,
                    );
                    return (
                      <ServiceIntegrationCard
                        key={connector.id}
                        connector={connector}
                        libraryId={currentLibraryId}
                        existingConnection={existing}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            {/* Category 2: Local & Academic Storage */}
            {localAndStorage.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-13 font-semibold uppercase tracking-wider text-ink-tertiary">
                    Local & Academic Storage
                  </h3>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {localAndStorage.map((connector) => {
                    const existing = (connections ?? []).find(
                      (conn) => conn.connector.id === connector.id,
                    );
                    return (
                      <ServiceIntegrationCard
                        key={connector.id}
                        connector={connector}
                        libraryId={currentLibraryId}
                        existingConnection={existing}
                      />
                    );
                  })}
                </div>
              </div>
            )}

            {filteredConnectors.length === 0 && (
              <div className="py-12 text-center text-13 text-ink-tertiary">
                No connections matched &ldquo;{searchQuery}&rdquo;.
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
