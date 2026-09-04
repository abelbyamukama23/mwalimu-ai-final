import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  acceptInvitation,
  declineInvitation,
  getUnreadNotificationCount,
  listNotifications,
  markAllNotificationsAsRead,
  markNotificationAsRead,
  resolveInvitation,
} from "./notifications";

function jsonRes(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(
  handler: (url: string, init?: RequestInit) => Promise<Response> | Response,
) {
  const fn = vi.fn(handler);
  vi.stubGlobal("fetch", fn as unknown as typeof fetch);
  return fn;
}

beforeEach(() => {
  vi.stubGlobal("document", { cookie: "" });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Notifications API", () => {
  const mockNotification = {
    id: "notif-123",
    actor_id: "user-1",
    actor_email: "headmaster@alliance.ac.ke",
    actor_name: "Headmaster",
    notification_type: "library_invitation",
    title: "Invitation to Join Library",
    message: "You have been invited to join the Form 4 Biology library.",
    payload: {
      token: "inv_tok_abc123",
      library_id: "lib-1",
      library_name: "Form 4 Biology",
      role: "viewer",
    },
    is_read: false,
    read_at: null,
    expires_at: null,
    created_at: "2026-09-04T12:00:00Z",
    updated_at: "2026-09-04T12:00:00Z",
  };

  it("lists notifications from paginated response", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/notifications/");
      return jsonRes(200, {
        count: 1,
        next: null,
        previous: null,
        results: [mockNotification],
      });
    });

    const res = await listNotifications();
    expect(res.results).toHaveLength(1);
    expect(res.results[0].id).toBe("notif-123");
    expect(res.results[0].title).toBe("Invitation to Join Library");
  });

  it("fetches unread count", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/notifications/unread-count/");
      return jsonRes(200, { unread_count: 5 });
    });

    const res = await getUnreadNotificationCount();
    expect(res.unread_count).toBe(5);
  });

  it("marks a notification as read", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/notifications/notif-123/read/");
      expect(init?.method).toBe("POST");
      return jsonRes(200, { ...mockNotification, is_read: true, read_at: "2026-09-04T12:05:00Z" });
    });

    const res = await markNotificationAsRead("notif-123");
    expect(res.is_read).toBe(true);
  });

  it("marks all notifications as read", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/notifications/read-all/");
      expect(init?.method).toBe("POST");
      return jsonRes(200, { marked_read_count: 3 });
    });

    const res = await markAllNotificationsAsRead();
    expect(res.marked_read_count).toBe(3);
  });

  it("resolves an invitation token publicly", async () => {
    stubFetch(async (url) => {
      expect(url).toBe("http://localhost:8000/api/v1/invitations/tok_123/");
      return jsonRes(200, {
        token: "tok_123",
        library: { id: "lib-1", name: "Form 4 Biology", slug: "biology" },
        institution: { id: "inst-1", name: "Alliance High", slug: "alliance" },
        inviter: { id: "u-1", email: "teacher@alliance.ac.ke" },
        role: "viewer",
        recipient_email_masked: "s***t@alliance.ac.ke",
        expires_at: "2026-09-11T12:00:00Z",
        is_expired: false,
        status: "pending",
      });
    });

    const res = await resolveInvitation("tok_123");
    expect(res.token).toBe("tok_123");
    expect(res.library.name).toBe("Form 4 Biology");
    expect(res.recipient_email_masked).toBe("s***t@alliance.ac.ke");
  });

  it("accepts an invitation", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/invitations/tok_123/accept/");
      expect(init?.method).toBe("POST");
      return jsonRes(200, {
        status: "accepted",
        message: "Successfully joined Form 4 Biology.",
        library_id: "lib-1",
      });
    });

    const res = await acceptInvitation("tok_123");
    expect(res.status).toBe("accepted");
    expect(res.library_id).toBe("lib-1");
  });

  it("declines an invitation", async () => {
    stubFetch(async (url, init) => {
      expect(url).toBe("http://localhost:8000/api/v1/invitations/tok_123/decline/");
      expect(init?.method).toBe("POST");
      return jsonRes(200, {
        status: "declined",
        message: "Invitation declined.",
      });
    });

    const res = await declineInvitation("tok_123");
    expect(res.status).toBe("declined");
  });
});
