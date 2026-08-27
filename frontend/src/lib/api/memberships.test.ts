import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { listMemberships } from "./memberships";

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

describe("Memberships API", () => {
  it("unwraps results from a paginated DRF response", async () => {
    const mockMemberships = [
      {
        id: "mem-1",
        user: { id: "u-1", email: "admin@school.ac.ke" },
        institution: { id: "inst-1", name: "Alliance High", slug: "alliance" },
        role: "administrator",
        status: "active",
        created_at: "2026-08-24T12:00:00Z",
        updated_at: "2026-08-24T12:00:00Z",
      },
    ];

    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/memberships/");
      return jsonRes(200, {
        count: 1,
        next: null,
        previous: null,
        results: mockMemberships,
      });
    });

    const result = await listMemberships();
    expect(result).toHaveLength(1);
    expect(result[0].role).toBe("administrator");
    expect(result[0].institution.name).toBe("Alliance High");
  });

  it("handles memberless users returning empty list", async () => {
    stubFetch(async () => {
      return jsonRes(200, {
        count: 0,
        next: null,
        previous: null,
        results: [],
      });
    });

    const result = await listMemberships();
    expect(result).toEqual([]);
  });

  it("handles direct array responses", async () => {
    stubFetch(async () => {
      return jsonRes(200, [
        {
          id: "mem-2",
          user: { id: "u-2", email: "teacher@school.ac.ke" },
          institution: { id: "inst-2", name: "Mang'u High", slug: "mangu" },
          role: "teacher",
          status: "active",
          created_at: "2026-08-24T12:00:00Z",
          updated_at: "2026-08-24T12:00:00Z",
        },
      ]);
    });

    const result = await listMemberships();
    expect(result).toHaveLength(1);
    expect(result[0].role).toBe("teacher");
  });
});
