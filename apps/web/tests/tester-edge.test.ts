// Tester (step 4), T1.18/T1.20: edge cases the mutation run found unguarded.
import { describe, expect, it } from "vitest";

import { parseExamDate } from "@/lib/exam-date";
import { isSubjectId } from "@/lib/subject-id";

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
