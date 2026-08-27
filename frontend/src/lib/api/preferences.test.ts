import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getUserPreferences, updateUserPreferences } from "./preferences";

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

describe("Preferences API", () => {
  const mockPreferences = {
    id: "pref-1",
    pedagogical_style: "socratic",
    explanation_depth: "in_depth",
    response_language: "sw",
    cross_session_memory: true,
    created_at: "2026-08-25T00:00:00Z",
    updated_at: "2026-08-25T00:00:00Z",
  };

  it("fetches user preferences via GET /api/v1/users/preferences/", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/users/preferences/");
      return jsonRes(200, mockPreferences);
    });

    const prefs = await getUserPreferences();
    expect(prefs.id).toBe("pref-1");
    expect(prefs.pedagogical_style).toBe("socratic");
    expect(prefs.response_language).toBe("sw");
  });

  it("updates user preferences via PATCH /api/v1/users/preferences/", async () => {
    const fetchStub = stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/users/preferences/");
      expect(init?.method).toBe("PATCH");
      const body = JSON.parse(init?.body as string);
      expect(body.pedagogical_style).toBe("formal");
      return jsonRes(200, { ...mockPreferences, pedagogical_style: "formal" });
    });

    const updated = await updateUserPreferences({ pedagogical_style: "formal" });
    expect(fetchStub).toHaveBeenCalled();
    expect(updated.pedagogical_style).toBe("formal");
  });
});
