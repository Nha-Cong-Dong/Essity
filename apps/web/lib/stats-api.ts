import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { type StatsView, toStatsData } from "@/lib/stats-view";
import { CoreStatusError } from "@/lib/subjects";

// T9.5 (US-10): GET /v1/stats read on the server for /stats.

/**
 * The stats of every subject, and the grid of `subjectId` when it is one of them (any other id
 * means all subjects: the page never 404s on a stale link). Throws CoreStatusError on a refusal.
 */
export async function getStats(subjectId?: string): Promise<{ view: StatsView; subject: string }> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const client = coreClient({ token });
  const all = await client.GET("/v1/stats");
  if (!all.data) throw new CoreStatusError("/v1/stats", all.response.status);
  const view = toStatsData(all.data);
  const chosen = view.subjects.find((s) => s.id === subjectId)?.id;
  if (chosen === undefined) return { view, subject: "" };
  const one = await client.GET("/v1/stats", { params: { query: { subject_id: chosen } } });
  if (!one.data) throw new CoreStatusError("/v1/stats", one.response.status);
  return { view: { ...view, cells: toStatsData(one.data).cells }, subject: chosen };
}
