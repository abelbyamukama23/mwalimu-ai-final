"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/components/auth/auth-provider";

function AuthSplash() {
  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-3 bg-canvas">
      <span aria-hidden className="h-9 w-9 animate-pulse rounded-sm bg-accent" />
      <p className="text-13 text-ink-tertiary">Mwalimu</p>
    </div>
  );
}

/**
 * Protects the generic application. While the session is being resolved it shows
 * a branded splash (no unauthenticated content flash); if the session is invalid
 * it redirects to the sign-in page.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "unauthenticated") {
      router.replace("/login");
    }
  }, [status, router]);

  if (status === "authenticated") return <>{children}</>;

  return <AuthSplash />;
}
