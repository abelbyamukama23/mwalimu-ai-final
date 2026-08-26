"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { isValidEmail } from "@/lib/auth/email";

/**
 * Account creation step. Submits the email/password to the platform
 * registration endpoint (POST /api/v1/auth/register/) via the auth panel.
 */
export function SignupForm({
  email,
  onChangeEmail,
  onBackToEntry,
  onLogin,
  onSubmit,
  submitting,
  error,
}: {
  email: string;
  onChangeEmail: (email: string) => void;
  onBackToEntry: () => void;
  onLogin: () => void;
  onSubmit: (email: string, password: string, confirm: string) => void;
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
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit && !submitting) onSubmit(email, password, confirm);
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
            autoFocus
            placeholder="you@example.com"
            value={email}
            onChange={(e) => onChangeEmail(e.target.value)}
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
              className="pr-11"
            />
            <IconButton
              type="button"
              size="sm"
              aria-label={showPassword ? "Hide password" : "Show password"}
              onClick={() => setShowPassword((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
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
              className="pr-11"
            />
            <IconButton
              type="button"
              size="sm"
              aria-label={showConfirm ? "Hide password" : "Show password"}
              onClick={() => setShowConfirm((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              {showConfirm ? <EyeOff size={15} /> : <Eye size={15} />}
            </IconButton>
          </div>
        </div>

        {error && (
          <p role="alert" className="rounded-sm bg-red-50 px-3 py-2 text-12 text-red-700">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={!canSubmit || submitting}>
          {submitting ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <div className="flex items-center justify-center gap-1.5 text-13 text-ink-secondary">
        <span>Already have an account?</span>
        <button
          type="button"
          onClick={onLogin}
          className="focus-ring rounded-sm font-medium text-accent hover:underline"
        >
          Log in
        </button>
      </div>

      <button
        type="button"
        onClick={onBackToEntry}
        className="focus-ring mx-auto block rounded-sm text-13 text-ink-secondary hover:text-ink"
      >
        ← Use another email
      </button>
    </div>
  );
}
