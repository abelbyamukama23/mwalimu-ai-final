"use client";

import { useState } from "react";
import { ViewIcon, ViewOffIcon } from "hugeicons-react";
import { BrandIcon } from "@/components/ui/brand-icon";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { isValidEmail } from "@/lib/auth/email";

/**
 * Account creation form: Google Signup + Email + Password + Confirm Password.
 */
export function SignupForm({
  email,
  onChangeEmail,
  onLogin,
  onSubmit,
  onGoogleSignup,
  submitting,
  error,
}: {
  email: string;
  onChangeEmail: (email: string) => void;
  onLogin: () => void;
  onSubmit: (email: string, password: string, confirm: string) => void;
  onGoogleSignup?: () => void;
  submitting: boolean;
  error: string | null;
}) {
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [emailTouched, setEmailTouched] = useState(false);
  const [confirmTouched, setConfirmTouched] = useState(false);

  const isEmailValid = isValidEmail(email);
  const showEmailError = emailTouched && email.length > 0 && !isEmailValid;
  const showMismatchError = confirmTouched && confirm.length > 0 && password !== confirm;
  const passwordValid = password.length > 0 && password === confirm;
  const canSubmit = isEmailValid && passwordValid && !submitting;

  return (
    <div className="space-y-4">
      {onGoogleSignup && (
        <>
          <button
            type="button"
            onClick={onGoogleSignup}
            disabled={submitting}
            className="focus-ring flex h-11 w-full items-center justify-center gap-2.5 rounded-lg border border-[#d4d4d8] bg-surface px-4 text-13 font-medium text-ink shadow-2xs transition-all duration-150 hover:bg-[#f4f4f5] hover:border-[#a1a1aa] active:scale-[0.99] disabled:opacity-60 cursor-pointer"
          >
            <BrandIcon name="google" size={18} />
            <span>Continue with Google</span>
          </button>

          <div className="relative flex items-center justify-center py-0.5">
            <div className="w-full border-t border-border" />
            <span className="absolute bg-surface px-2.5 text-[11px] font-medium uppercase tracking-wider text-[#a1a1aa]">
              or
            </span>
          </div>
        </>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) onSubmit(email, password, confirm);
        }}
        className="space-y-4"
      >
        <div>
          <label
            htmlFor="signup-email"
            className="mb-1.5 block text-13 font-medium text-ink"
          >
            Email address
          </label>
          <Input
            id="signup-email"
            type="email"
            autoComplete="email"
            inputMode="email"
            required
            autoFocus={!email}
            placeholder="you@example.com"
            value={email}
            error={showEmailError}
            aria-describedby={showEmailError ? "signup-email-error" : undefined}
            onChange={(e) => onChangeEmail(e.target.value)}
            onBlur={() => setEmailTouched(true)}
            disabled={submitting}
          />
          {showEmailError && (
            <p id="signup-email-error" role="alert" className="mt-1.5 text-12 font-medium text-red-600">
              Please enter a valid email address.
            </p>
          )}
        </div>

        <div>
          <label
            htmlFor="signup-password"
            className="mb-1.5 block text-13 font-medium text-ink"
          >
            Password
          </label>
          <div className="relative">
            <Input
              id="signup-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              required
              placeholder="Create a password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              className="pr-11"
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

        <div>
          <label
            htmlFor="signup-confirm"
            className="mb-1.5 block text-13 font-medium text-ink"
          >
            Confirm password
          </label>
          <div className="relative">
            <Input
              id="signup-confirm"
              type={showConfirm ? "text" : "password"}
              autoComplete="new-password"
              required
              placeholder="Repeat your password"
              value={confirm}
              error={showMismatchError}
              aria-describedby={showMismatchError ? "signup-mismatch-error" : undefined}
              onChange={(e) => setConfirm(e.target.value)}
              onBlur={() => setConfirmTouched(true)}
              disabled={submitting}
              className="pr-11"
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
          {showMismatchError && (
            <p id="signup-mismatch-error" role="alert" className="mt-1.5 text-12 font-medium text-red-600">
              Passwords do not match.
            </p>
          )}
        </div>

        {error && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-12 font-medium text-red-700">
            {error}
          </p>
        )}

        <Button
          type="submit"
          className="w-full h-11 text-14 font-medium"
          disabled={!canSubmit}
          loading={submitting}
        >
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <p className="pt-2 text-center text-13 text-ink-secondary">
        Already have an account?{" "}
        <button
          type="button"
          onClick={onLogin}
          className="focus-ring rounded-sm font-semibold text-[#0d7a68] underline underline-offset-2 transition-colors hover:text-[#0a6657]"
        >
          Log in
        </button>
      </p>
    </div>
  );
}
