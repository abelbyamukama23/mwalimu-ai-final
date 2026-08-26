"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isValidEmail } from "@/lib/auth/email";

/**
 * Email-first entry step. The purpose is to establish which email to continue
 * with — the password is NOT requested here. This screen never mentions
 * institutions: a Mwalimu account does not require one.
 */
export function AuthEntry({
  email,
  onChangeEmail,
  onContinue,
  onSignup,
}: {
  email: string;
  onChangeEmail: (email: string) => void;
  onContinue: (email: string) => void;
  onSignup: () => void;
}) {
  const canContinue = isValidEmail(email);

  return (
    <div className="space-y-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canContinue) onContinue(email);
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
            autoFocus
            placeholder="you@example.com"
            value={email}
            onChange={(e) => onChangeEmail(e.target.value)}
          />
        </div>
        <Button type="submit" className="w-full" disabled={!canContinue}>
          Continue
        </Button>
      </form>

      <div className="flex items-center justify-center gap-1.5 text-13 text-ink-secondary">
        <span>New to Mwalimu?</span>
        <button
          type="button"
          onClick={onSignup}
          className="focus-ring rounded-sm font-medium text-accent hover:underline"
        >
          Sign up
        </button>
      </div>
    </div>
  );
}
