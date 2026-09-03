/**
 * Typed Platform API client.
 *
 * Contracts are defined by the Django + DRF Platform API (see platform_api/openapi.yaml
 * and src/platform_api/apps/*). Feature modules (auth, sessions, runs, libraries,
 * resources, context, institutions) are added in their respective phases on top of
 * this client — do not add endpoints that the backend does not implement.
 *
 * Rules encoded here:
 * - Auth is `Authorization: Bearer <access JWT>` (memory from the token store).
 * - Tokens are never logged or put into URLs.
 * - A 401 triggers a single-flight refresh and one retry for non-auth endpoints.
 * - Errors are normalized into ApiError with the DRF `{detail}` / field-error shapes.
 */

import { singleFlightRefresh } from "@/lib/auth/refresh";
import { getAccess, getCsrfToken } from "@/lib/auth/token-store";

const BASE_URL =
  process.env.NEXT_PUBLIC_PLATFORM_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly details: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
}

/** Returns the current access token from memory (never localStorage). */
let accessTokenProvider: () => string | null = getAccess;

export function setAccessTokenProvider(provider: (() => string | null) | null) {
  accessTokenProvider = provider ?? getAccess;
}

export type ApiFetchOptions = {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  headers?: HeadersInit;
  body?: unknown;
  /** multipart/form-data uploads (Resource create). */
  formData?: FormData;
  signal?: AbortSignal;
  /** Attach the double-submit CSRF token (refresh/logout cookie endpoints). */
  csrf?: boolean;
  /** Internal — prevents an endless refresh loop. Do not set. */
  retry?: boolean;
};

const PUBLIC_AUTH_PATHS = new Set([
  "/api/v1/auth/login/",
  "/api/v1/auth/register/",
  "/api/v1/auth/refresh/",
]);

export async function apiFetch<T>(
  path: `/api/v1/${string}`,
  options: ApiFetchOptions = {},
): Promise<T> {
  const {
    method = "GET",
    headers: customHeaders,
    body,
    formData,
    signal,
    csrf = false,
    retry = false,
  } = options;

  const headers = new Headers(customHeaders);
  const token = accessTokenProvider();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (body !== undefined) headers.set("Content-Type", "application/json");
  if (csrf) {
    const csrfToken = getCsrfToken();
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: formData ?? (body !== undefined ? JSON.stringify(body) : undefined),
      signal,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "Network request failed. Check your connection.");
  }

  // 401 on a protected, non-auth endpoint → single-flight refresh, retry once.
  if (response.status === 401 && !retry && !PUBLIC_AUTH_PATHS.has(path)) {
    const refreshed = await singleFlightRefresh();
    if (refreshed) {
      return apiFetch<T>(path, { ...options, retry: true });
    }
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let data: unknown = undefined;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = undefined;
    }
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    if (data) {
      const recordData = data as {
        detail?: unknown;
        error?: { message?: unknown };
      };
      const detail = recordData.detail ?? recordData.error?.message;
      if (typeof detail === "string" && detail.length > 0) {
        message = detail;
      } else {
        // DRF validation errors are a TOP-LEVEL field→[message] map, e.g.
        // {email: ["A user with this email already exists."]}. Surface the first
        // field message so failures are actionable instead of a generic status.
        for (const value of Object.values(data as Record<string, unknown>)) {
          if (Array.isArray(value)) {
            const first = value.find(
              (v): v is string => typeof v === "string" && v.length > 0,
            );
            if (first) {
              message = first;
              break;
            }
          }
        }
      }
    }
    throw new ApiError(response.status, message, data);
  }

  return data as T;
}

/** DRF page-number pagination envelope used by all list endpoints (PAGE_SIZE = 20). */
export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};
