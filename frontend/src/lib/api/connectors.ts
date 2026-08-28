/**
 * Connectors, Library Connections, and Sync Jobs API module matching the
 * Django + DRF Platform API:
 *   GET    /api/v1/connectors/ -> Connector[]
 *   GET    /api/v1/connectors/{id}/ -> Connector
 *   GET    /api/v1/libraries/{libraryId}/connections/ -> Connection[]
 *   POST   /api/v1/libraries/{libraryId}/connections/ -> Connection
 *   GET    /api/v1/libraries/{libraryId}/connections/{connectionId}/ -> Connection
 *   PATCH  /api/v1/libraries/{libraryId}/connections/{connectionId}/ -> Connection
 *   DELETE /api/v1/libraries/{libraryId}/connections/{connectionId}/ -> 204
 *   GET    /api/v1/libraries/{libraryId}/connections/{connectionId}/sync-jobs/ -> ConnectionSyncJob[]
 */

import { apiFetch } from "@/lib/api/client";

export type ConnectorType =
  | "web_crawler"
  | "google_drive"
  | "notion"
  | "s3"
  | "file_system"
  | "custom";

export type ConnectorAuthType =
  | "none"
  | "api_key"
  | "oauth2"
  | "basic_auth"
  | "bearer_token";

export type JSONSchemaProperty = {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  minimum?: number;
  maximum?: number;
  minLength?: number;
  maxLength?: number;
  format?: string;
  enum?: string[];
  writeOnly?: boolean;
};

export type JSONSchema = {
  type?: string;
  title?: string;
  description?: string;
  properties?: Record<string, JSONSchemaProperty>;
  required?: string[];
  [key: string]: unknown;
};

export type Connector = {
  id: string;
  name: string;
  slug: string;
  description: string;
  connector_type: ConnectorType;
  auth_type: ConnectorAuthType;
  config_schema: JSONSchema;
  auth_schema: JSONSchema;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ConnectorSummary = {
  id: string;
  name: string;
  slug: string;
  connector_type: ConnectorType;
  auth_type: ConnectorAuthType;
};

export type ConnectionStatus = "active" | "inactive" | "error" | "syncing";
export type SyncFrequency = "manual" | "hourly" | "daily" | "weekly";
export type SyncStatus = "success" | "partial" | "failed";

export type Connection = {
  id: string;
  library_id: string;
  connector: ConnectorSummary | Connector;
  name: string;
  status: ConnectionStatus;
  configuration?: Record<string, unknown>;
  sync_frequency: SyncFrequency;
  last_synced_at: string | null;
  last_sync_status: SyncStatus | null;
  last_sync_error: string;
  has_credentials: boolean;
  created_by_id?: string | null;
  created_at: string;
  updated_at: string;
};

export type CreateConnectionPayload = {
  connector_id: string;
  name: string;
  configuration?: Record<string, unknown>;
  credentials?: Record<string, unknown>;
  sync_frequency?: SyncFrequency;
  status?: ConnectionStatus;
};

export type UpdateConnectionPayload = {
  name?: string;
  configuration?: Record<string, unknown>;
  credentials?: Record<string, unknown>;
  sync_frequency?: SyncFrequency;
  status?: ConnectionStatus;
};

export type SyncJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type ConnectionSyncJob = {
  id: string;
  connection_id: string;
  status: SyncJobStatus;
  celery_task_id: string | null;
  resources_discovered: number;
  resources_created: number;
  resources_updated: number;
  resources_deleted: number;
  error_code: string | null;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export async function listConnectors(): Promise<Connector[]> {
  return apiFetch<Connector[]>("/api/v1/connectors/");
}

export async function getConnector(id: string): Promise<Connector> {
  return apiFetch<Connector>(`/api/v1/connectors/${id}/`);
}

export async function listLibraryConnections(
  libraryId: string,
): Promise<Connection[]> {
  return apiFetch<Connection[]>(`/api/v1/libraries/${libraryId}/connections/`);
}

export async function createLibraryConnection(
  libraryId: string,
  payload: CreateConnectionPayload,
): Promise<Connection> {
  return apiFetch<Connection>(`/api/v1/libraries/${libraryId}/connections/`, {
    method: "POST",
    body: payload,
  });
}

export async function getLibraryConnection(
  libraryId: string,
  connectionId: string,
): Promise<Connection> {
  return apiFetch<Connection>(
    `/api/v1/libraries/${libraryId}/connections/${connectionId}/`,
  );
}

export async function updateLibraryConnection(
  libraryId: string,
  connectionId: string,
  payload: UpdateConnectionPayload,
): Promise<Connection> {
  return apiFetch<Connection>(
    `/api/v1/libraries/${libraryId}/connections/${connectionId}/`,
    {
      method: "PATCH",
      body: payload,
    },
  );
}

export async function deleteLibraryConnection(
  libraryId: string,
  connectionId: string,
): Promise<void> {
  await apiFetch(
    `/api/v1/libraries/${libraryId}/connections/${connectionId}/`,
    {
      method: "DELETE",
    },
  );
}

export async function listConnectionSyncJobs(
  libraryId: string,
  connectionId: string,
): Promise<ConnectionSyncJob[]> {
  return apiFetch<ConnectionSyncJob[]>(
    `/api/v1/libraries/${libraryId}/connections/${connectionId}/sync-jobs/`,
  );
}

export async function triggerConnectionSync(
  libraryId: string,
  connectionId: string,
): Promise<ConnectionSyncJob> {
  return apiFetch<ConnectionSyncJob>(
    `/api/v1/libraries/${libraryId}/connections/${connectionId}/sync/`,
    {
      method: "POST",
    },
  );
}

export async function getOAuthAuthorizeUrl(
  libraryId: string,
  provider: string,
): Promise<{ provider: string; authorization_url: string }> {
  return apiFetch<{ provider: string; authorization_url: string }>(
    `/api/v1/libraries/${libraryId}/connections/oauth/${provider}/authorize/`,
  );
}


