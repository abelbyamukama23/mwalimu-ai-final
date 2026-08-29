"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Loading03Icon } from "hugeicons-react";
import { Button } from "@/components/ui/button";
import { googleAuthCallback } from "@/lib/api/auth";
import { setAccess } from "@/lib/auth/token-store";

function GoogleCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    const oauthError = searchParams.get("error");

    if (oauthError) {
      setError(`Google authorization was cancelled or failed: ${oauthError}`);
      return;
    }

    if (!code || !state) {
      setError("Missing authorization code or state from Google.");
      return;
    }

    const completeOAuth = async () => {
      try {
        const redirectUri = `${window.location.origin}/auth/google/callback`;
        const result = await googleAuthCallback(code, state, redirectUri);

        if (window.opener) {
          // Notify parent window
          window.opener.postMessage(
            {
              type: "MWALIMU_GOOGLE_AUTH_SUCCESS",
              access: result.access,
            },
            window.location.origin,
          );
          window.close();
        } else {
          // Direct redirect
          setAccess(result.access);
          router.replace("/chat/new");
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to complete Google authentication.",
        );
      }
    };

    void completeOAuth();
  }, [router, searchParams]);

  if (error) {
    return (
      <div className="w-full max-w-[420px] space-y-4 rounded-lg border border-border bg-surface p-7 text-center shadow-composer">
        <h2 className="text-16 font-semibold text-danger">Authentication Failed</h2>
        <p className="text-13 text-ink-secondary">{error}</p>
        <Button onClick={() => router.replace("/login")} className="w-full">
          Return to log in
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center space-y-3 p-8">
      <Loading03Icon size={32} className="animate-spin text-accent" />
      <p className="text-14 font-medium text-ink">Completing Google sign-in…</p>
      <p className="text-12 text-ink-tertiary">Establishing your secure Mwalimu session</p>
    </div>
  );
}

export default function GoogleCallbackPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center bg-canvas px-6">
      <Suspense
        fallback={
          <div className="flex flex-col items-center justify-center space-y-3 p-8">
            <Loading03Icon size={32} className="animate-spin text-accent" />
            <p className="text-14 font-medium text-ink">Loading authentication state…</p>
          </div>
        }
      >
        <GoogleCallbackContent />
      </Suspense>
    </div>
  );
}
