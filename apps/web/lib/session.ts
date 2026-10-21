import "server-only";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { cache } from "react";

import { SESSION_COOKIE } from "@/lib/cookies";
import { type components, coreClient } from "@/lib/core-client";

export { PENDING_EMAIL_COOKIE, SESSION_COOKIE } from "@/lib/cookies";

export type Me = components["schemas"]["Me"];

/**
 * Who the session cookie belongs to, asked of core-api once per request (React `cache`, never a
 * cache shared between requests: W3). Null when there is no cookie or core-api no longer knows
 * it; a core-api failure throws, so it is never mistaken for a sign-out.
 */
export const getSession = cache(async (): Promise<Me | null> => {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  if (!token) return null;
  const { data, response } = await coreClient({ token }).GET("/v1/me");
  if (response.status === 401) return null;
  if (!data) throw new Error(`core-api answered /v1/me with ${response.status}`);
  return data;
});

/** For a private page: the user, or a redirect to /login. */
export async function requireSession(): Promise<Me> {
  const me = await getSession();
  if (me === null) redirect("/login");
  return me;
}

/** For a page of the app: the user, or /login, or /check-email until the email is verified (AC2). */
export async function requireVerifiedSession(): Promise<Me> {
  const me = await requireSession();
  if (!me.email_verified) redirect("/check-email");
  return me;
}
