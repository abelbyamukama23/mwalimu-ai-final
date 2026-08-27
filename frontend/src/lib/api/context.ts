/**
 * Context & Geographic Units API client module matching Django DRF Platform API:
 *   GET    /api/v1/context/familiar-regions/ -> UserFamiliarRegion[]
 *   POST   /api/v1/context/familiar-regions/ -> UserFamiliarRegion
 *   DELETE /api/v1/context/familiar-regions/{id}/ -> 204
 *   PUT    /api/v1/context/familiar-regions/reorder/ -> UserFamiliarRegion[]
 *   GET    /api/v1/context/geographic-units/?search=... -> PaginatedResponse<GeographicUnit>
 */

import { apiFetch } from "@/lib/api/client";
import type { PaginatedResponse } from "@/lib/api/memberships";
import type { GeographicUnit, UserFamiliarRegion } from "@/lib/settings/types";

export type AddFamiliarRegionPayload = {
  geographic_unit_id: string;
  priority?: number;
};

export async function listFamiliarRegions(): Promise<UserFamiliarRegion[]> {
  const res = await apiFetch<PaginatedResponse<UserFamiliarRegion> | UserFamiliarRegion[]>(
    "/api/v1/context/familiar-regions/",
  );
  if (Array.isArray(res)) return res;
  return res.results ?? [];
}

export async function addFamiliarRegion(
  payload: AddFamiliarRegionPayload,
): Promise<UserFamiliarRegion> {
  return apiFetch<UserFamiliarRegion>("/api/v1/context/familiar-regions/", {
    method: "POST",
    body: payload,
  });
}

export async function deleteFamiliarRegion(id: string): Promise<void> {
  return apiFetch<void>(`/api/v1/context/familiar-regions/${id}/`, {
    method: "DELETE",
  });
}

export async function reorderFamiliarRegions(
  regionIds: string[],
): Promise<UserFamiliarRegion[]> {
  return apiFetch<UserFamiliarRegion[]>("/api/v1/context/familiar-regions/reorder/", {
    method: "PUT",
    body: { region_ids: regionIds },
  });
}

export async function searchGeographicUnits(
  search: string,
): Promise<GeographicUnit[]> {
  const query = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : "";
  const res = await apiFetch<PaginatedResponse<GeographicUnit> | GeographicUnit[]>(
    `/api/v1/context/geographic-units/${query}`,
  );
  if (Array.isArray(res)) return res;
  return res.results ?? [];
}
