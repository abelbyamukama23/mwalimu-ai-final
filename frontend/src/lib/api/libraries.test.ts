import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import {
  createLibrary,
  deleteLibrary,
  getLibrary,
  listLibraries,
  listLibraryResources,
  updateLibrary,
} from "./libraries";

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

describe("Libraries API", () => {
  const mockLibrary = {
    id: "lib-1",
    institution: { id: "inst-1", name: "Alliance High", slug: "alliance" },
    name: "Form 4 Biology",
    slug: "form-4-biology",
    description: "Curriculum materials for Form 4 Biology.",
    status: "active",
    visibility: "discoverable",
    created_at: "2026-08-24T12:00:00Z",
    updated_at: "2026-08-24T12:00:00Z",
  };

  it("lists libraries from paginated response", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/libraries/");
      return jsonRes(200, {
        count: 1,
        next: null,
        previous: null,
        results: [mockLibrary],
      });
    });

    const results = await listLibraries();
    expect(results).toHaveLength(1);
    expect(results[0].slug).toBe("form-4-biology");
    expect(results[0].visibility).toBe("discoverable");
  });

  it("retrieves a single library by ID", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/libraries/lib-1/");
      return jsonRes(200, mockLibrary);
    });

    const result = await getLibrary("lib-1");
    expect(result.id).toBe("lib-1");
    expect(result.name).toBe("Form 4 Biology");
  });

  it("creates a library successfully", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/libraries/");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(init?.body as string);
      expect(body.institution_id).toBe("inst-1");
      expect(body.name).toBe("New Physics Library");
      expect(body.slug).toBe("new-physics-library");
      return jsonRes(201, {
        ...mockLibrary,
        id: "lib-2",
        name: "New Physics Library",
        slug: "new-physics-library",
      });
    });

    const result = await createLibrary({
      institution_id: "inst-1",
      name: "New Physics Library",
      slug: "new-physics-library",
      visibility: "restricted",
    });

    expect(fetchStub).toHaveBeenCalled();
    expect(result.id).toBe("lib-2");
  });

  it("creates a personal library successfully without institution_id", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/libraries/");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(init?.body as string);
      expect(body.institution_id).toBeUndefined();
      expect(body.name).toBe("My Biology Notes");
      expect(body.slug).toBe("my-biology-notes");
      return jsonRes(201, {
        id: "lib-personal-1",
        scope_type: "personal",
        is_personal: true,
        institution: null,
        name: "My Biology Notes",
        slug: "my-biology-notes",
        description: "Study notes",
        status: "active",
        visibility: "restricted",
        created_at: "2026-08-25T00:00:00Z",
        updated_at: "2026-08-25T00:00:00Z",
      });
    });

    const result = await createLibrary({
      name: "My Biology Notes",
      slug: "my-biology-notes",
      description: "Study notes",
    });

    expect(fetchStub).toHaveBeenCalled();
    expect(result.id).toBe("lib-personal-1");
    expect(result.scope_type).toBe("personal");
    expect(result.is_personal).toBe(true);
    expect(result.institution).toBeNull();
  });

  it("handles validation error (400) when creating library", async () => {
    stubFetch(async () => {
      return jsonRes(400, {
        slug: ["A library with this slug already exists in this institution."],
      });
    });

    await expect(
      createLibrary({
        institution_id: "inst-1",
        name: "Duplicate Library",
        slug: "duplicate-slug",
      }),
    ).rejects.toThrow(ApiError);
  });

  it("handles permission denied (403) when user is not admin", async () => {
    stubFetch(async () => {
      return jsonRes(403, {
        detail:
          "You do not have permission to create a library in this institution.",
      });
    });

    await expect(
      createLibrary({
        institution_id: "inst-1",
        name: "Unauthorized Library",
        slug: "unauthorized-slug",
      }),
    ).rejects.toThrow(ApiError);
  });

  it("updates library metadata via PATCH", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/libraries/lib-1/");
      expect(init?.method).toBe("PATCH");
      const body = JSON.parse(init?.body as string);
      expect(body.name).toBe("Updated Title");
      return jsonRes(200, {
        ...mockLibrary,
        name: "Updated Title",
      });
    });

    const result = await updateLibrary("lib-1", { name: "Updated Title" });
    expect(fetchStub).toHaveBeenCalled();
    expect(result.name).toBe("Updated Title");
  });

  it("deletes a library via DELETE", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/libraries/lib-1/");
      expect(init?.method).toBe("DELETE");
      return new Response(null, { status: 204 });
    });

    await deleteLibrary("lib-1");
    expect(fetchStub).toHaveBeenCalled();
  });

  it("lists library resources", async () => {
    const mockResource = {
      id: "res-1",
      library: { id: "lib-1", name: "Form 4 Biology", slug: "form-4-biology" },
      name: "cell-structure.pdf",
      resource_type: "pdf",
      original_filename: "cell-structure.pdf",
      content_type: "application/pdf",
      size: 1048576,
      object_key: "libraries/lib-1/cell-structure.pdf",
      checksum: "abc123sha",
      status: "indexed",
      created_at: "2026-08-24T12:00:00Z",
      updated_at: "2026-08-24T12:00:00Z",
    };

    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/libraries/lib-1/resources/");
      return jsonRes(200, {
        count: 1,
        next: null,
        previous: null,
        results: [mockResource],
      });
    });

    const resources = await listLibraryResources("lib-1");
    expect(resources).toHaveLength(1);
    expect(resources[0].name).toBe("cell-structure.pdf");
    expect(resources[0].status).toBe("indexed");
  });
});
