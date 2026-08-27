/**
 * Email helpers used by the authentication entry screen.
 *
 * Pure, UI-adjacent validation — it deliberately does NOT call any backend or
 * make claims about whether an account exists for a given address.
 */

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Trim and lowercase. Returns "" for empty/whitespace input. */
export function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

/** Returns true when the email is non-empty and has a plausible shape. */
export function isValidEmail(email: string): boolean {
  const value = normalizeEmail(email);
  return value.length > 0 && EMAIL_PATTERN.test(value);
}
