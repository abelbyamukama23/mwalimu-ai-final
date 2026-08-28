/**
 * Auth token state for the Mwalimu frontend.
 *
 * - Access token: stored in memory + persisted to localStorage for reliable tab/refresh persistence.
 * - Refresh token: persisted to localStorage & cookie for reliable single-flight token rotation.
 */

const ACCESS_KEY = "mwalimu_access_token";
const REFRESH_KEY = "mwalimu_refresh_token";

let accessToken: string | null = null;
let refreshToken: string | null = null;

let authExpiredHandler: (() => void) | null = null;

export function setAuthExpiredHandler(fn: (() => void) | null) {
  authExpiredHandler = fn;
}

/** Called when the session is definitively invalid (refresh rejected/expired). */
export function notifyAuthExpired() {
  clearTokens();
  authExpiredHandler?.();
}

export function setAccess(token: string) {
  accessToken = token;
  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(ACCESS_KEY, token);
    } catch {}
  }
}

export function getAccess(): string | null {
  if (accessToken) return accessToken;
  if (typeof window !== "undefined") {
    try {
      accessToken = localStorage.getItem(ACCESS_KEY);
    } catch {}
  }
  return accessToken;
}

export function setRefreshToken(token: string) {
  refreshToken = token;
  if (typeof window !== "undefined") {
    try {
      localStorage.setItem(REFRESH_KEY, token);
    } catch {}
  }
}

export function getRefreshToken(): string | null {
  if (refreshToken) return refreshToken;
  if (typeof window !== "undefined") {
    try {
      refreshToken = localStorage.getItem(REFRESH_KEY);
    } catch {}
  }
  return refreshToken;
}

export function clearTokens() {
  accessToken = null;
  refreshToken = null;
  if (typeof window !== "undefined") {
    try {
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
    } catch {}
  }
}

/** Read the non-HttpOnly double-submit CSRF token cookie. */
export function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/** Decode a JWT payload (claims) without verifying the signature. */
export function decodeJwt(
  token: string,
): { exp?: number; [key: string]: unknown } | null {
  try {
    const part = token.split(".")[1];
    if (!part) return null;
    const base64 = part.replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64.padEnd(Math.ceil(base64.length / 4) * 4, "=");
    const json = decodeURIComponent(
      atob(padded)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join(""),
    );
    return JSON.parse(json);
  } catch {
    return null;
  }
}

/** Milliseconds until the access token's `exp` claim, or 0 if unknown/expired. */
export function getAccessRemainingMs(token: string): number {
  const claims = decodeJwt(token);
  if (!claims || typeof claims.exp !== "number") return 0;
  return claims.exp * 1000 - Date.now();
}
