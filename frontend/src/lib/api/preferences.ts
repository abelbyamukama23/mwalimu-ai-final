/**
 * User Pedagogical Preferences API client module matching Django DRF Platform API:
 *   GET   /api/v1/users/preferences/ -> UserPreferences
 *   PATCH /api/v1/users/preferences/ -> UserPreferences
 */

import { apiFetch } from "@/lib/api/client";
import type {
  ExplanationDepth,
  PedagogicalStyle,
  UserPreferences,
} from "@/lib/settings/types";

export type UpdateUserPreferencesPayload = {
  pedagogical_style?: PedagogicalStyle;
  explanation_depth?: ExplanationDepth;
  response_language?: string;
  cross_session_memory?: boolean;
};

export async function getUserPreferences(): Promise<UserPreferences> {
  return apiFetch<UserPreferences>("/api/v1/users/preferences/");
}

export async function updateUserPreferences(
  payload: UpdateUserPreferencesPayload,
): Promise<UserPreferences> {
  return apiFetch<UserPreferences>("/api/v1/users/preferences/", {
    method: "PATCH",
    body: payload,
  });
}
