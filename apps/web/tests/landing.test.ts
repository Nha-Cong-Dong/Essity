// T1.18, plan K4: where someone goes when they open the app, from core-api's /v1/me (plan B14).
import { describe, expect, it } from "vitest";

import { landingFor, safeNext } from "@/lib/landing";

const me = (over: { email_verified?: boolean; needs_baseline?: boolean; has_subjects?: boolean } = {}) => ({
  email_verified: true,
  needs_baseline: false,
  has_subjects: true,
  ...over,
});

describe("landingFor (US-11 AC1, AC2; plan K4b)", () => {
  // Every combination: verified × needs_baseline × has_subjects (Guardian, step 1).
  it.each([
    [false, false, false, "/check-email"],
    [false, false, true, "/check-email"],
    [false, true, false, "/check-email"],
    [false, true, true, "/check-email"],
    [true, true, false, "/onboarding"],
    [true, true, true, "/onboarding"],
    [true, false, false, "/subjects/new"],
    [true, false, true, "/today"],
  ])("verified %s, needs_baseline %s, has_subjects %s → %s", (verified, needsBaseline, hasSubjects, to) => {
    expect(landingFor(me({ email_verified: verified, needs_baseline: needsBaseline, has_subjects: hasSubjects }))).toBe(
      to,
    );
  });
});

describe("safeNext (review plan R3)", () => {
  it.each(["/subjects/new", "/today"])("keeps %s", (next) => {
    expect(safeNext(next)).toBe(next);
  });

  // Red when: the browser follows whatever `next` a response carries (an open redirect).
  it.each(["//evil.example", "https://evil.example/today", "/onboarding", "/today?x=1", "", undefined, 42, null])(
    "turns %j into /today",
    (next) => {
      expect(safeNext(next)).toBe("/today");
    },
  );
});

describe("safeNext with its own pages (review 266042d #3: the sign-in form)", () => {
  const SIGN_IN = ["/", "/check-email"] as const;

  it.each(SIGN_IN)("keeps %s", (next) => {
    expect(safeNext(next, SIGN_IN, "/")).toBe(next);
  });

  it.each(["//evil.example", "/today", "https://evil.example/"])("turns %j into /", (next) => {
    expect(safeNext(next, SIGN_IN, "/")).toBe("/");
  });
});
