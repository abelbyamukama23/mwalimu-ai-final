/**
 * Notifications and Invitations API client module matching Django + DRF Platform API:
 *   GET   /api/v1/notifications/              -> Paginated<PlatformNotification>
 *   GET   /api/v1/notifications/unread-count/ -> { unread_count: number }
 *   POST  /api/v1/notifications/{id}/read/    -> PlatformNotification
 *   POST  /api/v1/notifications/read-all/     -> { marked_read_count: number }
 *   GET   /api/v1/invitations/{token}/        -> PublicInvitationResolution
 *   POST  /api/v1/invitations/{token}/accept/  -> { status: string, message: string, library_id: string }
 *   POST  /api/v1/invitations/{token}/decline/ -> { status: string, message: string }
 */

import { apiFetch, type Paginated } from "@/lib/api/client";

export interface PlatformNotification {
  id: string;
  actor_id: string | null;
  actor_email: string | null;
  actor_name: string | null;
  notification_type: string;
  title: string;
  message: string;
  payload: Record<string, any>;
  is_read: boolean;
  read_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface UnreadNotificationCountResponse {
  unread_count: number;
}

export interface PublicInvitationResolution {
  token: string;
  library: {
    id: string;
    name: string;
    slug: string;
    description?: string;
  };
  institution: {
    id: string;
    name: string;
    slug: string;
    badge_url?: string | null;
  };
  inviter: {
    id: string;
    email: string;
    display_name?: string;
  };
  role: string;
  recipient_email_masked: string;
  expires_at: string;
  is_expired: boolean;
  status: string;
}

export interface AcceptInvitationResponse {
  status: string;
  message: string;
  library_id?: string;
}

export interface DeclineInvitationResponse {
  status: string;
  message: string;
}

export async function listNotifications(): Promise<Paginated<PlatformNotification>> {
  return apiFetch<Paginated<PlatformNotification>>("/api/v1/notifications/");
}

export async function getUnreadNotificationCount(): Promise<UnreadNotificationCountResponse> {
  return apiFetch<UnreadNotificationCountResponse>("/api/v1/notifications/unread-count/");
}

export async function markNotificationAsRead(id: string): Promise<PlatformNotification> {
  return apiFetch<PlatformNotification>(`/api/v1/notifications/${id}/read/`, {
    method: "POST",
  });
}

export async function markAllNotificationsAsRead(): Promise<{ marked_read_count: number }> {
  return apiFetch<{ marked_read_count: number }>("/api/v1/notifications/read-all/", {
    method: "POST",
  });
}

export async function resolveInvitation(token: string): Promise<PublicInvitationResolution> {
  return apiFetch<PublicInvitationResolution>(`/api/v1/invitations/${token}/`);
}

export async function acceptInvitation(token: string): Promise<AcceptInvitationResponse> {
  return apiFetch<AcceptInvitationResponse>(`/api/v1/invitations/${token}/accept/`, {
    method: "POST",
  });
}

export async function declineInvitation(token: string): Promise<DeclineInvitationResponse> {
  return apiFetch<DeclineInvitationResponse>(`/api/v1/invitations/${token}/decline/`, {
    method: "POST",
  });
}
