import { NextResponse } from "next/server";

import { onlyPasswordTooLong, passwordReason } from "@/lib/auth-errors";
import { EXPIRED_COOKIE, SESSION_COOKIE } from "@/lib/cookies";
import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, rateLimited, readStrings, unavailable } from "@/lib/http";

// T1.14: the form of the reset link. core-api ends every session of the account (ADR-0021);
// this browser's cookie goes too, and the user signs in again with the new password (F6).
export const POST = withOrigin(async (request) => {
  const body = await readStrings(request, ["token", "password"]);
  if (body === null) return errorResponse("invalid_request", 400);

  let result;
  try {
    result = await coreClientFor(request).POST("/v1/auth/password-reset/confirm", { body });
  } catch (error) {
    return unavailable("password-reset-confirm", error);
  }
  const { response } = result;

  if (response.status === 200) {
    const done = NextResponse.json({ done: true });
    if (request.cookies.has(SESSION_COOKIE)) done.cookies.set(SESSION_COOKIE, "", EXPIRED_COOKIE);
    return done;
  }
  if (response.status === 422) {
    // A refused password keeps the link usable (F6); a malformed token is just a bad link.
    const detail: unknown = (result.error as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail)) {
      return onlyPasswordTooLong(detail)
        ? errorResponse("too_long", 422)
        : errorResponse("invalid_or_expired_token", 400);
    }
    return errorResponse(passwordReason(detail), 422);
  }
  if (response.status === 400) return errorResponse("invalid_or_expired_token", 400);
  if (response.status === 429) return rateLimited(response);
  return unavailable("password-reset-confirm");
});
