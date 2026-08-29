import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  confirmPasswordReset,
  getGoogleAuthUrl,
  googleAuthCallback,
  requestPasswordReset,
  resendOtp,
  verifyEmail,
} from "@/lib/api/auth";
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

describe("Extended Authentication API", () => {
  it("verifyEmail posts 6-digit OTP and optional display name", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/auth/verify-email/");
      const body = JSON.parse(init?.body as string);
      expect(body).toEqual({
        email: "test@example.com",
        otp: "123456",
        display_name: "Abel",
      });
      return jsonRes(200, {
        access: "access-token-xyz",
        user: { id: "u1", email: "test@example.com", is_active: true },
      });
    });

    const res = await verifyEmail("test@example.com", "123456", "Abel");
    expect(res.access).toBe("access-token-xyz");
    expect(res.user.email).toBe("test@example.com");
  });

  it("resendOtp sends email and purpose with cooldown enforcement", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/auth/resend-otp/");
      const body = JSON.parse(init?.body as string);
      expect(body).toEqual({
        email: "test@example.com",
        purpose: "email_verification",
      });
      return jsonRes(200, { message: "A new verification code has been sent." });
    });

    const res = await resendOtp("test@example.com", "email_verification");
    expect(res.message).toBe("A new verification code has been sent.");
  });

  it("requestPasswordReset sends neutral response", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/auth/password-reset/request/");
      const body = JSON.parse(init?.body as string);
      expect(body.email).toBe("test@example.com");
      return jsonRes(200, {
        message: "If an account exists for this email, a verification code has been sent.",
      });
    });

    const res = await requestPasswordReset("test@example.com");
    expect(res.message).toContain("If an account exists");
  });

  it("confirmPasswordReset submits OTP and new password", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/auth/password-reset/confirm/");
      const body = JSON.parse(init?.body as string);
      expect(body).toEqual({
        email: "test@example.com",
        otp: "654321",
        new_password: "NewPassword123!",
        new_password_confirm: "NewPassword123!",
      });
      return jsonRes(200, { message: "Your password has been successfully reset." });
    });

    const res = await confirmPasswordReset(
      "test@example.com",
      "654321",
      "NewPassword123!",
      "NewPassword123!",
    );
    expect(res.message).toContain("successfully reset");
  });

  it("getGoogleAuthUrl returns authorization url and state", async () => {
    stubFetch(async (url) => {
      expect(url).toContain("/api/v1/auth/google/url/");
      return jsonRes(200, { url: "https://accounts.google.com/o/oauth2/v2/auth?...", state: "state123" });
    });

    const res = await getGoogleAuthUrl("http://localhost:3000/auth/google/callback");
    expect(res.state).toBe("state123");
    expect(res.url).toContain("google.com");
  });

  it("googleAuthCallback exchanges code and state", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/auth/google/callback/");
      const body = JSON.parse(init?.body as string);
      expect(body.code).toBe("auth-code");
      expect(body.state).toBe("state-123");
      return jsonRes(200, {
        access: "google-access-token",
        user: { id: "g1", email: "google@example.com", is_active: true },
      });
    });

    const res = await googleAuthCallback("auth-code", "state-123", "http://localhost:3000/auth/google/callback");
    expect(res.access).toBe("google-access-token");
    expect(res.user?.email).toBe("google@example.com");
  });
});
