// T1.18, plan K4; T1.22: which page someone lands on when they open the app. Asked only at the
// ways in (/, sign-in, /login while signed in, after verifying an email); /today never sends
// anyone on (CONVENTIONS).

type Flags = { email_verified: boolean; has_subjects: boolean };

/** Every page landingFor may name, for the check that each has a page (internal-links test). */
export const LANDINGS = ["/check-email", "/subjects/new", "/today"] as const;

export type Landing = (typeof LANDINGS)[number];

export function landingFor(me: Flags): Landing {
  if (!me.email_verified) return "/check-email";
  if (!me.has_subjects) return "/subjects/new";
  return "/today";
}

/** The pages a verified, signed-in person goes on to (after verifying, after signing in). */
export const NEXT_PAGES = ["/subjects/new", "/today"] as const;

/**
 * A `next` from one of web's routes, kept only when it is one of `pages`; anything else is
 * `fallback` (review plan R3: never follow a page the flow does not know, like "//evil.example").
 */
export function safeNext(next: unknown, pages: readonly string[] = NEXT_PAGES, fallback = "/today"): string {
  return typeof next === "string" && pages.includes(next) ? next : fallback;
}
