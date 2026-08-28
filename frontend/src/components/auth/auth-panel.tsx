"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { LoginForm } from "@/components/auth/login-form";
import { SignupForm } from "@/components/auth/signup-form";
import { useAuth } from "@/components/auth/auth-provider";
import { register } from "@/lib/api/auth";
import { Button } from "@/components/ui/button";
import { normalizeEmail } from "@/lib/auth/email";

export type AuthMode = "page" | "modal";

export type AuthInitialView = "login" | "signup";

type AuthView =
  | { kind: "login" }
  | { kind: "signup" }
  | { kind: "forgot" };

/** Unified direct authentication panel (Single-screen Email + Password login). */
export function AuthPanel({
  mode,
  onSuccess,
  initialEmail = "",
  initialView = "login",
  redirectTo = "/chat/new",
}: {
  mode: AuthMode;
  onSuccess?: () => void;
  initialEmail?: string;
  initialView?: AuthInitialView;
  /** Internal destination used only when hosted as a full page (e.g. /login). */
  redirectTo?: string;
}) {
  const router = useRouter();
  const { login } = useAuth();

  const [view, setView] = useState<AuthView>(() => {
    if (initialView === "signup") return { kind: "signup" };
    return { kind: "login" };
  });
  const [email, setEmail] = useState(normalizeEmail(initialEmail));
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLogin = async (loginEmail: string, password: string) => {
    const normalized = normalizeEmail(loginEmail);
    setEmail(normalized);
    setSubmitting(true);
    setError(null);
    try {
      await login(normalized, password);
    } catch (err) {
      setSubmitting(false);
      setError(
        err instanceof Error && err.message.length > 0
          ? err.message
          : "Sign-in failed. Please check your email and password.",
      );
      return;
    }
    setSubmitting(false);
    if (mode === "page") {
      router.replace(redirectTo && redirectTo.startsWith("/") ? redirectTo : "/chat/new");
      router.refresh();
    } else {
      onSuccess?.();
    }
  };

  const handleSignup = async (
    signupEmail: string,
    password: string,
    confirm: string,
  ) => {
    const normalized = normalizeEmail(signupEmail);
    setEmail(normalized);
    setError(null);
    setSubmitting(true);
    try {
      await register(normalized, password, confirm);
      await login(normalized, password);
    } catch (err) {
      setSubmitting(false);
      setError(
        err instanceof Error && err.message.length > 0
          ? err.message
          : "Account creation failed. Please try again.",
      );
      return;
    }
    setSubmitting(false);
    if (mode === "page") {
      router.replace(redirectTo && redirectTo.startsWith("/") ? redirectTo : "/chat/new");
      router.refresh();
    } else {
      onSuccess?.();
    }
  };

  let title = "Log in";
  let subtitle = "Enter your email and password to access your learning workspace.";

  switch (view.kind) {
    case "login":
      title = "Log in";
      subtitle = "Enter your email and password to access your learning workspace.";
      break;
    case "signup":
      title = "Create your account";
      subtitle = "Join Mwalimu to explore personalized AI tutors and shared libraries.";
      break;
    case "forgot":
      title = "Reset password";
      subtitle = "Password recovery instructions will be provided here.";
      break;
  }

  return (
    <div className={mode === "page" ? "flex min-h-dvh items-center justify-center bg-canvas px-6" : ""}>
      <div
        className={
          mode === "page"
            ? "w-full max-w-[420px] rounded-lg border border-border bg-surface p-7 shadow-composer"
            : "w-full max-w-[420px]"
        }
      >
        {/* Brand mark */}
        <div className="mb-6 flex items-center justify-center gap-2">
          <span aria-hidden className="h-8 w-8 rounded-sm bg-accent" />
          <span className="text-17 font-semibold text-ink">Mwalimu</span>
        </div>

        <div className="mb-6">
          <PanelHeading mode={mode}>{title}</PanelHeading>
          <PanelSubtitle mode={mode}>{subtitle}</PanelSubtitle>
        </div>

        <AuthBody
          email={email}
          onChangeEmail={setEmail}
          view={view}
          submitting={submitting}
          error={error}
          onForgot={() => setView({ kind: "forgot" })}
          onToSignup={() => {
            setError(null);
            setView({ kind: "signup" });
          }}
          onLogin={handleLogin}
          onSignup={handleSignup}
          onBackToLogin={() => {
            setError(null);
            setView({ kind: "login" });
          }}
        />

        {mode === "page" && (
          <p className="mt-6 text-center text-12 leading-relaxed text-ink-tertiary">
            Mwalimu works without an institution — discover and join institutions later to
            unlock shared resources.
          </p>
        )}
      </div>
    </div>
  );
}

function AuthBody({
  email,
  onChangeEmail,
  view,
  submitting,
  error,
  onForgot,
  onToSignup,
  onLogin,
  onSignup,
  onBackToLogin,
}: {
  email: string;
  onChangeEmail: (email: string) => void;
  view: AuthView;
  submitting: boolean;
  error: string | null;
  onForgot: () => void;
  onToSignup: () => void;
  onLogin: (email: string, password: string) => void;
  onSignup: (email: string, password: string, confirm: string) => void;
  onBackToLogin: () => void;
}) {
  switch (view.kind) {
    case "login":
      return (
        <LoginForm
          email={email}
          onChangeEmail={onChangeEmail}
          onForgot={onForgot}
          onSignup={onToSignup}
          onSubmit={onLogin}
          submitting={submitting}
          error={error}
        />
      );
    case "signup":
      return (
        <SignupForm
          email={email}
          onChangeEmail={onChangeEmail}
          onLogin={onBackToLogin}
          onSubmit={onSignup}
          submitting={submitting}
          error={error}
        />
      );
    case "forgot":
      return (
        <div className="space-y-5">
          <p className="text-13 leading-relaxed text-ink-secondary">
            Self-service password recovery will be available in an upcoming update. Please contact your institution administrator if you need your password reset.
          </p>
          <Button variant="secondary" className="w-full" onClick={onBackToLogin}>
            Back to log in
          </Button>
        </div>
      );
    default:
      return null;
  }
}

function PanelHeading({ mode, children }: { mode: AuthMode; children: ReactNode }) {
  if (mode === "modal") {
    return (
      <DialogPrimitive.Title className="text-17 font-semibold text-ink">
        {children}
      </DialogPrimitive.Title>
    );
  }
  return <h1 className="text-17 font-semibold text-ink">{children}</h1>;
}

function PanelSubtitle({ mode, children }: { mode: AuthMode; children: ReactNode }) {
  if (mode === "modal") {
    return (
      <DialogPrimitive.Description className="mt-1 text-13 text-ink-secondary">
        {children}
      </DialogPrimitive.Description>
    );
  }
  return <p className="mt-1 text-13 text-ink-secondary">{children}</p>;
}
