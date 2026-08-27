/**
 * User Profile API client module matching Django DRF Platform API:
 *   GET   /api/v1/users/profile/ -> UserProfile
 *   PATCH /api/v1/users/profile/ -> UserProfile
 */

import { apiFetch } from "@/lib/api/client";
import type { UserProfile } from "@/lib/settings/types";

export type UpdateUserProfilePayload = {
  display_name?: string;
  avatar_url?: string;
  phone_number?: string;
  bio?: string;
};

export async function getUserProfile(): Promise<UserProfile> {
  return apiFetch<UserProfile>("/api/v1/users/profile/");
}

export async function updateUserProfile(
  payload: UpdateUserProfilePayload,
): Promise<UserProfile> {
  return apiFetch<UserProfile>("/api/v1/users/profile/", {
    method: "PATCH",
    body: payload,
  });
}
