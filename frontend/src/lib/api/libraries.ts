/**
 * Libraries and Resources API module matching the Django + DRF Platform API:
 *   GET    /api/v1/libraries/ -> PaginatedResponse<Library>
 *   POST   /api/v1/libraries/ -> Library
 *   GET    /api/v1/libraries/{id}/ -> Library
 *   PATCH  /api/v1/libraries/{id}/ -> Library
 *   DELETE /api/v1/libraries/{id}/ -> 204
 *   GET    /api/v1/libraries/{libraryId}/resources/ -> PaginatedResponse<LibraryResource>
 */

import { apiFetch } from "@/lib/api/client";
import type { PaginatedResponse } from "./memberships";

export type LibraryVisibility = "restricted" | "discoverable";
export type LibraryStatus = "active" | "archived";
export type LibraryScopeType = "personal" | "institution";

export type LibraryInstitution = {
  id: string;
  name: string;
  slug: string;
};

export type Library = {
  id: string;
  scope_type: LibraryScopeType;
  is_personal: boolean;
  institution: LibraryInstitution | null;
  name: string;
  slug: string;
  description: string;
  status: LibraryStatus;
  visibility: LibraryVisibility;
  created_at: string;
  updated_at: string;
};

export type CreateLibraryPayload = {
  institution_id?: string | null;
  name: string;
  slug?: string;
  description?: string;
  visibility?: LibraryVisibility;
};

export type UpdateLibraryPayload = {
  name?: string;
  slug?: string;
  description?: string;
  visibility?: LibraryVisibility;
  status?: LibraryStatus;
};

export type ResourceType = "pdf" | "docx" | "text" | "link";
export type ResourceStatus = "pending" | "indexed" | "failed";

export type LibraryResource = {
  id: string;
  library: {
    id: string;
    name: string;
    slug: string;
  };
  name: string;
  resource_type: ResourceType;
  original_filename: string;
  content_type: string;
  size: number;
  object_key: string;
  checksum: string;
  status: ResourceStatus;
  created_by?: {
    id: string;
    email: string;
  };
  created_at: string;
  updated_at: string;
};

export async function listLibraries(): Promise<Library[]> {
  const response = await apiFetch<PaginatedResponse<Library> | Library[]>(
    "/api/v1/libraries/",
  );
  if (Array.isArray(response)) {
    return response;
  }
  return response.results ?? [];
}

export async function getLibrary(id: string): Promise<Library> {
  return apiFetch<Library>(`/api/v1/libraries/${id}/`);
}

export async function createLibrary(payload: CreateLibraryPayload): Promise<Library> {
  return apiFetch<Library>("/api/v1/libraries/", {
    method: "POST",
    body: payload,
  });
}

export async function updateLibrary(
  id: string,
  payload: UpdateLibraryPayload,
): Promise<Library> {
  return apiFetch<Library>(`/api/v1/libraries/${id}/`, {
    method: "PATCH",
    body: payload,
  });
}

export async function deleteLibrary(id: string): Promise<void> {
  await apiFetch(`/api/v1/libraries/${id}/`, {
    method: "DELETE",
  });
}

export async function listLibraryResources(
  libraryId: string,
): Promise<LibraryResource[]> {
  const response = await apiFetch<
    PaginatedResponse<LibraryResource> | LibraryResource[]
  >(`/api/v1/libraries/${libraryId}/resources/`);
  if (Array.isArray(response)) {
    return response;
  }
  return response.results ?? [];
}

export async function uploadLibraryResource(
  libraryId: string,
  formData: FormData,
): Promise<LibraryResource> {
  return apiFetch<LibraryResource>(`/api/v1/libraries/${libraryId}/resources/`, {
    method: "POST",
    formData,
  });
}

export async function deleteLibraryResource(
  libraryId: string,
  resourceId: string,
): Promise<void> {
  await apiFetch(`/api/v1/libraries/${libraryId}/resources/${resourceId}/`, {
    method: "DELETE",
  });
}

export type ResourceProcessingStatusResponse = {
  run_id?: string;
  resource_id: string;
  status: "queued" | "processing" | "ready" | "failed" | "NOT_ENQUEUED";
  current_stage?: string | null;
  is_active?: boolean;
  chunks_count?: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export async function getResourceProcessingStatus(
  libraryId: string,
  resourceId: string,
): Promise<ResourceProcessingStatusResponse> {
  return apiFetch<ResourceProcessingStatusResponse>(
    `/api/v1/libraries/${libraryId}/resources/${resourceId}/processing-status/`,
  );
}

export async function triggerResourceProcessing(
  libraryId: string,
  resourceId: string,
): Promise<ResourceProcessingStatusResponse> {
  return apiFetch<ResourceProcessingStatusResponse>(
    `/api/v1/libraries/${libraryId}/resources/${resourceId}/processing-status/`,
    {
      method: "POST",
    },
  );
}

