"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getUserPreferences,
  updateUserPreferences,
  type UpdateUserPreferencesPayload,
} from "@/lib/api/preferences";
import type { UserPreferences } from "@/lib/settings/types";

export const USER_PREFERENCES_QUERY_KEY = ["user", "preferences"] as const;

export function useUserPreferences() {
  return useQuery<UserPreferences>({
    queryKey: USER_PREFERENCES_QUERY_KEY,
    queryFn: getUserPreferences,
    staleTime: 60_000,
  });
}

export function useUpdateUserPreferences() {
  const queryClient = useQueryClient();

  return useMutation<UserPreferences, Error, UpdateUserPreferencesPayload>({
    mutationFn: updateUserPreferences,
    onSuccess: (updated) => {
      queryClient.setQueryData(USER_PREFERENCES_QUERY_KEY, updated);
    },
  });
}
