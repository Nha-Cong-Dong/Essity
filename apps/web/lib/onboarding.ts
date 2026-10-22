import "server-only";

import { redirect } from "next/navigation";

import type { CoreClient } from "@/lib/core-client";
import { afterBaseline, landingFor } from "@/lib/landing";
import { type Me, requireVerifiedSession } from "@/lib/session";
import { errorName, logError } from "@/lib/log";

/**
 * For /onboarding: the user while core-api still asks for a baseline (US-11 AC2: not yet given,
 * skipped fewer than twice); anyone else goes where landingFor says.
 */
export async function requireBaselineToEnter(): Promise<Me> {
  const me = await requireVerifiedSession();
  if (!me.needs_baseline) redirect(landingFor(me));
  return me;
}

/**
 * Where to go once the baseline is saved or skipped (plan K4c): past /onboarding, by
 * has_subjects. /v1/me failing after the save must not ask for the save again: /today (review
 * plan R3).
 */
export async function nextAfterBaseline(core: CoreClient): Promise<"/subjects/new" | "/today"> {
  try {
    const { data } = await core.GET("/v1/me");
    return data ? afterBaseline(data) : "/today";
  } catch (error) {
    logError("core-api call failed", { route: "baseline-next", error: errorName(error) });
    return "/today";
  }
}
