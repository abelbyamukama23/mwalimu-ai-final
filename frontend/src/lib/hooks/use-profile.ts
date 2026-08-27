"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getUserProfile,
  updateUserProfile,
  type UpdateUserProfilePayload,
} from "@/lib/api/profile";
import type { UserProfile } from "@/lib/settings/types";

export const USER_PROFILE_QUERY_KEY = ["user", "profile"] as const;

export function useUserProfile() {
  return useQuery<UserProfile>({
    queryKey: USER_PROFILE_QUERY_KEY,
    queryFn: getUserProfile,
    staleTime: 60_000,
  });
}

export function useUpdateUserProfile() {
  const queryClient = useQueryClient();

  return useMutation<UserProfile, Error, UpdateUserProfilePayload>({
    mutationFn: updateUserProfile,
    onSuccess: (updated) => {
      queryClient.setQueryData(USER_PROFILE_QUERY_KEY, updated);
      queryClient.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });
}
