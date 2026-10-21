import { NextResponse } from "next/server";

import { EXPIRED_COOKIE, PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/cookies";
import { coreClientFor } from "@/lib/core-client";
import { withOrigin } from "@/lib/csrf";

// T1.12: POST only, so a link or an image on another site cannot sign anyone out.
export const POST = withOrigin(async (request) => {
  const token = request.cookies.get(SESSION_COOKIE)?.value;
  if (token) {
    try {
      await coreClientFor(request, token).POST("/v1/auth/logout");
    } catch (error) {
      // The cookie goes anyway: this browser is signed out even if core-api did not hear it.
      console.error("core-api call failed", {
        route: "logout",
        error: error instanceof Error ? error.name : undefined,
      });
    }
  }
  const response = NextResponse.json({ next: "/login" });
  response.cookies.set(SESSION_COOKIE, "", EXPIRED_COOKIE);
  if (request.cookies.has(PENDING_EMAIL_COOKIE)) {
    response.cookies.set(PENDING_EMAIL_COOKIE, "", EXPIRED_COOKIE); // F2: "Sai email?"
  }
  return response;
});
