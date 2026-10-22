import { redirect } from "next/navigation";
import { connection } from "next/server";

import { landingFor } from "@/lib/landing";
import { requireVerifiedSession } from "@/lib/session";

/**
 * "/" is the way into the app: the baseline screen, the first subject or "Phiên hôm nay", by
 * core-api's /v1/me (T1.18, plan K4). Put it in a Suspense.
 */
export async function LandingRedirect(): Promise<null> {
  await connection();
  redirect(landingFor(await requireVerifiedSession()));
}
