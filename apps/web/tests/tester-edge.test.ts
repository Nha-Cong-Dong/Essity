// Tester (step 4), T1.18/T1.20: edge cases the mutation run found unguarded.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST as save } from "@/app/api/baseline/route";
import { parseExamDate } from "@/lib/exam-date";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";

import { browserPost, fakeCoreApi, SERVICE_TOKEN } from "./helpers";

describe("parseExamDate: century years", () => {
  // Red when: lib/exam-date.ts daysIn drops `year % 100 !== 0` (1900 and 2100 would get a 29 Feb).
  it.each(["29/02/1900", "29/02/2100"])("%s is refused: a century is a leap year only if divisible by 400", (typed) => {
    expect(parseExamDate(typed)).toEqual({ error: "date_format" });
  });

  // Red when: the `year % 400 === 0` clause is removed.
  it("29/02/2000 is accepted", () => {
    expect(parseExamDate("29/02/2000")).toEqual({ value: "2000-02-29" });
  });
});

describe("isSubjectId: anchored at both ends (review plan R1)", () => {
  const ID = "3f2b8c1e-7a4d-4e5f-9b6a-1c2d3e4f5a6b";

  it("a UUID is accepted", () => {
    expect(isSubjectId(ID)).toBe(true);
  });

  // Red when: lib/subject-id.ts loses the leading `^`, so "../<uuid>" reaches core-api's path.
  it.each([`../${ID}`, `x${ID}`, `/${ID}`, `%2e%2e/${ID}`])("%s is refused", (id) => {
    expect(isSubjectId(id)).toBe(false);
  });

  it.each([`${ID}/..`, `${ID}x`, "", "..", 42, null, undefined])("%j is refused", (id) => {
    expect(isSubjectId(id)).toBe(false);
  });
});

describe("POST /api/baseline: /v1/me that throws after a save (review plan R3)", () => {
  beforeEach(() => {
    vi.stubEnv("WEB_TO_CORE_TOKEN", SERVICE_TOKEN);
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  // Red when: lib/onboarding.ts nextAfterBaseline's `catch` returns "/subjects/new" (or rethrows):
  // a network failure after the save would ask the user to start over.
  it("a network error on /v1/me still goes to /today", async () => {
    fakeCoreApi((call) => {
      if (call.path === "/v1/me") throw new TypeError("fetch failed");
      return Response.json({ gpa_before: "3.17" }, { status: 201 });
    });

    const response = await save(
      browserPost(
        "/api/baseline",
        { gpa_before: "3.17", prior_ready_days: 3, prior_days_unknown: false },
        { cookies: { [SESSION_COOKIE]: "session-token-marker-edge" } },
      ),
    );

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ next: "/today" });
  });
});
