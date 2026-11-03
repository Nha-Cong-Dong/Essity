import { cookies } from "next/headers";
import { Suspense } from "react";

import { LandingRedirect } from "@/components/landing-redirect";
import { SESSION_COOKIE } from "@/lib/cookies";

import { Landing } from "./landing";

/**
 * "/" (T0.15): a visitor without a session cookie sees the landing; with one, the way into the
 * app as before: the page asks core-api whether the cookie is a live, verified session
 * (landingFor). Reading cookies is request-time work, so put it in a Suspense.
 */
export async function LandingEntry() {
  if ((await cookies()).has(SESSION_COOKIE)) {
    return (
      <Suspense fallback={null}>
        <LandingRedirect />
      </Suspense>
    );
  }
  return <Landing />;
}
