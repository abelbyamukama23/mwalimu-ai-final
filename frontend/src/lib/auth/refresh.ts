/**
 * Single-flight refresh supporting both body-passed refresh tokens and HttpOnly cookies.
 * Deduplicates concurrent refresh calls so the 401-retry path and the proactive
 * scheduler never stampede the endpoint.
 */
import {
  getCsrfToken,
  getRefreshToken,
  notifyAuthExpired,
  setAccess,
  setRefreshToken,
} from "./token-store";

const BASE_URL =
  process.env.NEXT_PUBLIC_PLATFORM_API_BASE_URL ?? "http://localhost:8000";

let inflight: Promise<string | null> | null = null;

/** Returns a fresh access token, or null if the session cannot be restored. */
export function singleFlightRefresh(): Promise<string | null> {
  if (inflight) return inflight;
  inflight = refreshOnce().finally(() => {
    inflight = null;
  });
  return inflight;
}

async function refreshOnce(): Promise<string | null> {
  const csrf = getCsrfToken();
  const storedRefresh = getRefreshToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (csrf) {
    headers["X-CSRFToken"] = csrf;
  }

  const payload: Record<string, string> = {};
  if (storedRefresh) {
    payload["refresh"] = storedRefresh;
  }

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/api/v1/auth/refresh/`, {
      method: "POST",
      headers,
      body: Object.keys(payload).length > 0 ? JSON.stringify(payload) : "{}",
      credentials: "include",
    });
  } catch {
    // Transient network failure — do not sign the user out.
    return null;
  }

  // 400/401 = the refresh token is invalid/expired → a definitive session loss.
  if (res.status === 400 || res.status === 401) {
    notifyAuthExpired();
    return null;
  }
  if (res.status === 204 || !res.ok) return null;

  const data = (await res.json()) as { access?: string; refresh?: string };
  if (typeof data.access !== "string" || data.access.length === 0) {
    notifyAuthExpired();
    return null;
  }

  setAccess(data.access);
  if (data.refresh) {
    setRefreshToken(data.refresh);
  }
  return data.access;
}
