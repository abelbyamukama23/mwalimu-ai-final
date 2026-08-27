import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "@/lib/api/client";
import { singleFlightRefresh } from "@/lib/auth/refresh";
import {
  clearTokens,
  getAccess,
  getCsrfToken,
  setAccess,
} from "@/lib/auth/token-store";

const refreshUrl = "http://localhost:8000/api/v1/auth/refresh/";
const sessionsUrl = "http://localhost:8000/api/v1/sessions/";

function jsonRes(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(handler: (url: string, init?: RequestInit) => Promise<Response> | Response) {
  const fn = vi.fn(handler);
  vi.stubGlobal("fetch", fn as unknown as typeof fetch);
  return fn;
}

beforeEach(() => {
  clearTokens();
  vi.stubGlobal("document", { cookie: "csrftoken=abc" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getCsrfToken", () => {
  it("reads the double-submit csrftoken cookie", () => {
    expect(getCsrfToken()).toBe("abc");
  });

  it("returns null when the cookie is absent", () => {
    vi.stubGlobal("document", { cookie: "other=1" });
    expect(getCsrfToken()).toBeNull();
  });
});

describe("singleFlightRefresh", () => {
  it("deduplicates concurrent refreshes into one request", async () => {
    let calls = 0;
    stubFetch(async (url) => {
      expect(url).toBe(refreshUrl);
      calls += 1;
      return jsonRes(200, { access: `tok-${calls}` });
    });

    const [a, b] = await Promise.all([singleFlightRefresh(), singleFlightRefresh()]);

    expect(calls).toBe(1);
    expect(a).toBe("tok-1");
    expect(b).toBe("tok-1");
    expect(getAccess()).toBe("tok-1");
  });

  it("clears the session when the refresh is rejected (401)", async () => {
    setAccess("old-access");
    stubFetch(async () => jsonRes(401, { detail: "Token is invalid or expired" }));

    const result = await singleFlightRefresh();

    expect(result).toBeNull();
    expect(getAccess()).toBeNull();
  });
});

describe("apiFetch 401 refresh-and-retry", () => {
  it("refreshes once then retries the original request", async () => {
    let sessionCalls = 0;
    const fetchMock = stubFetch(async (url) => {
      if (url === refreshUrl) return jsonRes(200, { access: "new-access" });
      if (url === sessionsUrl) {
        sessionCalls += 1;
        return sessionCalls === 1 ? jsonRes(401, { detail: "unauth" }) : jsonRes(200, { results: [] });
      }
      return jsonRes(404, {});
    });

    const result = await apiFetch("/api/v1/sessions/");

    expect(result).toEqual({ results: [] });
    expect(sessionCalls).toBe(2);
    // One refresh for the 401, one retried original request.
    expect(fetchMock.mock.calls.filter(([u]) => u === refreshUrl)).toHaveLength(1);
    expect(getAccess()).toBe("new-access");
  });
});
