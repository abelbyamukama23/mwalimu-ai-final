/**
 * Auth feature module. Contracts match the Platform API:
 *   POST /api/v1/auth/register/          -> {email, requires_verification, message}
 *   POST /api/v1/auth/verify-email/      -> {access, user, message} (refresh delivered as HttpOnly cookie)
 *   POST /api/v1/auth/resend-otp/        -> {message}
 *   POST /api/v1/auth/login/             -> {access, user} (refresh delivered as HttpOnly cookie)
 *   POST /api/v1/auth/refresh/           -> {access} (refresh read from cookie)
 *   POST /api/v1/auth/logout/            -> 204 (clears refresh cookie)
 *   GET  /api/v1/auth/me/                -> User
 *   POST /api/v1/auth/password-reset/request/ -> {message}
 *   POST /api/v1/auth/password-reset/confirm/ -> {message}
 *   GET  /api/v1/auth/google/url/        -> {url, state}
 *   POST /api/v1/auth/google/callback/   -> {access, user}
 */
import { apiFetch } from "@/lib/api/client";

export type UserProfile = {
  id: string;
  display_name: string;
  avatar_url: string;
  phone_number?: string;
  bio?: string;
  created_at: string;
  updated_at: string;
};

export type User = {
  id: string;
  email: string;
  is_active: boolean;
  is_email_verified?: boolean;
  profile?: UserProfile | null;
  created_at: string;
  updated_at: string;
};

export type LoginResult = {
  access: string;
  refresh?: string;
  user?: User;
};

export type RegisterResult = {
  email: string;
  requires_verification: boolean;
  message: string;
};

export type VerifyEmailResult = {
  access: string;
  user: User;
  message?: string;
};

export type GenericAuthMessage = {
  message?: string;
  error?: string;
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

export async function verifyEmail(
  email: string,
  otp: string,
  displayName?: string,
): Promise<VerifyEmailResult> {
  return apiFetch<VerifyEmailResult>("/api/v1/auth/verify-email/", {
    method: "POST",
    body: { email, otp, display_name: displayName || "" },
  });
}

export async function resendOtp(
  email: string,
  purpose: "email_verification" | "password_reset" = "email_verification",
): Promise<GenericAuthMessage> {
  return apiFetch<GenericAuthMessage>("/api/v1/auth/resend-otp/", {
    method: "POST",
    body: { email, purpose },
  });
}

export async function login(email: string, password: string): Promise<LoginResult> {
  return apiFetch<LoginResult>("/api/v1/auth/login/", {
    method: "POST",
    body: { email, password },
  });
}

export async function requestPasswordReset(email: string): Promise<GenericAuthMessage> {
  return apiFetch<GenericAuthMessage>("/api/v1/auth/password-reset/request/", {
    method: "POST",
    body: { email },
  });
}

export async function confirmPasswordReset(
  email: string,
  otp: string,
  newPassword: string,
  confirmPassword: string,
): Promise<GenericAuthMessage> {
  return apiFetch<GenericAuthMessage>("/api/v1/auth/password-reset/confirm/", {
    method: "POST",
    body: {
      email,
      otp,
      new_password: newPassword,
      new_password_confirm: confirmPassword,
    },
  });
}

export async function getGoogleAuthUrl(redirectUri?: string): Promise<{ url: string; state: string }> {
  const query = redirectUri ? `?redirect_uri=${encodeURIComponent(redirectUri)}` : "";
  return apiFetch<{ url: string; state: string }>(`/api/v1/auth/google/url/${query}`);
}

export async function googleAuthCallback(
  code: string,
  state: string,
  redirectUri?: string,
): Promise<LoginResult> {
  return apiFetch<LoginResult>("/api/v1/auth/google/callback/", {
    method: "POST",
    body: { code, state, redirect_uri: redirectUri || "" },
  });
}

export async function me(): Promise<User> {
  return apiFetch<User>("/api/v1/auth/me/");
}

export async function logout(): Promise<void> {
  await apiFetch("/api/v1/auth/logout/", { method: "POST", csrf: true });
}
