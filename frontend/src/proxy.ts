import { NextResponse, type NextRequest } from "next/server";

/**
 * Mwalimu serves two application surfaces from one Next.js app:
 *
 *   app.mwalimu.com           → generic user application (default routes)
 *   institutions.mwalimu.com  → institution console (rewritten to /console/*)
 *
 * Local development is path-based: /console/* works directly on localhost.
 * The subdomain mapping activates when the host starts with "institutions.".
 *
 * Note: the subdomain is a UX boundary only — authorization is always enforced
 * by the Platform API (active membership, administrator role).
 */
export function proxy(request: NextRequest) {
  const host = request.headers.get("host") ?? "";
  const { pathname } = request.nextUrl;

  if (host.startsWith("institutions.") && !pathname.startsWith("/console")) {
    const url = request.nextUrl.clone();
    url.pathname = `/console${pathname === "/" ? "/dashboard" : pathname}`;
    return NextResponse.rewrite(url);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon.svg|.*\\..*).*)"],
};
