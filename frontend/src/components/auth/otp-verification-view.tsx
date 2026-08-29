"use client";

import { useEffect, useState } from "react";
import { ArrowLeft01Icon, Loading03Icon, Mail01Icon } from "hugeicons-react";
import { OtpInput } from "@/components/auth/otp-input";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface OtpVerificationViewProps {
  email: string;
  onVerify: (otp: string, displayName?: string) => Promise<void>;
  onResend: () => Promise<void>;
  onBack: () => void;
  submitting?: boolean;
  error?: string | null;
}

export function OtpVerificationView({
  email,
  onVerify,
  onResend,
  onBack,
  submitting = false,
  error = null,
}: OtpVerificationViewProps) {
  const [otp, setOtp] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [cooldown, setCooldown] = useState(60);
  const [resending, setResending] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);

  // 60-second countdown timer
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((prev) => prev - 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const handleResend = async () => {
    if (cooldown > 0 || resending) return;
    setResending(true);
    setLocalError(null);
    try {
      await onResend();
      setCooldown(60);
      setOtp("");
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Could not send a new verification code. Please try again.";
      setLocalError(msg);
    } finally {
      setResending(false);
    }
  };

  const handleSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (otp.length !== 6 || submitting) return;
    setLocalError(null);
    try {
      await onVerify(otp, displayName.trim());
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "That code isn't correct. Please try again.";
      setLocalError(msg);
    }
  };

  const activeError = error || localError;

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      {/* Email badge */}
      <div className="flex items-center justify-between rounded-lg border border-border/80 bg-surface-muted px-3.5 py-2.5">
        <div className="flex items-center gap-2 overflow-hidden">
          <Mail01Icon size={16} className="shrink-0 text-accent" />
          <span className="truncate text-13 font-medium text-ink">{email}</span>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="shrink-0 text-12 font-medium text-[#0d7a68] transition-colors hover:text-[#0a6657] hover:underline"
        >
          Change
        </button>

      </div>

      {/* 6-digit OTP Input */}
      <div className="space-y-2">
        <label className="block text-13 font-medium text-ink">
          6-digit verification code
        </label>
        <OtpInput
          value={otp}
          onChange={setOtp}
          disabled={submitting}
          hasError={Boolean(activeError)}
          onComplete={() => handleSubmit()}
        />
      </div>

      {/* Display name prompt */}
      <div className="space-y-1.5 pt-1">
        <label htmlFor="auth-display-name" className="block text-13 font-medium text-ink">
          What should Mwalimu call you? <span className="font-normal text-ink-tertiary">(optional)</span>
        </label>
        <Input
          id="auth-display-name"
          type="text"
          placeholder="e.g. Abel or Teacher Sarah"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          disabled={submitting}
          maxLength={60}
          className="text-13"
        />
      </div>

      {activeError && (
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-12 font-medium text-red-700">
          {activeError}
        </p>
      )}

      {/* Submit Button */}
      <Button
        type="submit"
        className="w-full"
        disabled={otp.length !== 6 || submitting}
      >
        {submitting ? (
          <>
            <Loading03Icon size={16} className="mr-2 animate-spin" />
            Verifying account…
          </>
        ) : (
          "Verify and continue"
        )}
      </Button>

      {/* Resend Cooldown Action */}
      <div className="flex items-center justify-between pt-1 text-12">
        <button
          type="button"
          onClick={onBack}
          className="inline-flex items-center gap-1 text-ink-secondary hover:text-ink"
        >
          <ArrowLeft01Icon size={14} />
          Back to registration
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
            className="font-semibold text-[#0d7a68] transition-colors hover:text-[#0a6657] hover:underline disabled:opacity-50"
          >
            {resending ? "Sending code…" : "Resend code"}
          </button>
        )}

      </div>
    </form>
  );
}
