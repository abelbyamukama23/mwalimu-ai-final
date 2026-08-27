"use client";

import { useQuery } from "@tanstack/react-query";
import { listMemberships, type Membership } from "@/lib/api/memberships";

export const MEMBERSHIPS_QUERY_KEY = ["memberships"] as const;

export function useMemberships() {
  return useQuery<Membership[]>({
    queryKey: MEMBERSHIPS_QUERY_KEY,
    queryFn: listMemberships,
  });
}
