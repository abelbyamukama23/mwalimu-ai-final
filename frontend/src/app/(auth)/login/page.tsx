import type { Metadata } from "next";
import { AuthPanel } from "@/components/auth/auth-panel";

export const metadata: Metadata = { title: "Log in or sign up" };

/**
 * Route-compatible authentication surface: hosts the SAME reusable AuthPanel
 * component used by the app-wide auth modal, in a full-page layout. Login is
 * wired to the real POST /api/v1/auth/login/ and signup to the real
 * POST /api/v1/auth/register/ (which doubles as sign-in).
 *
 * `next` is resolved server-side so the auth surface fully renders (no blank
 * Suspense shell) and only internal redirects are permitted.
 */
export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const rawNext = typeof params.next === "string" ? params.next : "";
  const redirectTo = rawNext.startsWith("/") ? rawNext : "/chat/new";

  return <AuthPanel mode="page" redirectTo={redirectTo} />;
}
