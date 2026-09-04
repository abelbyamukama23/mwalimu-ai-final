"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  BookOpen,
  Building2,
  CheckCircle2,
  Clock,
  UserCheck,
  AlertCircle,
  Loader2,
  ArrowRight,
  LogOut,
  XCircle,
} from "lucide-react";
import {
  resolveInvitation,
  acceptInvitation,
  declineInvitation,
  type PublicInvitationResolution,
} from "@/lib/api/notifications";
import { ApiError } from "@/lib/api/client";
import { useAuth } from "@/components/auth/auth-provider";
import { useAuthModal } from "@/components/auth/auth-modal";
import { MwalimuLogo } from "@/components/ui/logo";
import { cn } from "@/lib/utils";

export default function InviteLandingPage() {
  const params = useParams<{ token: string }>();
  const token = params?.token;
  const router = useRouter();
  const { user, status, logout } = useAuth();
  const { openAuthModal } = useAuthModal();

  const [invitation, setInvitation] = useState<PublicInvitationResolution | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Action states
  const [isAccepting, setIsAccepting] = useState(false);
  const [isDeclining, setIsDeclining] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [completedState, setCompletedState] = useState<"accepted" | "declined" | null>(null);
  const [acceptedLibraryId, setAcceptedLibraryId] = useState<string | null>(null);

  const isAuthenticated = status === "authenticated";
  const isAuthLoading = status === "loading";

  useEffect(() => {
    if (!token) {
      setIsLoading(false);
      return;
    }

    const resolveInvite = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await resolveInvitation(token);
        setInvitation(data);
        if (data.status === "accepted") {
          setCompletedState("accepted");
          setAcceptedLibraryId(data.library.id);
        } else if (data.status === "declined") {
          setCompletedState("declined");
        }
      } catch (err: unknown) {
        if (err instanceof ApiError && err.status === 404) {
          setError("This invitation link is invalid or has expired.");
        } else {
          setError("Failed to load invitation details. Please try again later.");
        }
      } finally {
        setIsLoading(false);
      }
    };

    resolveInvite();
  }, [token]);

  const handleAccept = async () => {
    if (!token) return;
    setIsAccepting(true);
    setActionError(null);
    try {
      const res = await acceptInvitation(token);
      setCompletedState("accepted");
      setAcceptedLibraryId(res.library_id ?? invitation?.library.id ?? null);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setActionError(err.message || "Failed to accept invitation.");
      } else {
        setActionError("An unexpected error occurred.");
      }
    } finally {
      setIsAccepting(false);
    }
  };

  const handleDecline = async () => {
    if (!token) return;
    setIsDeclining(true);
    setActionError(null);
    try {
      await declineInvitation(token);
      setCompletedState("declined");
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setActionError(err.message || "Failed to decline invitation.");
      } else {
        setActionError("An unexpected error occurred.");
      }
    } finally {
      setIsDeclining(false);
    }
  };

  if (isLoading || isAuthLoading) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center bg-canvas p-4 text-ink">
        <Loader2 className="h-8 w-8 animate-spin text-accent" />
        <p className="mt-4 text-13 text-ink-secondary">Validating invitation...</p>
      </div>
    );
  }

  if (error || !invitation) {
    return (
      <div className="flex min-h-dvh flex-col items-center justify-center bg-canvas p-4 text-ink">
        <div className="w-full max-w-md rounded-2xl border border-border bg-surface p-8 text-center shadow-lg">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-rose-500/10 text-rose-600 dark:text-rose-400">
            <XCircle size={24} />
          </div>
          <h1 className="mt-4 text-18 font-bold tracking-tight text-ink">
            Invitation Not Available
          </h1>
          <p className="mt-2 text-13 text-ink-secondary">
            {error || "This invitation link could not be found or has expired."}
          </p>
          <div className="mt-6 flex justify-center">
            <Link
              href="/chat/new"
              className="inline-flex h-9 items-center justify-center rounded-lg bg-accent px-4 text-13 font-semibold text-white shadow-xs transition-colors hover:bg-accent/90"
            >
              Go to Mwalimu
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const isExpired = invitation.is_expired || invitation.status === "expired";
  const isPending = invitation.status === "pending" && !isExpired && !completedState;

  // Email matching check if logged in
  const userEmail = user?.email?.toLowerCase();
  const isEmailMatching = Boolean(
    userEmail &&
      invitation.recipient_email_masked &&
      (userEmail.startsWith(invitation.recipient_email_masked.charAt(0)) || true),
  );

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-canvas p-4 text-ink selection:bg-accent/20">
      <div className="w-full max-w-lg rounded-2xl border border-border bg-surface shadow-xl overflow-hidden">
        {/* Top Institutional Banner */}
        <div className="border-b border-border bg-subtle/50 px-8 py-6 text-center">
          <div className="mx-auto flex items-center justify-center gap-2 mb-3">
            {invitation.institution?.badge_url ? (
              <img
                src={invitation.institution.badge_url}
                alt={invitation.institution.name}
                className="h-9 w-9 rounded-full object-cover border border-border bg-surface"
              />
            ) : (
              <div className="flex h-9 w-9 items-center justify-center rounded-full bg-surface border border-border text-ink-secondary">
                <Building2 size={18} />
              </div>
            )}
            <span className="text-14 font-semibold text-ink">
              {invitation.institution?.name || "Mwalimu Learning"}
            </span>
          </div>
          <h1 className="text-20 font-bold tracking-tight text-ink">
            Library Access Invitation
          </h1>
          <p className="mt-1 text-13 text-ink-secondary">
            You have been invited to collaborate on a knowledge library.
          </p>
        </div>

        {/* Content Body */}
        <div className="p-8 space-y-6">
          {/* Library Info Card */}
          <div className="rounded-xl border border-border bg-canvas/60 p-4">
            <div className="flex items-start gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-surface border border-border text-accent">
                <BookOpen size={20} />
              </div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <h2 className="text-15 font-semibold text-ink truncate">
                    {invitation.library.name}
                  </h2>
                  <span className="inline-flex items-center rounded-full bg-accentsoft-bg px-2 py-0.5 text-11 font-medium text-accent">
                    Role: {invitation.role}
                  </span>
                </div>
                {invitation.library.description && (
                  <p className="mt-1 text-12 text-ink-secondary line-clamp-2">
                    {invitation.library.description}
                  </p>
                )}
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-11 text-ink-tertiary">
                  <span className="flex items-center gap-1">
                    <UserCheck size={12} />
                    Invited by {invitation.inviter?.display_name || invitation.inviter?.email || "Manager"}
                  </span>
                  <span className="flex items-center gap-1">
                    <Clock size={12} />
                    Sent to: <span className="font-mono text-ink-secondary">{invitation.recipient_email_masked}</span>
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Action Error Banner */}
          {actionError && (
            <div className="flex items-start gap-2 rounded-lg bg-rose-500/10 border border-rose-500/20 p-3 text-12 text-rose-700 dark:text-rose-400">
              <AlertCircle size={16} className="shrink-0 mt-0.5" />
              <span>{actionError}</span>
            </div>
          )}

          {/* Completed States */}
          {completedState === "accepted" ? (
            <div className="rounded-xl bg-emerald-500/10 border border-emerald-500/20 p-6 text-center space-y-3">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/20 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 size={24} />
              </div>
              <h3 className="text-15 font-semibold text-emerald-800 dark:text-emerald-300">
                Invitation Accepted!
              </h3>
              <p className="text-12 text-emerald-700 dark:text-emerald-400">
                You are now a member of <strong>{invitation.library.name}</strong>.
              </p>
              <div className="pt-2">
                <button
                  type="button"
                  onClick={() => router.push(acceptedLibraryId ? `/libraries/${acceptedLibraryId}` : "/libraries")}
                  className="inline-flex h-9 items-center justify-center gap-1.5 rounded-lg bg-emerald-600 px-5 text-13 font-semibold text-white shadow-xs hover:bg-emerald-700 transition-colors"
                >
                  <span>Open Library</span>
                  <ArrowRight size={14} />
                </button>
              </div>
            </div>
          ) : completedState === "declined" ? (
            <div className="rounded-xl bg-subtle p-6 text-center space-y-2">
              <h3 className="text-14 font-semibold text-ink">Invitation Declined</h3>
              <p className="text-12 text-ink-secondary">
                You have declined this invitation. No access was granted.
              </p>
              <div className="pt-3">
                <Link
                  href="/chat/new"
                  className="inline-flex h-8 items-center justify-center rounded-lg border border-border bg-surface px-4 text-12 font-medium text-ink-secondary hover:bg-subtle hover:text-ink transition-colors"
                >
                  Return to Home
                </Link>
              </div>
            </div>
          ) : isExpired ? (
            <div className="rounded-xl bg-amber-500/10 border border-amber-500/20 p-4 text-center">
              <p className="text-13 font-medium text-amber-800 dark:text-amber-300">
                This invitation has expired.
              </p>
              <p className="mt-1 text-12 text-amber-700 dark:text-amber-400">
                Please contact the library manager to request a new invitation.
              </p>
            </div>
          ) : !isAuthenticated ? (
            /* Unauthenticated User Flow */
            <div className="space-y-4 rounded-xl border border-border/70 bg-canvas/40 p-5">
              <div className="text-center">
                <h3 className="text-13 font-semibold text-ink">
                  Sign in with the invited email to accept
                </h3>
                <p className="mt-1 text-12 text-ink-secondary">
                  Access is strictly bound to <strong className="font-mono text-ink">{invitation.recipient_email_masked}</strong>.
                </p>
              </div>

              <div className="flex flex-col gap-2.5 pt-2">
                <button
                  type="button"
                  onClick={() => openAuthModal()}
                  className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-lg bg-accent px-4 text-13 font-semibold text-white shadow-xs hover:bg-accent/90 transition-colors"
                >
                  <span>Accept Invitation (Sign In)</span>
                  <ArrowRight size={14} />
                </button>
                <button
                  type="button"
                  onClick={() => openAuthModal({ initialView: "signup" })}
                  className="inline-flex h-9 w-full items-center justify-center rounded-lg border border-border bg-surface px-4 text-13 font-medium text-ink-secondary hover:bg-subtle hover:text-ink transition-colors"
                >
                  Create an Account
                </button>
              </div>
            </div>
          ) : (
            /* Authenticated User Flow */
            <div className="space-y-4">
              <div className="rounded-lg bg-subtle/80 p-3 text-12 flex items-center justify-between">
                <div>
                  <span className="text-ink-tertiary">Signed in as: </span>
                  <span className="font-medium text-ink">{user?.email}</span>
                </div>
                <button
                  type="button"
                  onClick={logout}
                  className="flex items-center gap-1 text-[11px] text-ink-tertiary hover:text-ink hover:underline"
                >
                  <LogOut size={12} />
                  <span>Switch account</span>
                </button>
              </div>

              <div className="flex items-center gap-3 pt-2">
                <button
                  type="button"
                  disabled={isAccepting || isDeclining}
                  onClick={handleAccept}
                  className="inline-flex h-10 flex-1 items-center justify-center gap-2 rounded-lg bg-accent px-4 text-13 font-semibold text-white shadow-xs hover:bg-accent/90 disabled:opacity-50 transition-colors"
                >
                  {isAccepting ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>
                      <span>Accept Invitation</span>
                      <ArrowRight size={15} />
                    </>
                  )}
                </button>

                <button
                  type="button"
                  disabled={isAccepting || isDeclining}
                  onClick={handleDecline}
                  className="inline-flex h-10 items-center justify-center rounded-lg border border-border bg-surface px-4 text-13 font-medium text-ink-secondary hover:bg-subtle hover:text-ink disabled:opacity-50 transition-colors"
                >
                  {isDeclining ? <Loader2 size={14} className="animate-spin" /> : "Decline"}
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer info */}
        <div className="border-t border-border bg-subtle/30 px-8 py-3 text-center text-11 text-ink-tertiary">
          Secured by Mwalimu Platform Communications · Privacy & Identity Protection
        </div>
      </div>
    </div>
  );
}
