import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
  type Connector,
} from "./connectors";

function jsonRes(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(
  handler: (url: string, init?: RequestInit) => Promise<Response> | Response,
) {
  const fn = vi.fn(handler);
  vi.stubGlobal("fetch", fn as unknown as typeof fetch);
  return fn;
}

beforeEach(() => {
  vi.stubGlobal("document", { cookie: "" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Connectors & Connections API", () => {
  const mockConnector: Connector = {
    id: "conn-cat-1",
    name: "Web Crawler",
    slug: "web-crawler",
    description: "Crawl web pages and download documentation.",
    connector_type: "web_crawler",
    auth_type: "none",
    config_schema: {
      type: "object",
      properties: {
        base_url: { type: "string", title: "Base URL" },
      },
      required: ["base_url"],
    },
    auth_schema: {
      type: "object",
      properties: {
        api_key: { type: "string", title: "API Key", writeOnly: true },
      },
    },
    is_active: true,
    created_at: "2026-08-24T12:00:00Z",
    updated_at: "2026-08-24T12:00:00Z",
  };

  const mockConnection: Connection = {
    id: "conn-inst-1",
    library_id: "lib-1",
    connector: {
      id: "conn-cat-1",
      name: "Web Crawler",
      slug: "web-crawler",
      connector_type: "web_crawler",
      auth_type: "none",
    },
    name: "Curriculum Docs Crawler",
    status: "active",
    configuration: { base_url: "https://curriculum.ac.ke" },
    sync_frequency: "daily",
    last_synced_at: "2026-08-24T13:00:00Z",
    last_sync_status: "success",
    last_sync_error: "",
    has_credentials: true,
    created_at: "2026-08-24T12:00:00Z",
    updated_at: "2026-08-24T12:00:00Z",
  };

  it("lists active connectors from catalog", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/connectors/");
      return jsonRes(200, [mockConnector]);
    });

    const connectors = await listConnectors();
    expect(connectors).toHaveLength(1);
    expect(connectors[0].name).toBe("Web Crawler");
    expect(connectors[0].is_active).toBe(true);
  });

  it("retrieves connector detail by ID", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/connectors/conn-cat-1/");
      return jsonRes(200, mockConnector);
    });

    const connector = await getConnector("conn-cat-1");
    expect(connector.id).toBe("conn-cat-1");
    expect(connector.config_schema.properties).toBeDefined();
  });

  it("retrieves a single connection by ID", async () => {
    stubFetch(async (url) => {
      expect(url).toBe(
        "http://localhost:8000/api/v1/libraries/lib-1/connections/conn-inst-1/",
      );
      return jsonRes(200, mockConnection);
    });

    const connection = await getLibraryConnection("lib-1", "conn-inst-1");
    expect(connection.id).toBe("conn-inst-1");
    expect(connection.name).toBe("Curriculum Docs Crawler");
  });

  it("lists connections for a library", async () => {
    stubFetch(async (url) => {
      expect(url).toBe(
        "http://localhost:8000/api/v1/libraries/lib-1/connections/",
      );
      return jsonRes(200, [mockConnection]);
    });

    const connections = await listLibraryConnections("lib-1");
    expect(connections).toHaveLength(1);
    expect(connections[0].name).toBe("Curriculum Docs Crawler");
    expect(connections[0].has_credentials).toBe(true);
    // Invariant: encrypted_credentials is NEVER returned
    expect((connections[0] as unknown as { encrypted_credentials?: string }).encrypted_credentials).toBeUndefined();
  });

  it("creates a connection with write-only credentials", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe(
        "http://localhost:8000/api/v1/libraries/lib-1/connections/",
      );
      expect(init?.method).toBe("POST");
      const body = JSON.parse(init?.body as string);
      expect(body.connector_id).toBe("conn-cat-1");
      expect(body.name).toBe("New S3 Link");
      expect(body.credentials?.api_key).toBe("secret-api-key-123");

      return jsonRes(201, {
        ...mockConnection,
        id: "conn-inst-2",
        name: "New S3 Link",
        has_credentials: true,
      });
    });

    const created = await createLibraryConnection("lib-1", {
      connector_id: "conn-cat-1",
      name: "New S3 Link",
      configuration: { base_url: "https://s3.aws.com" },
      credentials: { api_key: "secret-api-key-123" },
      sync_frequency: "hourly",
      status: "active",
    });

    expect(fetchStub).toHaveBeenCalled();
    expect(created.id).toBe("conn-inst-2");
    expect(created.has_credentials).toBe(true);
    // Invariant: API does not echo back raw or encrypted credentials
    expect((created as unknown as { credentials?: unknown }).credentials).toBeUndefined();
  });

  it("updates connection configuration via PATCH", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe(
        "http://localhost:8000/api/v1/libraries/lib-1/connections/conn-inst-1/",
      );
      expect(init?.method).toBe("PATCH");
      const body = JSON.parse(init?.body as string);
      expect(body.sync_frequency).toBe("weekly");

      return jsonRes(200, {
        ...mockConnection,
        sync_frequency: "weekly",
      });
    });

    const updated = await updateLibraryConnection("lib-1", "conn-inst-1", {
      sync_frequency: "weekly",
    });

    expect(fetchStub).toHaveBeenCalled();
    expect(updated.sync_frequency).toBe("weekly");
  });

  it("deletes a connection via DELETE", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe(
        "http://localhost:8000/api/v1/libraries/lib-1/connections/conn-inst-1/",
      );
      expect(init?.method).toBe("DELETE");
      return new Response(null, { status: 204 });
    });

    await deleteLibraryConnection("lib-1", "conn-inst-1");
    expect(fetchStub).toHaveBeenCalled();
  });

  it("lists sync jobs for a connection", async () => {
    const mockSyncJob = {
      id: "job-1",
      connection_id: "conn-inst-1",
      status: "completed",
      celery_task_id: "task-uuid-1",
      resources_discovered: 12,
      resources_created: 5,
      resources_updated: 7,
      resources_deleted: 0,
      error_code: null,
      error_message: "",
      started_at: "2026-08-24T12:00:00Z",
      finished_at: "2026-08-24T12:01:00Z",
      created_at: "2026-08-24T12:00:00Z",
      updated_at: "2026-08-24T12:01:00Z",
    };

    stubFetch(async (url) => {
      expect(url).toBe(
        "http://localhost:8000/api/v1/libraries/lib-1/connections/conn-inst-1/sync-jobs/",
      );
      return jsonRes(200, [mockSyncJob]);
    });

    const jobs = await listConnectionSyncJobs("lib-1", "conn-inst-1");
    expect(jobs).toHaveLength(1);
    expect(jobs[0].status).toBe("completed");
    expect(jobs[0].resources_discovered).toBe(12);
  });
});
