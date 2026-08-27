/**
 * Single-flight cookie-based refresh. Deduplicates concurrent refresh calls so
 * the 401-retry path and the proactive scheduler never stampede the endpoint.
 *
 * The refresh token is never touched by JavaScript: the browser sends the
 * HttpOnly cookie automatically (credentials: "include"), and the double-submit
 * CSRF token is attached as the X-CSRFToken header.
 *
 * Uses a raw fetch (NOT the apiFetch client) to avoid recursion through the
 * 401-and-retry handler. Only mutates token state; does not touch React.
 */
import { getCsrfToken, notifyAuthExpired, setAccess } from "./token-store";

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

  // A session can only exist if the double-submit CSRF cookie was set (login and
  // registration always set it alongside the refresh cookie). When it is absent
  // there is nothing to restore — return without a network round-trip, which
  // avoids a needless 401/403 console error on the public auth surface.
  if (!csrf) return null;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}/api/v1/auth/refresh/`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf,
      },
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

  const data = (await res.json()) as { access?: string };
  if (typeof data.access !== "string" || data.access.length === 0) {
    notifyAuthExpired();
    return null;
  }

  setAccess(data.access);
  return data.access;
}
