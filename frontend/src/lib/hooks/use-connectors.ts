"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createLibraryConnection,
  deleteLibraryConnection,
  getConnector,
  getLibraryConnection,
  listConnectionSyncJobs,
  listConnectors,
  listLibraryConnections,
  updateLibraryConnection,
  type Connection,
  type ConnectionSyncJob,
  type Connector,
  type CreateConnectionPayload,
  type UpdateConnectionPayload,
} from "@/lib/api/connectors";

export const CONNECTORS_QUERY_KEY = ["connectors"] as const;

export function useConnectors() {
  return useQuery<Connector[]>({
    queryKey: CONNECTORS_QUERY_KEY,
    queryFn: listConnectors,
  });
}

export function useConnector(id: string | undefined) {
  return useQuery<Connector>({
    queryKey: ["connectors", id],
    queryFn: () => {
      if (!id) throw new Error("Connector ID is required");
      return getConnector(id);
    },
    enabled: Boolean(id),
  });
}

export function useLibraryConnections(libraryId: string | undefined) {
  return useQuery<Connection[]>({
    queryKey: ["libraries", libraryId, "connections"],
    queryFn: () => {
      if (!libraryId) throw new Error("Library ID is required");
      return listLibraryConnections(libraryId);
    },
    enabled: Boolean(libraryId),
  });
}

export function useLibraryConnection(
  libraryId: string | undefined,
  connectionId: string | undefined,
) {
  return useQuery<Connection>({
    queryKey: ["libraries", libraryId, "connections", connectionId],
    queryFn: () => {
      if (!libraryId || !connectionId) {
        throw new Error("Library ID and Connection ID are required");
      }
      return getLibraryConnection(libraryId, connectionId);
    },
    enabled: Boolean(libraryId && connectionId),
  });
}

export function useCreateLibraryConnection(libraryId: string) {
  const queryClient = useQueryClient();
  return useMutation<Connection, Error, CreateConnectionPayload>({
    mutationFn: (payload) => createLibraryConnection(libraryId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["libraries", libraryId, "connections"],
      });
    },
  });
}

export function useUpdateLibraryConnection(
  libraryId: string,
  connectionId: string,
) {
  const queryClient = useQueryClient();
  return useMutation<Connection, Error, UpdateConnectionPayload>({
    mutationFn: (payload) =>
      updateLibraryConnection(libraryId, connectionId, payload),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({
        queryKey: ["libraries", libraryId, "connections"],
      });
      queryClient.setQueryData(
        ["libraries", libraryId, "connections", connectionId],
        updated,
      );
    },
  });
}

export function useDeleteLibraryConnection(libraryId: string) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (connectionId) =>
      deleteLibraryConnection(libraryId, connectionId),
    onSuccess: (_data, connectionId) => {
      void queryClient.invalidateQueries({
        queryKey: ["libraries", libraryId, "connections"],
      });
      queryClient.removeQueries({
        queryKey: ["libraries", libraryId, "connections", connectionId],
      });
    },
  });
}

export function useConnectionSyncJobs(
  libraryId: string | undefined,
  connectionId: string | undefined,
) {
  return useQuery<ConnectionSyncJob[]>({
    queryKey: ["libraries", libraryId, "connections", connectionId, "sync-jobs"],
    queryFn: () => {
      if (!libraryId || !connectionId) {
        throw new Error("Library ID and Connection ID are required");
      }
      return listConnectionSyncJobs(libraryId, connectionId);
    },
    enabled: Boolean(libraryId && connectionId),
  });
}

export function useTriggerConnectionSync(libraryId: string) {
  const queryClient = useQueryClient();
  return useMutation<ConnectionSyncJob, Error, string>({
    mutationFn: (connectionId) => triggerConnectionSync(libraryId, connectionId),
    onSuccess: (_data, connectionId) => {
      void queryClient.invalidateQueries({
        queryKey: ["libraries", libraryId, "connections"],
      });
      void queryClient.invalidateQueries({
        queryKey: [
          "libraries",
          libraryId,
          "connections",
          connectionId,
          "sync-jobs",
        ],
      });
    },
  });
}

