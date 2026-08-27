/**
 * Auth token state for the Mwalimu frontend.
 *
 * - Access token: memory only (5-minute TTL) — NEVER persisted.
 * - Refresh token: an HttpOnly + Secure cookie owned by the Platform API.
 *   JavaScript can never read, persist, decode, or transmit it. The only JS
 *   cookie we touch is the (non-HttpOnly) double-submit CSRF token.
 */

let accessToken: string | null = null;

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
}

export function getAccess(): string | null {
  return accessToken;
}

export function clearTokens() {
  accessToken = null;
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
