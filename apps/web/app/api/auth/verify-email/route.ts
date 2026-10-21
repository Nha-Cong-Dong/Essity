import { NextResponse } from "next/server";

import { sessionUser } from "@/lib/account";
import { EXPIRED_COOKIE, PENDING_EMAIL_COOKIE } from "@/lib/cookies";
import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";
import { errorResponse, rateLimited, readStrings, unavailable } from "@/lib/http";

// T1.13: the link in the verification email. The page POSTs its token here after taking it
// out of the URL (F8). `signedIn` tells the page whether to go on into the app or show
// "Đăng nhập" (F4). core-api's answer names no account, so /v1/me is asked before and after:
// only a session that this link just verified is the link owner's (review 822b3ea #2).
export const POST = withOrigin(async (request) => {
  const body = await readStrings(request, ["token"]);
  if (body === null) return errorResponse("invalid_request", 400);

  try {
    const before = await sessionUser(request);
    const { response } = await coreClientFor(request).POST("/v1/auth/verify-email", { body });
    if (response.status === 429) return rateLimited(response);
    if (response.status !== 200 && response.status !== 400 && response.status !== 422) {
      return unavailable("verify-email");
    }
    const after = await sessionUser(request);
    if (response.status !== 200) {
      const signedIn = after?.email_verified === true;
      // AC2, F5: expired, used or unknown are one answer.
      return NextResponse.json({ error: "invalid_or_expired_token", signedIn }, { status: 400 });
    }
    const signedIn = before?.email_verified === false && after?.email_verified === true;
    const verified = NextResponse.json({ verified: true, signedIn });
    if (request.cookies.has(PENDING_EMAIL_COOKIE)) {
      verified.cookies.set(PENDING_EMAIL_COOKIE, "", EXPIRED_COOKIE);
    }
    return verified;
  } catch (error) {
    return unavailable("verify-email", error);
  }
});
