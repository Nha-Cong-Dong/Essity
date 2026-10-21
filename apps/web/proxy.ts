import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/cookies";

// T1.12, W3: an optimistic check only. A page without a session cookie goes to /login; whether
// the cookie is still a live session, and whether the email is verified, the page itself asks
// core-api (lib/session.ts). Never sends /login back to the app, so a dead cookie cannot loop.

export const PUBLIC_PAGES: ReadonlySet<string> = new Set([
  "/login",
  "/register",
  "/check-email",
  "/verify-email",
  "/forgot-password",
  "/reset-password",
  "/design-preview",
]);

export function proxy(request: NextRequest) {
  if (PUBLIC_PAGES.has(request.nextUrl.pathname) || request.cookies.has(SESSION_COOKIE)) {
    return NextResponse.next();
  }
  // No ?next=: nothing from the request decides where the user lands (F7).
  return NextResponse.redirect(new URL("/login", request.url));
}

export const config = {
  // Pages only: API routes answer for themselves (401 from core-api, origin check), and static
  // files must load on /login. A page path may contain a dot (/subjects/de-thi.v2), so only
  // the extensions of real files are skipped.
  matcher: [
    "/((?!api/|_next/|.*\\.(?:png|jpg|jpeg|gif|svg|webp|ico|css|js|map|txt|woff2?)$).*)",
  ],
};
