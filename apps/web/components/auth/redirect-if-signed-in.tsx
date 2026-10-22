import { redirect } from "next/navigation";
import { connection } from "next/server";

import { landingFor } from "@/lib/landing";
import { getSession } from "@/lib/session";
import { errorName, logError } from "@/lib/log";

/**
 * On /login and /register: someone still signed in goes straight to the app (AC7). The proxy
 * never does this (a dead cookie would loop), so the page asks core-api. Put it in a Suspense.
 */
export async function RedirectIfSignedIn() {
  await connection();
  const me = await getSession().catch((error: unknown) => {
    // core-api down: show the form, and say so in the log (R12).
    logError("core-api call failed", { route: "session-check", error: errorName(error) });
    return null;
  });
  if (me) redirect(landingFor(me));
  return null;
}
