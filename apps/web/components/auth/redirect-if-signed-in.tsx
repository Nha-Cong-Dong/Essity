import { redirect } from "next/navigation";
import { connection } from "next/server";

import { getSession } from "@/lib/session";

/**
 * On /login and /register: someone still signed in goes straight to the app (AC7). The proxy
 * never does this (a dead cookie would loop), so the page asks core-api. Put it in a Suspense.
 */
export async function RedirectIfSignedIn() {
  await connection();
  const me = await getSession().catch(() => null); // core-api down: show the form
  if (me) redirect(me.email_verified ? "/today" : "/check-email");
  return null;
}
