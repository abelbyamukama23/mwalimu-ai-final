/**
 * Auth feature module. Contracts match the Platform API exactly:
 *   POST /api/v1/auth/register/ -> {access, user}  (refresh delivered as an HttpOnly cookie)
 *   POST /api/v1/auth/login/    -> {access}   (refresh delivered as an HttpOnly cookie)
 *   POST /api/v1/auth/refresh/  -> {access}   (refresh read from the cookie)
 *   POST /api/v1/auth/logout/   -> 204        (clears the refresh cookie)
 *   GET  /api/v1/auth/me/       -> User
 */
import { apiFetch } from "@/lib/api/client";

export type User = {
  id: string;
  email: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type LoginResult = {
  access: string;
  refresh?: string;
};


export type RegisterResult = LoginResult & {
  user: User;
};

export async function register(
  email: string,
  password: string,
  confirm: string,
): Promise<RegisterResult> {
  return apiFetch<RegisterResult>("/api/v1/auth/register/", {
    method: "POST",
    body: { email, password, password_confirm: confirm },
  });
}

export async function login(email: string, password: string): Promise<LoginResult> {
  return apiFetch<LoginResult>("/api/v1/auth/login/", {
    method: "POST",
    body: { email, password },
  });
}

export async function me(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me/");
}

export async function logout(): Promise<void> {
  await apiFetch("/api/v1/auth/logout/", { method: "POST", csrf: true });
}
