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

const NEXT_PAGES = new Set<string>(["/subjects/new", "/today"]);

/** A `next` from one of web's routes, kept only when it is a page the flow knows (review plan R3). */
export function safeNext(next: unknown): string {
  return typeof next === "string" && NEXT_PAGES.has(next) ? next : "/today";
}
