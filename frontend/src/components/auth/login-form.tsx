"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";

/**
 * Password login step for the email already entered on the entry screen.
 * Calls the real platform login endpoint through the existing auth provider —
 * this file never talks to the platform API directly.
 */
export function LoginForm({
  email,
  onBackToEntry,
  onForgot,
  onSignup,
  onSubmit,
  submitting,
  error,
}: {
  email: string;
  onBackToEntry: () => void;
  onForgot: () => void;
  onSignup: () => void;
  onSubmit: (email: string, password: string) => void;
  submitting: boolean;
  error: string | null;
}) {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);

  const canSubmit = password.length > 0 && !submitting;

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSubmit) onSubmit(email, password);
        }}
        className="space-y-4"
      >
        <div>
          <span className="mb-1.5 block text-13 font-medium text-ink">Email</span>
          <div className="flex h-11 items-center rounded-md border border-border bg-subtle/50 px-3.5 text-14 text-ink">
            {email}
          </div>
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
              autoFocus
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="pr-11"
            />
            <IconButton
              type="button"
              size="sm"
              aria-label={show ? "Hide password" : "Show password"}
              onClick={() => setShow((s) => !s)}
              className="absolute right-2 top-1/2 -translate-y-1/2"
            >
              {show ? <EyeOff size={15} /> : <Eye size={15} />}
            </IconButton>
          </div>
        </div>

        {error && (
          <p role="alert" className="rounded-sm bg-red-50 px-3 py-2 text-12 text-red-700">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={!canSubmit}>
          {submitting ? "Logging in…" : "Log in"}
        </Button>
      </form>

      <div className="flex items-center justify-between gap-2 text-13">
        <button
          type="button"
          onClick={onBackToEntry}
          className="focus-ring rounded-sm text-ink-secondary hover:text-ink"
        >
          ← Use another email
        </button>
        <button
          type="button"
          onClick={onForgot}
          className="focus-ring rounded-sm text-accent hover:underline"
        >
          Forgot password?
        </button>
      </div>

      <p className="text-center text-13 text-ink-secondary">
        New to Mwalimu?{" "}
        <button
          type="button"
          onClick={onSignup}
          className="focus-ring rounded-sm font-medium text-accent hover:underline"
        >
          Sign up
        </button>
      </p>
    </div>
  );
}
