"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";
import { Input } from "@/components/ui/input";
import { isValidEmail } from "@/lib/auth/email";

/**
 * Direct single-screen login form: Email + Password with instant sign-in.
 */
export function LoginForm({
  email,
  onChangeEmail,
  onForgot,
  onSignup,
  onSubmit,
  submitting,
  error,
}: {
  email: string;
  onChangeEmail: (email: string) => void;
  onForgot: () => void;
  onSignup: () => void;
  onSubmit: (email: string, password: string) => void;
  submitting: boolean;
  error: string | null;
}) {
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);

  const canSubmit = isValidEmail(email) && password.length > 0 && !submitting;

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
            onChange={(e) => onChangeEmail(e.target.value)}
          />
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label
              htmlFor="auth-password"
              className="text-13 font-medium text-ink"
            >
              Password
            </label>
            <button
              type="button"
              onClick={onForgot}
              className="focus-ring rounded-sm text-12 text-accent hover:underline"
            >
              Forgot password?
            </button>
          </div>
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
