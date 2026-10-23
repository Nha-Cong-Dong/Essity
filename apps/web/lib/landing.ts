// T1.18, plan K4: which page someone lands on when they open the app. core-api decides who still
// needs a baseline (plan B14); web only follows its flags, and only at the ways in (/, sign-in,
// /login while signed in, /onboarding itself). /today never sends anyone on: right after
// "Nhập sau", needs_baseline is still true, and /today would send them straight back.

type Flags = { email_verified: boolean; needs_baseline: boolean; has_subjects: boolean };

export type Landing = "/check-email" | "/onboarding" | "/subjects/new" | "/today";

export function landingFor(me: Flags): Landing {
  if (!me.email_verified) return "/check-email";
  if (me.needs_baseline) return "/onboarding";
  if (!me.has_subjects) return "/subjects/new";
  return "/today";
}

/** Where to go after the baseline screen: past it, never back (plan K4c). */
export function afterBaseline(me: { has_subjects: boolean }): "/subjects/new" | "/today" {
  return me.has_subjects ? "/today" : "/subjects/new";
}

/** The pages a verified, signed-in person goes on to (after the baseline screen, after verifying). */
export const NEXT_PAGES = ["/subjects/new", "/today"] as const;

/**
 * A `next` from one of web's routes, kept only when it is one of `pages`; anything else is
 * `fallback` (review plan R3: never follow a page the flow does not know, like "//evil.example").
 */
export function safeNext(next: unknown, pages: readonly string[] = NEXT_PAGES, fallback = "/today"): string {
  return typeof next === "string" && pages.includes(next) ? next : fallback;
}
