"use client";

import { useQuery } from "@tanstack/react-query";
import { me, type User } from "@/lib/api/auth";

export const CURRENT_USER_QUERY_KEY = ["auth", "me"] as const;

export function useCurrentUser() {
  return useQuery<User>({
    queryKey: CURRENT_USER_QUERY_KEY,
    queryFn: me,
    staleTime: 300_000,
    retry: false,
  });
}
