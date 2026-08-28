"use client";

import {
  Book02Icon,
  Building01Icon,
  FolderAddIcon,
  PlusSignIcon,
  Search01Icon,
} from "hugeicons-react";

import Link from "next/link";
import { useMemo, useState } from "react";
import { CreateLibraryModal } from "@/components/libraries/create-library-modal";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLibraries } from "@/lib/hooks/use-libraries";
import { useMemberships } from "@/lib/hooks/use-memberships";
import type { Library } from "@/lib/api/libraries";

export default function LibrariesPage() {
  const [createOpen, setCreateOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");

  const { data: libraries, isLoading: loadingLibraries } = useLibraries();
  const { data: memberships, isLoading: loadingMemberships } = useMemberships();

  const hasAnyMembership = (memberships ?? []).length > 0;

  // Filter libraries based on search query
  const filteredLibraries = useMemo(() => {
    const list = libraries ?? [];
    if (!searchQuery.trim()) return list;
    const query = searchQuery.toLowerCase().trim();
    return list.filter(
      (lib) =>
        lib.name.toLowerCase().includes(query) ||
        (lib.description && lib.description.toLowerCase().includes(query)) ||
        (lib.institution && lib.institution.name.toLowerCase().includes(query)),
    );
  }, [libraries, searchQuery]);

  // Tab 1: My libraries (Personal libraries owned by current user)
  const myLibraries = useMemo(() => {
    return filteredLibraries.filter(
      (lib) => lib.scope_type === "personal" || lib.is_personal,
    );
  }, [filteredLibraries]);

  // Tab 2: Institution libraries (Institutional libraries user has access to)
  const institutionLibraries = useMemo(() => {
    return filteredLibraries.filter(
      (lib) => lib.scope_type === "institution" || !lib.is_personal,
    );
  }, [filteredLibraries]);

  // Tab 3: Discover (Discoverable institutional libraries)
  const discoverLibraries = useMemo(() => {
    return filteredLibraries.filter(
      (lib) =>
        lib.visibility === "discoverable" &&
        (lib.scope_type === "institution" || !lib.is_personal),
    );
  }, [filteredLibraries]);

  const isLoading = loadingLibraries || loadingMemberships;

  return (
    <div className="h-full overflow-y-auto px-6 py-10 md:px-12">
      <div className="mx-auto max-w-[1072px]">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-22 font-semibold text-ink">Libraries</h1>
            <p className="text-13 text-ink-secondary">
              Personal knowledge spaces and institutional libraries for your teaching and learning.
            </p>
          </div>
          <Button onClick={() => setCreateOpen(true)}>
            <PlusSignIcon size={16} aria-hidden /> Create library
          </Button>
        </div>

        <div className="relative mb-6 max-w-[400px]">
          <Search01Icon
            size={16}
            aria-hidden
            className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-ink-tertiary"
          />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search libraries…"
            aria-label="Search libraries"
            className="focus-ring h-11 w-full rounded-md border border-border bg-surface pl-10 pr-3 text-14 text-ink placeholder:text-ink-tertiary"
          />
        </div>

        <Tabs defaultValue="my">
          <TabsList>
            <TabsTrigger value="my">
              My libraries ({myLibraries.length})
            </TabsTrigger>
            <TabsTrigger value="institution">
              Institution ({institutionLibraries.length})
            </TabsTrigger>
            <TabsTrigger value="discover">
              Discover ({discoverLibraries.length})
            </TabsTrigger>
          </TabsList>

          {/* Tab 1: My libraries */}
          <TabsContent value="my">
            {isLoading ? (
              <div className="py-12 text-center text-13 text-ink-tertiary">
                Loading libraries…
              </div>
            ) : myLibraries.length === 0 ? (
              <EmptyState
                icon={FolderAddIcon}
                title="No personal libraries yet"
                body={
                  searchQuery
                    ? "No personal libraries match your search."
                    : "Create a personal library to start organizing your study materials and lecture notes."
                }
              />
            ) : (
              <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2 lg:grid-cols-3">
                {myLibraries.map((lib) => (
                  <LibraryCard key={lib.id} library={lib} />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Tab 2: Institution libraries */}
          <TabsContent value="institution">
            {isLoading ? (
              <div className="py-12 text-center text-13 text-ink-tertiary">
                Loading libraries…
              </div>
            ) : !hasAnyMembership ? (
              <EmptyState
                icon={Building01Icon}
                title="No institution connected"
                body="You don't have an institution connected yet. Mwalimu can still be used independently. Institutional libraries become available after joining an institution."
              />
            ) : institutionLibraries.length === 0 ? (
              <EmptyState
                icon={Book02Icon}
                title="No institutional libraries"
                body="No libraries have been shared with you in your connected institutions yet."
              />
            ) : (
              <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2 lg:grid-cols-3">
                {institutionLibraries.map((lib) => (
                  <LibraryCard key={lib.id} library={lib} />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Tab 3: Discover */}
          <TabsContent value="discover">
            {isLoading ? (
              <div className="py-12 text-center text-13 text-ink-tertiary">
                Loading libraries…
              </div>
            ) : discoverLibraries.length === 0 ? (
              <EmptyState
                icon={Book02Icon}
                title="No discoverable libraries"
                body="Discoverable libraries published across your institution will appear here."
              />
            ) : (
              <div className="grid grid-cols-1 gap-4 pt-2 md:grid-cols-2 lg:grid-cols-3">
                {discoverLibraries.map((lib) => (
                  <LibraryCard key={lib.id} library={lib} />
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>

        <CreateLibraryModal open={createOpen} onOpenChange={setCreateOpen} />
      </div>
    </div>
  );
}

function LibraryCard({ library }: { library: Library }) {
  const isPersonal = library.scope_type === "personal" || library.is_personal;

  return (
    <Link
      href={`/libraries/${library.id}`}
      className="focus-ring group flex flex-col justify-between rounded-lg border border-border bg-surface p-5 transition-colors hover:border-ink-tertiary/50"
    >
      <div>
        <div className="flex items-start justify-between gap-2">
          <h2 className="text-15 font-semibold text-ink group-hover:text-ink-primary">
            {library.name}
          </h2>
          <Badge
            tone={
              isPersonal
                ? "neutral"
                : library.visibility === "discoverable"
                  ? "success"
                  : "neutral"
            }
            className="capitalize"
          >
            {isPersonal ? "Personal" : library.visibility}
          </Badge>
        </div>

        <p className="mt-1 text-12 text-ink-tertiary font-mono">
          {isPersonal ? "Personal Knowledge" : library.institution?.name ?? "Institution"}
        </p>

        {library.description ? (
          <p className="mt-3 line-clamp-2 text-13 text-ink-secondary">
            {library.description}
          </p>
        ) : (
          <p className="mt-3 text-13 italic text-ink-tertiary">
            No description provided.
          </p>
        )}
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-border-subtle pt-3 text-11 text-ink-tertiary">
        <span>/{library.slug}</span>
        <span>{new Date(library.created_at).toLocaleDateString()}</span>
      </div>
    </Link>
  );
}
