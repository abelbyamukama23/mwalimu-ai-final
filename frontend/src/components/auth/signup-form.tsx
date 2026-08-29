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

  const passwordValid = password.length > 0 && password === confirm;
  const canSubmit = isValidEmail(email) && passwordValid;

  return (
    <div className="space-y-4">
      {onGoogleSignup && (
        <>
          <button
            type="button"
            onClick={onGoogleSignup}
            disabled={submitting}
            className="focus-ring flex h-10 w-full items-center justify-center gap-2.5 rounded-lg border border-border bg-surface px-4 text-13 font-medium text-ink transition-colors duration-150 hover:bg-surface-elevated hover:border-border-strong disabled:opacity-60"
          >
            <BrandIcon name="google" size={16} />
            <span>Continue with Google</span>
          </button>

          <div className="relative flex items-center justify-center">
            <div className="w-full border-t border-border" />
            <span className="absolute bg-surface px-2.5 text-11 uppercase tracking-wider text-ink-tertiary">
              or
            </span>
          </div>
        </>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit && !submitting) onSubmit(email, password, confirm);
        }}
        className="space-y-3.5"
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
            autoFocus
            placeholder="you@example.com"
            value={email}
            onChange={(e) => onChangeEmail(e.target.value)}
            disabled={submitting}
            className="text-13"
          />
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

        <Button type="submit" className="w-full" disabled={!canSubmit || submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <p className="pt-1 text-center text-13 text-ink-secondary">
        Already have an account?{" "}
        <button
          type="button"
          onClick={onLogin}
          className="focus-ring rounded-sm font-semibold text-[#1f5c52] transition-colors hover:text-[#184a41] hover:underline"
        >
          Log in
        </button>
      </p>
    </div>
  );
}

