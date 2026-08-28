"use client";

import {
  ArrowDown,
  ArrowUp,
  MagnifyingGlass,
  MapPin,
  Plus,
  Trash,
} from "@phosphor-icons/react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useToast } from "@/components/ui/toast";
import {
  useAddFamiliarRegion,
  useDeleteFamiliarRegion,
  useFamiliarRegions,
  useReorderFamiliarRegions,
  useSearchGeographicUnits,
} from "@/lib/hooks/use-familiar-regions";
import type { GeographicUnit } from "@/lib/settings/types";

export function FamiliarRegionsSection() {
  const { data: regions, isLoading } = useFamiliarRegions();
  const addMutation = useAddFamiliarRegion();
  const deleteMutation = useDeleteFamiliarRegion();
  const reorderMutation = useReorderFamiliarRegions();
  const toast = useToast();

  const [search, setSearch] = useState("");
  const { data: searchResults, isLoading: searching } = useSearchGeographicUnits(search);

  const existingUnitIds = new Set((regions ?? []).map((r) => r.geographic_unit.id));

  const handleAdd = async (unit: GeographicUnit) => {
    try {
      await addMutation.mutateAsync({ geographic_unit_id: unit.id });
      toast(`Added "${unit.name}" to familiar regions`);
      setSearch("");
    } catch {
      toast("Failed to add familiar region.");
    }
  };

  const handleDelete = async (id: string, name: string) => {
    try {
      await deleteMutation.mutateAsync(id);
      toast(`Removed "${name}" from familiar regions`);
    } catch {
      toast("Failed to remove familiar region.");
    }
  };

  const handleMove = async (index: number, direction: "up" | "down") => {
    if (!regions) return;
    const targetIndex = direction === "up" ? index - 1 : index + 1;
    if (targetIndex < 0 || targetIndex >= regions.length) return;

    const newOrder = [...regions];
    const [moved] = newOrder.splice(index, 1);
    newOrder.splice(targetIndex, 0, moved);

    try {
      await reorderMutation.mutateAsync(newOrder.map((r) => r.id));
      toast("Region priority updated");
    } catch {
      toast("Failed to reorder familiar regions.");
    }
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      <div>
        <div className="flex items-center gap-2">
          <h2 className="text-22 font-semibold text-ink">Familiar Regions</h2>
          <Badge tone="info">Synced to account</Badge>
        </div>
        <p className="mt-1 text-13 text-ink-secondary">
          Places whose agricultural practices, climate, geography, and daily life you already understand.
          Mwalimu prioritizes these when generating contextual examples for you.
        </p>
      </div>

      {/* Add new region search */}
      <div className="rounded-lg border border-border bg-surface p-5 space-y-3">
        <label className="block text-13 font-semibold text-ink">
          Add a familiar county, district, or town
        </label>
        <div className="relative">
          <MagnifyingGlass
            size={16}
            className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-tertiary"
          />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Type at least 2 letters (e.g. Kirinyaga, Nakuru, Gulu)…"
            aria-label="Search geographic units"
            className="focus-ring h-10 w-full rounded-md border border-border bg-surface pl-9 pr-3 text-13 text-ink placeholder:text-ink-tertiary"
          />
        </div>

        {search.trim().length >= 2 && (
          <div className="rounded-md border border-border bg-surface-sunken divide-y divide-border-subtle max-h-48 overflow-y-auto">
            {searching ? (
              <div className="p-3 text-center text-12 text-ink-tertiary">
                Searching geographic units…
              </div>
            ) : !searchResults || searchResults.length === 0 ? (
              <div className="p-3 text-center text-12 text-ink-tertiary">
                No matching locations found.
              </div>
            ) : (
              searchResults.map((unit) => {
                const alreadyAdded = existingUnitIds.has(unit.id);
                return (
                  <div
                    key={unit.id}
                    className="flex items-center justify-between p-2.5 text-13"
                  >
                    <div>
                      <span className="font-medium text-ink">{unit.name}</span>
                      <span className="ml-2 text-11 text-ink-tertiary capitalize">
                        ({unit.unit_type} · {unit.country_code})
                      </span>
                    </div>
                    {alreadyAdded ? (
                      <Badge tone="neutral">Already added</Badge>
                    ) : (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={addMutation.isPending}
                        onClick={() => handleAdd(unit)}
                      >
                        <Plus size={14} weight="bold" /> Add
                      </Button>
                    )}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {/* List of configured familiar regions */}
      <div className="rounded-lg border border-border bg-surface p-5 space-y-3">
        <h3 className="text-13 font-semibold text-ink uppercase tracking-wide">
          Your Priority Regions ({regions?.length ?? 0})
        </h3>

        {isLoading ? (
          <div className="py-6 text-center text-13 text-ink-tertiary">
            Loading familiar regions…
          </div>
        ) : !regions || regions.length === 0 ? (
          <div className="rounded-md border border-border-subtle bg-surface-sunken p-6 text-center text-13 text-ink-tertiary">
            No familiar regions configured yet. Add your home county or town above to ground Mwalimu&apos;s explanations in your local environment.
          </div>
        ) : (
          <div className="divide-y divide-border-subtle">
            {regions.map((item, idx) => (
              <div
                key={item.id}
                className="flex items-center justify-between py-3 group"
              >
                <div className="flex items-center gap-3">
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-surface-sunken text-11 font-bold text-ink-tertiary border border-border">
                    {idx + 1}
                  </span>
                  <div>
                    <div className="flex items-center gap-2">
                      <MapPin size={16} weight="duotone" className="text-accent" />
                      <span className="text-14 font-medium text-ink">
                        {item.geographic_unit.name}
                      </span>
                    </div>
                    <span className="text-11 text-ink-tertiary capitalize">
                      {item.geographic_unit.unit_type} · {item.geographic_unit.country_code}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={idx === 0 || reorderMutation.isPending}
                    onClick={() => handleMove(idx, "up")}
                    aria-label="Move region up"
                    className="p-1 rounded text-ink-tertiary hover:text-ink disabled:opacity-30"
                  >
                    <ArrowUp size={14} weight="bold" />
                  </button>
                  <button
                    type="button"
                    disabled={idx === regions.length - 1 || reorderMutation.isPending}
                    onClick={() => handleMove(idx, "down")}
                    aria-label="Move region down"
                    className="p-1 rounded text-ink-tertiary hover:text-ink disabled:opacity-30"
                  >
                    <ArrowDown size={14} weight="bold" />
                  </button>
                  <button
                    type="button"
                    disabled={deleteMutation.isPending}
                    onClick={() => handleDelete(item.id, item.geographic_unit.name)}
                    aria-label="Remove familiar region"
                    className="p-1 ml-2 rounded text-danger/70 hover:text-danger hover:bg-danger-surface transition-colors"
                  >
                    <Trash size={15} weight="bold" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


