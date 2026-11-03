import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { type StatsView, toStatsData } from "@/lib/stats-view";
import { CoreStatusError } from "@/lib/subjects";

// T9.5 (US-10): GET /v1/stats read on the server for /stats.

/** The overall stats (all subjects together). Throws CoreStatusError on a refusal. */
export async function getStats(): Promise<{ view: StatsView; subject: string }> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const client = coreClient({ token });
  const all = await client.GET("/v1/stats");
  if (!all.data) throw new CoreStatusError("/v1/stats", all.response.status);
  return { view: toStatsData(all.data), subject: "" };
}
