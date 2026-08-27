"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addFamiliarRegion,
  deleteFamiliarRegion,
  listFamiliarRegions,
  reorderFamiliarRegions,
  searchGeographicUnits,
  type AddFamiliarRegionPayload,
} from "@/lib/api/context";
import type { GeographicUnit, UserFamiliarRegion } from "@/lib/settings/types";

export const FAMILIAR_REGIONS_QUERY_KEY = ["context", "familiar-regions"] as const;

export function useFamiliarRegions() {
  return useQuery<UserFamiliarRegion[]>({
    queryKey: FAMILIAR_REGIONS_QUERY_KEY,
    queryFn: listFamiliarRegions,
    staleTime: 60_000,
  });
}

export function useSearchGeographicUnits(search: string) {
  return useQuery<GeographicUnit[]>({
    queryKey: ["context", "geographic-units", search],
    queryFn: () => searchGeographicUnits(search),
    enabled: search.trim().length >= 2,
    staleTime: 300_000,
  });
}

export function useAddFamiliarRegion() {
  const queryClient = useQueryClient();

  return useMutation<UserFamiliarRegion, Error, AddFamiliarRegionPayload>({
    mutationFn: addFamiliarRegion,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FAMILIAR_REGIONS_QUERY_KEY });
    },
  });
}

export function useDeleteFamiliarRegion() {
  const queryClient = useQueryClient();

  return useMutation<void, Error, string>({
    mutationFn: deleteFamiliarRegion,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: FAMILIAR_REGIONS_QUERY_KEY });
    },
  });
}

export function useReorderFamiliarRegions() {
  const queryClient = useQueryClient();

  return useMutation<UserFamiliarRegion[], Error, string[]>({
    mutationFn: reorderFamiliarRegions,
    onSuccess: (updated) => {
      queryClient.setQueryData(FAMILIAR_REGIONS_QUERY_KEY, updated);
    },
  });
}
