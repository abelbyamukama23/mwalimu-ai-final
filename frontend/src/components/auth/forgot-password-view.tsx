"use client";

import { useEffect, useState } from "react";
import {
  ArrowLeft01Icon,
  CheckmarkCircle01Icon,
  Loading03Icon,
  Mail01Icon,
  ViewIcon,
  ViewOffIcon,
} from "hugeicons-react";
import { OtpInput } from "@/components/auth/otp-input";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { confirmPasswordReset, requestPasswordReset } from "@/lib/api/auth";
import { isValidEmail, normalizeEmail } from "@/lib/auth/email";

interface ForgotPasswordViewProps {
  initialEmail?: string;
  onBackToLogin: () => void;
}

export function ForgotPasswordView({
  initialEmail = "",
  onBackToLogin,
}: ForgotPasswordViewProps) {
  const [step, setStep] = useState<"request" | "verify" | "success">("request");
  const [email, setEmail] = useState(normalizeEmail(initialEmail));
  const [otp, setOtp] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cooldown, setCooldown] = useState(60);
  const [resending, setResending] = useState(false);

  useEffect(() => {
    if (step !== "verify" || cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [step, cooldown]);

  const handleRequestSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValidEmail(email) || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await requestPasswordReset(email);
      setStep("verify");
      setCooldown(60);
    } catch {
      // Neutral error fallback
      setStep("verify");
      setCooldown(60);
    } finally {
      setSubmitting(false);
    }
  };

  const handleResend = async () => {
    if (cooldown > 0 || resending) return;
    setResending(true);
    setError(null);
    try {
      await requestPasswordReset(email);
      setCooldown(60);
      setOtp("");
    } catch {
      setCooldown(60);
    } finally {
      setResending(false);
    }
  };

  const handleResetSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (otp.length !== 6 || !password || password !== confirm || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await confirmPasswordReset(email, otp, password, confirm);
      setStep("success");
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Could not reset password. Please check your verification code.";
      setError(msg);
    } finally {
      setSubmitting(false);
    }
  };

  if (step === "success") {
    return (
      <div className="space-y-5 text-center">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-50 text-emerald-600">
          <CheckmarkCircle01Icon size={24} />
        </div>
        <div>
          <h3 className="text-16 font-semibold text-ink">Password updated</h3>
          <p className="mt-1 text-13 text-ink-secondary">
            Your password has been successfully reset. You can now log in with your new credentials.
          </p>
        </div>
        <Button onClick={onBackToLogin} className="w-full">
          Log in with new password
        </Button>
      </div>
    );
  }

  if (step === "verify") {
    return (
      <form onSubmit={handleResetSubmit} className="space-y-4">
        <div className="flex items-center justify-between rounded-lg border border-border/80 bg-surface-muted px-3.5 py-2.5">
          <div className="flex items-center gap-2 overflow-hidden">
            <Mail01Icon size={16} className="shrink-0 text-accent" />
            <span className="truncate text-13 font-medium text-ink">{email}</span>
          </div>
          <button
            type="button"
            onClick={() => setStep("request")}
            className="shrink-0 text-12 font-medium text-accent hover:underline"
          >
            Change
          </button>
        </div>

        <div className="space-y-2">
          <label className="block text-13 font-medium text-ink">
            6-digit reset code
          </label>
          <OtpInput
            value={otp}
            onChange={setOtp}
            disabled={submitting}
            hasError={Boolean(error)}
          />
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reset-password" className="block text-13 font-medium text-ink">
            New password
          </label>
          <div className="relative">
            <Input
              id="reset-password"
              type={showPassword ? "text" : "password"}
              required
              placeholder="Enter new password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              className="pr-11 text-13"
            />
            <IconButton
              type="button"
              size="sm"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              {showPassword ? <ViewOffIcon size={16} /> : <ViewIcon size={16} />}
            </IconButton>
          </div>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="reset-confirm" className="block text-13 font-medium text-ink">
            Confirm new password
          </label>
          <div className="relative">
            <Input
              id="reset-confirm"
              type={showConfirm ? "text" : "password"}
              required
              placeholder="Confirm new password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              disabled={submitting}
              className="pr-11 text-13"
            />
            <IconButton
              type="button"
              size="sm"
              aria-label={showConfirm ? "Hide password" : "Show password"}
              onClick={() => setShowConfirm((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              {showConfirm ? <ViewOffIcon size={16} /> : <ViewIcon size={16} />}
            </IconButton>
          </div>
        </div>

        {error && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-12 font-medium text-red-700">
            {error}
          </p>
        )}

        <Button
          type="submit"
          className="w-full"
          disabled={otp.length !== 6 || !password || password !== confirm || submitting}
        >
          {submitting ? (
            <>
              <Loading03Icon size={16} className="mr-2 animate-spin" />
              Resetting password…
            </>
          ) : (
            "Reset password"
          )}
        </Button>

        <div className="flex items-center justify-between pt-1 text-12">
          <button
            type="button"
            onClick={onBackToLogin}
            className="inline-flex items-center gap-1 text-ink-secondary hover:text-ink"
          >
            <ArrowLeft01Icon size={14} />
            Back to log in
          </button>

          {cooldown > 0 ? (
            <span className="text-ink-tertiary">
              Resend code in <strong className="font-medium text-ink-secondary">{cooldown}s</strong>
            </span>
          ) : (
            <button
              type="button"
              disabled={resending}
              onClick={handleResend}
              className="font-medium text-accent hover:underline disabled:opacity-50"
            >
              {resending ? "Sending code…" : "Resend code"}
            </button>
          )}
        </div>
      </form>
    );
  }

  return (
    <form onSubmit={handleRequestSubmit} className="space-y-4">
      <div>
        <label htmlFor="reset-email" className="mb-1.5 block text-13 font-medium text-ink">
          Email address
        </label>
        <Input
          id="reset-email"
          type="email"
          autoComplete="email"
          required
          autoFocus
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={submitting}
          className="text-13"
        />
      </div>

      <Button
        type="submit"
        className="w-full"
        disabled={!isValidEmail(email) || submitting}
      >
        {submitting ? (
          <>
            <Loading03Icon size={16} className="mr-2 animate-spin" />
            Sending code…
          </>
        ) : (
          "Send reset code"
        )}
      </Button>

      <div className="text-center pt-2">
        <button
          type="button"
          onClick={onBackToLogin}
          className="text-13 text-accent hover:underline"
        >
          Remember your password? Log in
        </button>
      </div>
    </form>
  );
}
