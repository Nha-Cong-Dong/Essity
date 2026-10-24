// T1.18, plan K4: where someone goes when they open the app, from core-api's /v1/me (plan B14).
import { describe, expect, it } from "vitest";

import { LANDINGS, landingFor, safeNext } from "@/lib/landing";

describe("landingFor (plan K4b; T1.22: no baseline step)", () => {
  // Every combination: verified × has_subjects.
  it.each([
    [false, false, "/check-email"],
    [false, true, "/check-email"],
    [true, false, "/subjects/new"],
    [true, true, "/today"],
  ])("verified %s, has_subjects %s → %s", (verified, hasSubjects, to) => {
    expect(landingFor({ email_verified: verified, has_subjects: hasSubjects })).toBe(to);
  });

  // us-01 AC8 (T2.3b): deleting the last subject turns has_subjects false (core-api test), and
  // that alone sends the user back to creating one.
  it("us-01 AC8: someone with no subject left goes to /subjects/new", () => {
    expect(landingFor({ email_verified: true, has_subjects: false })).toBe("/subjects/new");
  });

  // Red when: a landing is added back (like /onboarding) without its own decision.
  it("names exactly three pages", () => {
    expect([...LANDINGS]).toEqual(["/check-email", "/subjects/new", "/today"]);
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
