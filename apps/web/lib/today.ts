import "server-only";

import { cookies } from "next/headers";

import { type components, coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { CoreStatusError } from "@/lib/subjects";

// T2.14: today's session, read on the server for /today (GET /v1/today, T2.8).
export type Today = components["schemas"]["TodayOut"];

/** What /v1/today answers for the signed-in user. Throws CoreStatusError when core-api refuses. */
export async function getToday(): Promise<Today> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const { data, response } = await coreClient({ token }).GET("/v1/today");
  if (!data) throw new CoreStatusError("/v1/today", response.status);
  return data;
}
