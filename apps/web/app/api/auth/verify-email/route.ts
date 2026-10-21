import { NextResponse } from "next/server";

import { sessionUser } from "@/lib/account";
import { EXPIRED_COOKIE, PENDING_EMAIL_COOKIE } from "@/lib/cookies";
import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, rateLimited, readStrings, unavailable } from "@/lib/http";

// T1.13: the link in the verification email. The page POSTs its token here after taking it
// out of the URL (F8). `signedIn` tells the page whether to go on into the app or show
// "Đăng nhập" (F4); core-api's answer names no account, so it is asked of /v1/me afresh.
export const POST = withOrigin(async (request) => {
  const body = await readStrings(request, ["token"]);
  if (body === null) return errorResponse("invalid_request", 400);

  try {
    const { response } = await coreClientFor(request).POST("/v1/auth/verify-email", { body });
    if (response.status === 429) return rateLimited(response);
    if (response.status !== 200 && response.status !== 400 && response.status !== 422) {
      return unavailable("verify-email");
    }
    const signedIn = (await sessionUser(request))?.email_verified === true;
    if (response.status !== 200) {
      // AC2, F5: expired, used or unknown are one answer.
      return NextResponse.json({ error: "invalid_or_expired_token", signedIn }, { status: 400 });
    }
    const verified = NextResponse.json({ verified: true, signedIn });
    if (request.cookies.has(PENDING_EMAIL_COOKIE)) {
      verified.cookies.set(PENDING_EMAIL_COOKIE, "", EXPIRED_COOKIE);
    }
    return verified;
  } catch (error) {
    return unavailable("verify-email", error);
  }
});
