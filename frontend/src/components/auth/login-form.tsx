"use client";

import { useState } from "react";
import { ViewIcon, ViewOffIcon } from "hugeicons-react";

import { BrandIcon } from "@/components/ui/brand-icon";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { isValidEmail } from "@/lib/auth/email";

/**
 * Direct single-screen login form: Google Login + Email + Password with inline validation.
 */
export function LoginForm({
  email,
  onChangeEmail,
  onForgot,
  onSignup,
  onSubmit,
  onGoogleLogin,
  submitting,
  error,
}: {
  email: string;
  onChangeEmail: (email: string) => void;
  onForgot: () => void;
  onSignup: () => void;
  onSubmit: (email: string, password: string) => void;
  onGoogleLogin?: () => void;
  submitting: boolean;
  error: string | null;
}) {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [emailTouched, setEmailTouched] = useState(false);

  const isEmailValid = isValidEmail(email);
  const showEmailError = emailTouched && email.length > 0 && !isEmailValid;
  const canSubmit = isEmailValid && password.length > 0 && !submitting;

  return (
    <div className="space-y-4">
      {onGoogleLogin && (
        <>
          <button
            type="button"
            onClick={onGoogleLogin}
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
          if (canSubmit) onSubmit(email, password);
        }}
        className="space-y-4"
      >
        <div>
          <label
            htmlFor="auth-email"
            className="mb-1.5 block text-13 font-medium text-ink"
          >
            Email address
          </label>
          <Input
            id="auth-email"
            type="email"
            autoComplete="email"
            inputMode="email"
            required
            autoFocus={!email}
            placeholder="you@example.com"
            value={email}
            error={showEmailError}
            aria-describedby={showEmailError ? "email-format-error" : undefined}
            onChange={(e) => {
              onChangeEmail(e.target.value);
            }}
            onBlur={() => setEmailTouched(true)}
            disabled={submitting}
          />
          {showEmailError && (
            <p id="email-format-error" role="alert" className="mt-1.5 text-12 font-medium text-red-600">
              Please enter a valid email address.
            </p>
          )}
        </div>

        <div>
          <label
            htmlFor="auth-password"
            className="mb-1.5 block text-13 font-medium text-ink"
          >
            Password
          </label>
          <div className="relative">
            <Input
              id="auth-password"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              required
              autoFocus={Boolean(email)}
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              className="pr-11"
            />
            <IconButton
              type="button"
              size="sm"
              aria-label={show ? "Hide password" : "Show password"}
              onClick={() => setShow((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              {show ? <ViewOffIcon size={16} /> : <ViewIcon size={16} />}
            </IconButton>
          </div>
          <div className="flex justify-end pt-1.5">
            <button
              type="button"
              onClick={onForgot}
              className="focus-ring rounded-sm text-12 font-medium text-[#0d7a68] transition-colors hover:text-[#0a6657] hover:underline"
            >
              Forgot password?
            </button>
          </div>
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
          {submitting ? "Logging in…" : "Log in"}
        </Button>
      </form>

      <p className="pt-2 text-center text-13 text-ink-secondary">
        New to Mwalimu?{" "}
        <button
          type="button"
          onClick={onSignup}
          className="focus-ring rounded-sm font-semibold text-[#0d7a68] underline underline-offset-2 transition-colors hover:text-[#0a6657]"
        >
          Sign up
        </button>
      </p>
    </div>
  );
}

