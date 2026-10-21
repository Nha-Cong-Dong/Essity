import { NextResponse } from "next/server";

import { onlyPasswordTooLong, passwordReason } from "@/lib/auth-errors";
import { cookieOptions, PENDING_EMAIL_COOKIE, PENDING_EMAIL_MAX_AGE } from "@/lib/cookies";
import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, rateLimited, readStrings, unavailable } from "@/lib/http";

// T1.13: sign-up. core-api answers 202 whether or not the email has an account (AC5), so this
// always goes on to /check-email, remembering the email in a cookie rather than the URL (F1).
export const POST = withOrigin(async (request) => {
  const signUp = await readStrings(request, ["email", "password"]);
  if (signUp === null) return errorResponse("invalid_request", 400);

  let result;
  try {
    result = await coreClientFor(request).POST("/v1/auth/register", { body: signUp });
  } catch (error) {
    return unavailable("register", error);
  }
  const { response } = result;

  if (response.status === 202) {
    const next = NextResponse.json({ next: "/check-email" });
    const expires = new Date(Date.now() + PENDING_EMAIL_MAX_AGE * 1000);
    // Next encodes the value; the cookie never holds anything but the address.
    next.cookies.set(PENDING_EMAIL_COOKIE, signUp.email, cookieOptions(expires));
    return next;
  }
  if (response.status === 422) {
    // AC1: a refused password says why; a malformed email is a list of field errors.
    const detail: unknown = (result.error as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return errorResponse(onlyPasswordTooLong(detail) ? "too_long" : "invalid_email", 422);
    }
    return errorResponse(passwordReason(detail), 422);
  }
  if (response.status === 429) return rateLimited(response);
  return unavailable("register");
});
