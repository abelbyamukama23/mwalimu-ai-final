"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bell,
  Check,
  CheckCheck,
  Clock,
  ExternalLink,
  Shield,
  BookOpen,
  UserCheck,
  X,
  AlertCircle,
  Loader2,
  Mail,
} from "lucide-react";
import { useAuth } from "@/components/auth/auth-provider";
import { useAuthModal } from "@/components/auth/auth-modal";
import {
  listNotifications,
  getUnreadNotificationCount,
  markNotificationAsRead,
  markAllNotificationsAsRead,
  acceptInvitation,
  declineInvitation,
  type PlatformNotification,
} from "@/lib/api/notifications";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface NotificationCenterProps {
  align?: "start" | "center" | "end";
  side?: "top" | "bottom" | "left" | "right";
  className?: string;
  triggerClassName?: string;
  showLabel?: boolean;
}

export function NotificationCenter({
  align = "end",
  side = "bottom",
  className,
  triggerClassName,
  showLabel = false,
}: NotificationCenterProps) {
  const router = useRouter();
  const { status } = useAuth();
  const { openAuthModal } = useAuthModal();

  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<PlatformNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [actionMessage, setActionMessage] = useState<{
    id: string;
    text: string;
    type: "success" | "error";
    libraryId?: string;
  } | null>(null);

  const isAuthenticated = status === "authenticated";

  const fetchUnreadCount = async () => {
    if (!isAuthenticated) return;
    try {
      const res = await getUnreadNotificationCount();
      setUnreadCount(res.unread_count);
    } catch {
      // Ignore background refresh errors
    }
  };

  const fetchNotifications = async () => {
    if (!isAuthenticated) return;
    setIsLoading(true);
    try {
      const res = await listNotifications();
      setNotifications(res.results);
      const unread = res.results.filter((n) => !n.is_read).length;
      setUnreadCount(unread);
    } catch {
      // Handle gracefully
    } finally {
      setIsLoading(false);
    }
  };

  // Poll for unread count every 30s when authenticated
  useEffect(() => {
    if (!isAuthenticated) {
      setUnreadCount(0);
      setNotifications([]);
      return;
    }

    fetchUnreadCount();
    const interval = setInterval(fetchUnreadCount, 30000);
    return () => clearInterval(interval);
  }, [isAuthenticated]);

  // Fetch full notification list when popover opens
  useEffect(() => {
    if (isOpen && isAuthenticated) {
      fetchNotifications();
    }
  }, [isOpen, isAuthenticated]);

  const handleTriggerClick = (e: React.MouseEvent) => {
    if (!isAuthenticated) {
      e.preventDefault();
      openAuthModal();
    }
  };

  const handleMarkRead = async (notification: PlatformNotification) => {
    if (notification.is_read) return;
    try {
      await markNotificationAsRead(notification.id);
      setNotifications((prev) =>
        prev.map((n) => (n.id === notification.id ? { ...n, is_read: true } : n)),
      );
      setUnreadCount((c) => Math.max(0, c - 1));
    } catch {
      // Ignore
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsAsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      // Ignore
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

  // Group notifications into Today vs Earlier
  const today = new Date().toDateString();
  const todayNotifications = notifications.filter(
    (n) => new Date(n.created_at).toDateString() === today,
  );
  const earlierNotifications = notifications.filter(
    (n) => new Date(n.created_at).toDateString() !== today,
  );

  const getNotificationIcon = (type: string) => {
    if (type.includes("library_invitation")) {
      return <BookOpen size={14} className="text-accent" />;
    }
    if (type.includes("security") || type.includes("auth")) {
      return <Shield size={14} className="text-amber-500" />;
    }
    if (type.includes("member")) {
      return <UserCheck size={14} className="text-indigo-500" />;
    }
    return <Mail size={14} className="text-ink-secondary" />;
  };

  return (
    <Popover open={isOpen} onOpenChange={setIsOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          onClick={handleTriggerClick}
          aria-label="Notifications"
          className={cn(
            "focus-ring relative flex items-center justify-center rounded-sm transition-colors duration-150",
            showLabel
              ? "w-full gap-2.5 px-3 py-2 text-14 text-ink-secondary hover:bg-subtle hover:text-ink"
              : "h-9 w-9 text-ink-tertiary hover:bg-subtle hover:text-ink",
            triggerClassName,
          )}
        >
          <div className="relative">
            <Bell size={18} aria-hidden />
            {unreadCount > 0 && (
              <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-bold text-white shadow-xs">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </div>
          {showLabel && (
            <span className="flex-1 truncate text-left">Notifications</span>
          )}
          {showLabel && unreadCount > 0 && (
            <span className="rounded-full bg-accentsoft-bg px-2 py-0.5 text-11 font-medium text-accentsoft-fg">
              {unreadCount}
            </span>
          )}
        </button>
      </PopoverTrigger>

      <PopoverContent
        align={align}
        side={side}
        sideOffset={6}
        className={cn(
          "w-84 sm:w-96 rounded-xl border border-border bg-surface p-0 text-ink shadow-xl overflow-hidden",
          className,
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border bg-surface px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-13 font-semibold text-ink">Notifications</span>
            {unreadCount > 0 && (
              <span className="rounded-full bg-accentsoft-bg px-2 py-0.5 text-11 font-medium text-accent">
                {unreadCount} new
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={handleMarkAllRead}
                className="flex items-center gap-1 text-12 font-medium text-accent transition-colors hover:underline"
              >
                <CheckCheck size={14} />
                <span>Mark all read</span>
              </button>
            )}
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              aria-label="Close notifications"
              className="rounded p-1 text-ink-tertiary transition-colors hover:bg-subtle hover:text-ink"
            >
              <X size={15} />
            </button>
          </div>
        </div>

        {/* List Content */}
        <div className="max-h-[380px] divide-y divide-border/60 overflow-y-auto">
          {isLoading && notifications.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-13 text-ink-tertiary">
              <Loader2 size={16} className="mr-2 animate-spin text-accent" />
              Loading updates...
            </div>
          ) : notifications.length === 0 ? (
            <div className="flex flex-col items-center justify-center px-4 py-10 text-center">
              <div className="mb-2.5 flex h-10 w-10 items-center justify-center rounded-full bg-subtle text-ink-tertiary">
                <Bell size={18} />
              </div>
              <div className="text-13 font-medium text-ink">No notifications yet</div>
              <div className="mt-1 max-w-[220px] text-12 text-ink-tertiary">
                Library invitations and updates will appear here.
              </div>
            </div>
          ) : (
            <>
              {/* Today Section */}
              {todayNotifications.length > 0 && (
                <div>
                  <div className="bg-canvas/60 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-tertiary">
                    Today
                  </div>
                  {todayNotifications.map((n) => renderNotificationItem(n))}
                </div>
              )}

              {/* Earlier Section */}
              {earlierNotifications.length > 0 && (
                <div>
                  <div className="bg-canvas/60 px-4 py-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-tertiary">
                    Earlier
                  </div>
                  {earlierNotifications.map((n) => renderNotificationItem(n))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border bg-surface px-4 py-2 text-12 text-ink-tertiary">
          <span>Mwalimu Communications</span>
          <Link
            href="/libraries"
            onClick={() => setIsOpen(false)}
            className="flex items-center gap-1 font-medium text-accent transition-colors hover:underline"
          >
            <span>My Libraries</span>
            <ExternalLink size={12} />
          </Link>
        </div>
      </PopoverContent>
    </Popover>
  );

  function renderNotificationItem(n: PlatformNotification) {
    const isInvite =
      n.notification_type.includes("library_invitation") && n.payload?.token;
    const isActionLoading = actionLoadingId === n.id;
    const actionResult = actionMessage?.id === n.id ? actionMessage : null;

    return (
      <div
        key={n.id}
        onClick={() => handleMarkRead(n)}
        className={cn(
          "cursor-pointer p-3.5 text-left transition-colors",
          !n.is_read ? "bg-accent/5 hover:bg-accent/8" : "hover:bg-subtle",
        )}
      >
        <div className="flex items-start gap-2.5">
          <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border bg-surface">
            {getNotificationIcon(n.notification_type)}
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between gap-1">
              <span
                className={cn(
                  "truncate text-13 font-semibold leading-tight",
                  !n.is_read ? "text-ink" : "text-ink-secondary",
                )}
              >
                {n.title}
              </span>
              {!n.is_read && (
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-accent" />
              )}
            </div>

            <p className="mt-1 line-clamp-2 text-12 leading-snug text-ink-secondary">
              {n.message}
            </p>

            {/* Inline Action for Library Invitations */}
            {isInvite && !actionResult && (
              <div
                className="mt-2.5 flex items-center gap-2"
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  disabled={isActionLoading}
                  onClick={() => handleAcceptInvite(n)}
                  className="inline-flex h-6 items-center justify-center rounded-md bg-accent px-2.5 text-11 font-semibold text-white shadow-2xs transition-colors hover:bg-accent/90 disabled:opacity-50"
                >
                  {isActionLoading ? (
                    <Loader2 size={11} className="animate-spin" />
                  ) : (
                    "Accept"
                  )}
                </button>
                <button
                  type="button"
                  disabled={isActionLoading}
                  onClick={() => handleDeclineInvite(n)}
                  className="inline-flex h-6 items-center justify-center rounded-md border border-border bg-surface px-2.5 text-11 font-medium text-ink-secondary transition-colors hover:bg-subtle hover:text-ink disabled:opacity-50"
                >
                  Decline
                </button>
              </div>
            )}

            {/* Action Feedback Message */}
            {actionResult && (
              <div
                className={cn(
                  "mt-2 flex items-center justify-between gap-1.5 rounded px-2 py-1 text-11",
                  actionResult.type === "success"
                    ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                    : "bg-rose-500/10 text-rose-700 dark:text-rose-400",
                )}
                onClick={(e) => e.stopPropagation()}
              >
                <div className="flex items-center gap-1.5">
                  {actionResult.type === "success" ? (
                    <Check size={12} />
                  ) : (
                    <AlertCircle size={12} />
                  )}
                  <span>{actionResult.text}</span>
                </div>
                {actionResult.libraryId && (
                  <button
                    type="button"
                    onClick={() => {
                      setIsOpen(false);
                      router.push(`/libraries/${actionResult.libraryId}`);
                    }}
                    className="font-semibold underline hover:opacity-80"
                  >
                    View Library
                  </button>
                )}
              </div>
            )}

            {/* Timestamp */}
            <div className="mt-1.5 flex items-center gap-1 text-[11px] text-ink-tertiary">
              <Clock size={11} />
              <span>{formatRelativeTime(n.created_at)}</span>
            </div>
          </div>
        </div>
      </div>
    );
  }
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
