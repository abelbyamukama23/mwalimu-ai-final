"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createMembership,
  listInstitutions,
  listMemberships,
  type Institution,
  type Membership,
  type MembershipRole,
} from "@/lib/api/memberships";

export const MEMBERSHIPS_QUERY_KEY = ["memberships"] as const;
export const INSTITUTIONS_QUERY_KEY = ["institutions"] as const;

export function useMemberships() {
  return useQuery<Membership[]>({
    queryKey: MEMBERSHIPS_QUERY_KEY,
    queryFn: listMemberships,
  });
}

export function useInstitutions() {
  return useQuery<Institution[]>({
    queryKey: INSTITUTIONS_QUERY_KEY,
    queryFn: listInstitutions,
  });
}

export function useCreateMembership() {
  const queryClient = useQueryClient();
  return useMutation<
    Membership,
    Error,
    { institution_id: string; role?: MembershipRole }
  >({
    mutationFn: createMembership,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: MEMBERSHIPS_QUERY_KEY });
    },
  });
}

