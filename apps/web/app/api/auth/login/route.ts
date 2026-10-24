import { NextResponse } from "next/server";

import { cookieOptions, EXPIRED_COOKIE, PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/cookies";
import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, rateLimited, readStrings, unavailable } from "@/lib/http";

// T1.12: signs in through core-api and keeps the session token in an HttpOnly cookie, so the
// browser's JavaScript never sees it (ADR-0014).
export const POST = withOrigin(async (request) => {
  const credentials = await readStrings(request, ["email", "password"]);
  if (credentials === null) return errorResponse("invalid_request", 400);

  let result;
  try {
    result = await coreClientFor(request).POST("/v1/auth/login", { body: credentials });
  } catch (error) {
    return unavailable("login", error);
  }
  const { data, response } = result;

  if (data) {
    // AC7: core-api says whether the email is verified, so no second round trip (W3). "/" then
    // picks the first subject or /today (T1.18, plan K4).
    const next = NextResponse.json({ next: data.email_verified ? "/" : "/check-email" });
    next.cookies.set(SESSION_COOKIE, data.token, cookieOptions(new Date(data.expires_at)));
    if (request.cookies.has(PENDING_EMAIL_COOKIE)) {
      next.cookies.set(PENDING_EMAIL_COOKIE, "", EXPIRED_COOKIE);
    }
    return next;
  }
  // AC5: one answer for a wrong email, a wrong password or a malformed email.
  if (response.status === 401 || response.status === 422) {
    return errorResponse("invalid_credentials", 401);
  }
  if (response.status === 429) return rateLimited(response);
  return unavailable("login");
});
