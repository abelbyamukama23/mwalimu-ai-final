import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  addFamiliarRegion,
  deleteFamiliarRegion,
  listFamiliarRegions,
  reorderFamiliarRegions,
  searchGeographicUnits,
} from "./context";

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

describe("Context API", () => {
  const mockRegion = {
    id: "reg-1",
    geographic_unit: {
      id: "geo-1",
      name: "Kirinyaga County",
      unit_type: "county",
      country_code: "KE",
    },
    priority: 1,
    created_at: "2026-08-25T00:00:00Z",
    updated_at: "2026-08-25T00:00:00Z",
  };

  it("lists familiar regions", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/context/familiar-regions/");
      return jsonRes(200, [mockRegion]);
    });

    const list = await listFamiliarRegions();
    expect(list).toHaveLength(1);
    expect(list[0].geographic_unit.name).toBe("Kirinyaga County");
  });

  it("adds a familiar region", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/context/familiar-regions/");
      expect(init?.method).toBe("POST");
      const body = JSON.parse(init?.body as string);
      expect(body.geographic_unit_id).toBe("geo-2");
      return jsonRes(201, { ...mockRegion, id: "reg-2" });
    });

    const result = await addFamiliarRegion({ geographic_unit_id: "geo-2" });
    expect(fetchStub).toHaveBeenCalled();
    expect(result.id).toBe("reg-2");
  });

  it("deletes a familiar region", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/context/familiar-regions/reg-1/");
      expect(init?.method).toBe("DELETE");
      return new Response(null, { status: 204 });
    });

    await deleteFamiliarRegion("reg-1");
    expect(fetchStub).toHaveBeenCalled();
  });

  it("reorders familiar regions", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/context/familiar-regions/reorder/");
      expect(init?.method).toBe("PUT");
      const body = JSON.parse(init?.body as string);
      expect(body.region_ids).toEqual(["reg-2", "reg-1"]);
      return jsonRes(200, [{ ...mockRegion, id: "reg-2", priority: 1 }]);
    });

    const result = await reorderFamiliarRegions(["reg-2", "reg-1"]);
    expect(fetchStub).toHaveBeenCalled();
    expect(result[0].id).toBe("reg-2");
  });

  it("searches geographic units", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/context/geographic-units/?search=Kirinyaga");
      return jsonRes(200, {
        count: 1,
        results: [mockRegion.geographic_unit],
      });
    });

    const results = await searchGeographicUnits("Kirinyaga");
    expect(results).toHaveLength(1);
    expect(results[0].name).toBe("Kirinyaga County");
  });
});
