"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { ForgotPasswordView } from "@/components/auth/forgot-password-view";
import { LoginForm } from "@/components/auth/login-form";
import { OtpVerificationView } from "@/components/auth/otp-verification-view";
import { SignupForm } from "@/components/auth/signup-form";
import { useAuth } from "@/components/auth/auth-provider";
import { getGoogleAuthUrl, register, resendOtp, verifyEmail } from "@/lib/api/auth";
import { normalizeEmail } from "@/lib/auth/email";
import { setAccess } from "@/lib/auth/token-store";

export type AuthMode = "page" | "modal";

export type AuthInitialView = "login" | "signup";

type AuthView =
  | { kind: "login" }
  | { kind: "signup" }
  | { kind: "verify_email"; email: string }
  | { kind: "forgot" };

/** Unified direct authentication panel with Google, 6-digit OTP, and Password Reset. */
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

  // Listen for Google OAuth popup messages
  useEffect(() => {
    const handleOAuthMessage = (event: MessageEvent) => {
      if (event.data?.type === "MWALIMU_GOOGLE_AUTH_SUCCESS") {
        const { access } = event.data;
        if (access) {
          setAccess(access);
          if (mode === "page") {
            router.replace(redirectTo && redirectTo.startsWith("/") ? redirectTo : "/chat/new");
            router.refresh();
          } else {
            onSuccess?.();
          }
        }
      }
    };
    window.addEventListener("message", handleOAuthMessage);
    return () => window.removeEventListener("message", handleOAuthMessage);
  }, [mode, onSuccess, redirectTo, router]);

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
      const result = await register(normalized, password, confirm);
      setSubmitting(false);
      if (result.requires_verification) {
        setView({ kind: "verify_email", email: normalized });
      } else {
        await login(normalized, password);
        if (mode === "page") {
          router.replace(redirectTo && redirectTo.startsWith("/") ? redirectTo : "/chat/new");
          router.refresh();
        } else {
          onSuccess?.();
        }
      }
    } catch (err) {
      setSubmitting(false);
      setError(
        err instanceof Error && err.message.length > 0
          ? err.message
          : "Account creation failed. Please try again.",
      );
    }
  };

  const handleVerifyEmail = async (otp: string, displayName?: string) => {
    setSubmitting(true);
    setError(null);
    try {
      const result = await verifyEmail(email, otp, displayName);
      setAccess(result.access);
      setSubmitting(false);
      if (mode === "page") {
        router.replace(redirectTo && redirectTo.startsWith("/") ? redirectTo : "/chat/new");
        router.refresh();
      } else {
        onSuccess?.();
      }
    } catch (err) {
      setSubmitting(false);
      setError(
        err instanceof Error && err.message.length > 0
          ? err.message
          : "That verification code isn't correct. Please try again.",
      );
      throw err;
    }
  };

  const handleResendOtp = async () => {
    await resendOtp(email, "email_verification");
  };

  const handleGoogleLogin = async () => {
    try {
      const callbackUrl = `${window.location.origin}/auth/google/callback`;
      const { url } = await getGoogleAuthUrl(callbackUrl);

      // Open popup for seamless OAuth experience
      const width = 540;
      const height = 640;
      const left = window.screen.width / 2 - width / 2;
      const top = window.screen.height / 2 - height / 2;
      window.open(
        url,
        "GoogleSignIn",
        `width=${width},height=${height},top=${top},left=${left},scrollbars=yes`,
      );
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to initiate Google sign-in.",
      );
    }
  };

  let title = "Log in";
  let subtitle = "Enter your email and password to access your learning workspace.";

  switch (view.kind) {
    case "login":
      title = "Log in";
      subtitle = "Access your personalized learning workspace and course materials.";
      break;
    case "signup":
      title = "Create your account";
      subtitle = "Join Mwalimu to explore personalized AI tutors and shared libraries.";
      break;
    case "verify_email":
      title = "Check your email";
      subtitle = "We sent a 6-digit verification code to confirm your email address.";
      break;
    case "forgot":
      title = "Reset password";
      subtitle = "Recover access to your Mwalimu account using a 6-digit code.";
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
          onVerifyEmail={handleVerifyEmail}
          onResendOtp={handleResendOtp}
          onGoogleLogin={handleGoogleLogin}
          onBackToLogin={() => {
            setError(null);
            setView({ kind: "login" });
          }}
          onBackToSignup={() => {
            setError(null);
            setView({ kind: "signup" });
          }}
        />
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
  onVerifyEmail,
  onResendOtp,
  onGoogleLogin,
  onBackToLogin,
  onBackToSignup,
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
  onVerifyEmail: (otp: string, displayName?: string) => Promise<void>;
  onResendOtp: () => Promise<void>;
  onGoogleLogin: () => void;
  onBackToLogin: () => void;
  onBackToSignup: () => void;
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
          onGoogleLogin={onGoogleLogin}
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
          onGoogleSignup={onGoogleLogin}
          submitting={submitting}
          error={error}
        />
      );
    case "verify_email":
      return (
        <OtpVerificationView
          email={view.email || email}
          onVerify={onVerifyEmail}
          onResend={onResendOtp}
          onBack={onBackToSignup}
          submitting={submitting}
          error={error}
        />
      );
    case "forgot":
      return (
        <ForgotPasswordView
          initialEmail={email}
          onBackToLogin={onBackToLogin}
        />
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
