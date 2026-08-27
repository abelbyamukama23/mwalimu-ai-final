"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createLibrary,
  deleteLibrary,
  deleteLibraryResource,
  getLibrary,
  getResourceProcessingStatus,
  listLibraries,
  listLibraryResources,
  updateLibrary,
  uploadLibraryResource,
  type CreateLibraryPayload,
  type Library,
  type LibraryResource,
  type UpdateLibraryPayload,
} from "@/lib/api/libraries";

export const LIBRARIES_QUERY_KEY = ["libraries"] as const;

export function useLibraries() {
  return useQuery<Library[]>({
    queryKey: LIBRARIES_QUERY_KEY,
    queryFn: listLibraries,
  });
}

export function useLibrary(id: string | undefined) {
  return useQuery<Library>({
    queryKey: ["libraries", id],
    queryFn: () => {
      if (!id) throw new Error("Library ID is required");
      return getLibrary(id);
    },
    enabled: Boolean(id),
  });
}

export function useLibraryResources(libraryId: string | undefined) {
  return useQuery<LibraryResource[]>({
    queryKey: ["libraries", libraryId, "resources"],
    queryFn: () => {
      if (!libraryId) throw new Error("Library ID is required");
      return listLibraryResources(libraryId);
    },
    enabled: Boolean(libraryId),
  });
}

export function useCreateLibrary() {
  const queryClient = useQueryClient();
  return useMutation<Library, Error, CreateLibraryPayload>({
    mutationFn: createLibrary,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: LIBRARIES_QUERY_KEY });
    },
  });
}

export function useUpdateLibrary(id: string) {
  const queryClient = useQueryClient();
  return useMutation<Library, Error, UpdateLibraryPayload>({
    mutationFn: (payload) => updateLibrary(id, payload),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: LIBRARIES_QUERY_KEY });
      queryClient.setQueryData(["libraries", id], updated);
    },
  });
}

export function useDeleteLibrary() {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: deleteLibrary,
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: LIBRARIES_QUERY_KEY });
      queryClient.removeQueries({ queryKey: ["libraries", id] });
    },
  });
}

export function useUploadLibraryResource(libraryId: string) {
  const queryClient = useQueryClient();
  return useMutation<LibraryResource, Error, FormData>({
    mutationFn: (formData) => uploadLibraryResource(libraryId, formData),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["libraries", libraryId, "resources"],
      });
    },
  });
}

export function useDeleteLibraryResource(libraryId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (resourceId) => deleteLibraryResource(libraryId, resourceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["libraries", libraryId, "resources"],
      });
    },
  });
}

export function useResourceProcessingStatus(
  libraryId: string | undefined,
  resourceId: string | undefined,
) {
  return useQuery({
    queryKey: ["libraries", libraryId, "resources", resourceId, "status"],
    queryFn: () => {
      if (!libraryId || !resourceId) throw new Error("Missing IDs");
      return getResourceProcessingStatus(libraryId, resourceId);
    },
    enabled: Boolean(libraryId && resourceId),
    refetchInterval: (query) => {
      const data = query.state.data;
      if (data && (data.status === "ready" || data.status === "failed")) {
        return false;
      }
      return 2000;
    },
  });
}

