/**
 * Memberships API module matching the Django + DRF Platform API:
 *   GET /api/v1/memberships/ -> PaginatedResponse<Membership>
 */

import { apiFetch } from "@/lib/api/client";

export type MembershipRole = "administrator" | "teacher" | "student";
export type MembershipStatus = "active" | "pending" | "suspended";

export type MembershipInstitution = {
  id: string;
  name: string;
  slug: string;
};

export type MembershipUser = {
  id: string;
  email: string;
};

export type Membership = {
  id: string;
  user: MembershipUser;
  institution: MembershipInstitution;
  role: MembershipRole;
  status: MembershipStatus;
  created_at: string;
  updated_at: string;
};

export type PaginatedResponse<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

export async function listMemberships(): Promise<Membership[]> {
  const response = await apiFetch<PaginatedResponse<Membership> | Membership[]>(
    "/api/v1/memberships/",
  );
  if (Array.isArray(response)) {
    return response;
  }
  return response.results ?? [];
}

export type Institution = {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
};

export async function listInstitutions(): Promise<Institution[]> {
  const response = await apiFetch<PaginatedResponse<Institution> | Institution[]>(
    "/api/v1/institutions/",
  );
  if (Array.isArray(response)) {
    return response;
  }
  return response.results ?? [];
}

export async function createMembership(payload: {
  institution_id: string;
  role?: MembershipRole;
}): Promise<Membership> {
  return apiFetch<Membership>("/api/v1/memberships/", {
    method: "POST",
    body: payload,
  });
}

