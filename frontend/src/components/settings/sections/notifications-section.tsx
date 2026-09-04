"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  Bell,
  BookOpen,
  Check,
  CheckCheck,
  Clock,
  ExternalLink,
  Loader2,
  Mail,
  Shield,
  UserCheck,
} from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { useToast } from "@/components/ui/toast";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { SettingRow } from "../primitives/setting-row";
import { SettingToggle } from "../primitives/setting-toggle";
import {
  listNotifications,
  markAllNotificationsAsRead,
  markNotificationAsRead,
  acceptInvitation,
  declineInvitation,
  type PlatformNotification,
} from "@/lib/api/notifications";
import { cn } from "@/lib/utils";

type FilterTab = "all" | "unread" | "invitations";

export function NotificationsSection() {
  const router = useRouter();
  const toast = useToast();
  const { status, user } = useAuth();

  const [notifications, setNotifications] = useState<PlatformNotification[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [filter, setFilter] = useState<FilterTab>("all");
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{
    id: string;
    text: string;
    type: "success" | "error";
    libraryId?: string;
  } | null>(null);

  // Preference states (stored in local device preferences for now)
  const [emailInvites, setEmailInvites] = useState(true);
  const [securityAlerts, setSecurityAlerts] = useState(true);
  const [inAppAlerts, setInAppAlerts] = useState(true);

  const isAuthenticated = status === "authenticated";

  const fetchNotifications = async () => {
    if (!isAuthenticated) {
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    try {
      const res = await listNotifications();
      setNotifications(res.results ?? []);
    } catch {
      // Graceful fallback
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchNotifications();
  }, [isAuthenticated]);

  const handleMarkRead = async (notification: PlatformNotification) => {
    if (notification.is_read) return;
    try {
      await markNotificationAsRead(notification.id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n)),
      );
    } catch {
      // Ignore
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      toast("All notifications marked as read");
    } catch {
      toast("Failed to mark all as read");
    }
  };

  const handleAcceptInvite = async (notification: PlatformNotification) => {
    const token = notification.payload?.token;
    if (!token) return;

    setActionLoadingId(notification.id);
    setActionMessage(null);
    try {
      const res = await acceptInvitation(token);
      setActionMessage({
        id: notification.id,
        text: res.message || "Joined library successfully!",
        type: "success",
        libraryId: res.library_id,
      });
      await handleMarkRead(notification);
      toast("Joined library successfully");
    } catch (err: any) {
      setActionMessage({
        id: notification.id,
        text: err?.message || "Failed to accept invitation.",
        type: "error",
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleDeclineInvite = async (notification: PlatformNotification) => {
    const token = notification.payload?.token;
    if (!token) return;

    setActionLoadingId(notification.id);
    setActionMessage(null);
    try {
      const res = await declineInvitation(token);
      setActionMessage({
        id: notification.id,
        text: res.message || "Invitation declined.",
        type: "success",
      });
      await handleMarkRead(notification);
      toast("Invitation declined");
    } catch (err: any) {
      setActionMessage({
        id: notification.id,
        text: err?.message || "Failed to decline invitation.",
        type: "error",
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  const unreadCount = notifications.filter((n) => !n.is_read).length;

  const filteredNotifications = notifications.filter((n) => {
    if (filter === "unread") return !n.is_read;
    if (filter === "invitations") {
      return n.notification_type.includes("library_invitation");
    }
    return true;
  });

  const getNotificationIcon = (type: string) => {
    if (type.includes("library_invitation")) {
      return <BookOpen size={16} className="text-accent" />;
    }
    if (type.includes("security") || type.includes("auth")) {
      return <Shield size={16} className="text-amber-500" />;
    }
    if (type.includes("member")) {
      return <UserCheck size={16} className="text-indigo-500" />;
    }
    return <Mail size={16} className="text-ink-secondary" />;
  };

  return (
    <div className="mx-auto max-w-xl space-y-6">
      {/* Title */}
      <div>
        <h2 className="text-22 font-semibold text-ink">Notifications</h2>
        <p className="mt-1 text-13 text-ink-secondary">
          What Mwalimu tells you about, and when.
        </p>
      </div>

      {/* Communications Inbox Card */}
      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        {/* Inbox Header */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border bg-canvas/40 px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="text-14 font-medium text-ink">Inbox</span>
            {unreadCount > 0 ? (
              <Badge tone="accent">{unreadCount} unread</Badge>
            ) : (
              <Badge tone="neutral">All caught up</Badge>
            )}
          </div>

          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="flex items-center gap-1.5 text-12 font-medium text-accent transition-colors hover:underline"
              >
                <CheckCheck size={14} />
                <span>Mark all read</span>
              </button>
            )}
          </div>
        </div>

        {/* Filter Tabs */}
        <div className="flex border-b border-border bg-surface px-5 text-13">
          <button
            type="button"
            onClick={() => setFilter("all")}
            className={cn(
              "border-b-2 py-2.5 px-3 font-medium transition-colors",
              filter === "all"
                ? "border-accent text-accent"
                : "border-transparent text-ink-secondary hover:text-ink",
            )}
          >
            All ({notifications.length})
          </button>
          <button
            type="button"
            onClick={() => setFilter("unread")}
            className={cn(
              "border-b-2 py-2.5 px-3 font-medium transition-colors",
              filter === "unread"
                ? "border-accent text-accent"
                : "border-transparent text-ink-secondary hover:text-ink",
            )}
          >
            Unread ({unreadCount})
          </button>
          <button
            type="button"
            onClick={() => setFilter("invitations")}
            className={cn(
              "border-b-2 py-2.5 px-3 font-medium transition-colors",
              filter === "invitations"
                ? "border-accent text-accent"
                : "border-transparent text-ink-secondary hover:text-ink",
            )}
          >
            Invitations (
            {notifications.filter((n) => n.notification_type.includes("library_invitation")).length}
            )
          </button>
        </div>

        {/* List Content */}
        <div className="divide-y divide-border/70 max-h-[380px] overflow-y-auto">
          {isLoading ? (
            <div className="flex h-36 items-center justify-center text-13 text-ink-tertiary">
              <Loader2 size={18} className="mr-2 animate-spin text-accent" />
              Loading notifications...
            </div>
          ) : filteredNotifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-4 py-12 text-center">
              <div className="mb-2.5 flex h-10 w-10 items-center justify-center rounded-full bg-subtle text-ink-tertiary">
                <Bell size={18} />
              </div>
              <div className="text-13 font-medium text-ink">No notifications</div>
              <div className="mt-1 max-w-xs text-12 text-ink-tertiary">
                {filter === "unread"
                  ? "You have no unread notifications right now."
                  : filter === "invitations"
                    ? "You have no pending library invitations."
                    : "Library invitations, system updates, and security alerts will appear here."}
              </div>
            </div>
          ) : (
            filteredNotifications.map((n) => {
              const isInvite =
                n.notification_type.includes("library_invitation") && n.payload?.token;
              const isActionLoading = actionLoadingId === n.id;
              const actionResult = actionMessage?.id === n.id ? actionMessage : null;

              return (
                <div
                  key={n.id}
                  onClick={() => handleMarkRead(n)}
                  className={cn(
                    "p-4 transition-colors cursor-pointer text-left",
                    !n.is_read ? "bg-accent/5 hover:bg-accent/8" : "hover:bg-subtle/70",
                  )}
                >
                  <div className="flex items-start gap-3">
                    <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg border border-border bg-surface">
                      {getNotificationIcon(n.notification_type)}
                    </div>

                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className={cn(
                              "text-13 font-semibold leading-tight",
                              !n.is_read ? "text-ink" : "text-ink-secondary",
                            )}
                          >
                            {n.title}
                          </span>
                          {!n.is_read && (
                            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                          )}
                        </div>
                        <span className="shrink-0 flex items-center gap-1 text-11 text-ink-tertiary">
                          <Clock size={11} />
                          <span>{formatRelativeTime(n.created_at)}</span>
                        </span>
                      </div>

                      <p className="mt-1 text-12 text-ink-secondary leading-relaxed">
                        {n.message}
                      </p>

                      {/* Inline Actions for Library Invitations */}
                      {isInvite && !actionResult && (
                        <div
                          className="mt-3 flex items-center gap-2"
                          onClick={(e) => e.stopPropagation()}
                        >
                          <button
                            type="button"
                            disabled={isActionLoading}
                            onClick={() => handleAcceptInvite(n)}
                            className="inline-flex h-7 items-center justify-center rounded-md bg-accent px-3 text-12 font-semibold text-white shadow-2xs hover:bg-accent/90 disabled:opacity-50 transition-colors"
                          >
                            {isActionLoading ? (
                              <Loader2 size={12} className="animate-spin" />
                            ) : (
                              "Accept"
                            )}
                          </button>
                          <button
                            type="button"
                            disabled={isActionLoading}
                            onClick={() => handleDeclineInvite(n)}
                            className="inline-flex h-7 items-center justify-center rounded-md border border-border bg-surface px-3 text-12 font-medium text-ink-secondary hover:bg-subtle hover:text-ink disabled:opacity-50 transition-colors"
                          >
                            Decline
                          </button>
                        </div>
                      )}

                      {/* Action Result Feedback */}
                      {actionResult && (
                        <div
                          className={cn(
                            "mt-2.5 flex items-center justify-between gap-2 rounded px-2.5 py-1.5 text-12",
                            actionResult.type === "success"
                              ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                              : "bg-rose-500/10 text-rose-700 dark:text-rose-400",
                          )}
                          onClick={(e) => e.stopPropagation()}
                        >
                          <div className="flex items-center gap-1.5">
                            {actionResult.type === "success" ? (
                              <Check size={14} />
                            ) : (
                              <AlertCircle size={14} />
                            )}
                            <span>{actionResult.text}</span>
                          </div>
                          {actionResult.libraryId && (
                            <Link
                              href={`/libraries/${actionResult.libraryId}`}
                              className="font-semibold underline hover:opacity-80 flex items-center gap-1"
                            >
                              <span>View Library</span>
                              <ExternalLink size={12} />
                            </Link>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Preferences Card */}
      <div className="rounded-lg border border-border bg-surface p-6 space-y-4">
        <div>
          <h3 className="text-14 font-semibold text-ink">Communication Channels</h3>
          <p className="mt-0.5 text-12 text-ink-secondary">
            Manage how notifications and transactional emails reach you.
          </p>
        </div>

        <Separator />

        <div className="divide-y divide-border">
          <SettingRow
            label="Library Invitations by Email"
            description="Receive an email notification when invited to view or contribute to a knowledge library."
          >
            <SettingToggle
              checked={emailInvites}
              onCheckedChange={(checked) => {
                setEmailInvites(checked);
                toast(checked ? "Email invitations enabled" : "Email invitations disabled");
              }}
              aria-label="Toggle email invitations"
            />
          </SettingRow>

          <SettingRow
            label="Security & Account Alerts"
            description="Important security notices, such as new logins, email verifications, and access grants."
            badge={{ label: "Recommended", tone: "info" }}
          >
            <SettingToggle
              checked={securityAlerts}
              onCheckedChange={(checked) => {
                setSecurityAlerts(checked);
                toast(checked ? "Security alerts enabled" : "Security alerts disabled");
              }}
              aria-label="Toggle security alerts"
            />
          </SettingRow>

          <SettingRow
            label="In-App Activity Notifications"
            description="Deliver in-platform updates to your notifications inbox when domain events occur."
          >
            <SettingToggle
              checked={inAppAlerts}
              onCheckedChange={(checked) => {
                setInAppAlerts(checked);
                toast(checked ? "In-app alerts enabled" : "In-app alerts disabled");
              }}
              aria-label="Toggle in-app alerts"
            />
          </SettingRow>
        </div>
      </div>
    </div>
  );
}

function formatRelativeTime(isoString: string): string {
  try {
    const date = new Date(isoString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);
    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return "";
  }
}
