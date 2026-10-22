// Risk register R24, plan D11/D11b/D11c: the exam-date example is always a date core-api accepts.
// learningDay mirrors core_api/domain/learning_day.py; the boundary cases below are copied from
// services/core-api/tests/domain/test_learning_day.py so the two stay in step (plan K3 keeps the
// server as the source for "today"; this is only for the example).
import { describe, expect, it } from "vitest";

import { examExample, exampleFor, learningDay } from "@/lib/exam-date";

describe("learningDay (R24, same cases as core-api)", () => {
  it.each([
    ["2026-10-15T20:59:59Z", "Asia/Ho_Chi_Minh", 4, "2026-10-15"], // 03:59:59 local: still yesterday
    ["2026-10-15T21:00:00Z", "Asia/Ho_Chi_Minh", 4, "2026-10-16"], // 04:00 local: a new day
    ["2026-10-15T17:00:00Z", "Asia/Ho_Chi_Minh", 4, "2026-10-15"], // midnight: previous day
    ["2026-10-15T17:00:00Z", "Asia/Ho_Chi_Minh", 0, "2026-10-16"], // start 0: the calendar day
    ["2026-10-15T22:00:00Z", "Asia/Ho_Chi_Minh", 4, "2026-10-16"], // local time, not UTC
    ["2026-10-25T01:30:00Z", "Europe/Berlin", 4, "2026-10-24"], // 02:30 the day DST ends
    ["2026-10-25T03:00:00Z", "Europe/Berlin", 4, "2026-10-25"], // 04:00 CET
    ["2026-03-08T10:59:00Z", "America/Los_Angeles", 4, "2026-03-07"], // 03:59 PDT, DST began at 02:00
    ["2026-03-08T11:00:00Z", "America/Los_Angeles", 4, "2026-03-08"], // 04:00 PDT
    ["2026-12-14T15:00:00Z", "Pacific/Auckland", 4, "2026-12-15"], // 04:00 NZDT, a day ahead of UTC
    ["2026-03-08T04:59:59Z", "America/Havana", 0, "2026-03-07"], // before a midnight DST gap
    ["2026-03-08T05:00:00Z", "America/Havana", 0, "2026-03-08"], // the gap's day starts at 01:00
  ])("%s in %s, day starting at %i → %s", (instant, zone, hour, day) => {
    expect(learningDay(new Date(instant), zone, hour)).toBe(day);
  });
});

describe("examExample (R24, D11)", () => {
  // Red when: the example is today (refused: exam_date_not_in_future) or a fixed year.
  it.each([
    ["2026-12-14", "15/12/2026"],
    ["2026-12-15", "15/12/2027"], // an exam today is refused, so the example moves on
    ["2026-12-16", "15/12/2027"],
    ["2026-12-31", "15/12/2027"],
    ["2027-01-01", "15/12/2027"],
  ])("today %s → %s", (today, example) => {
    expect(examExample(today)).toBe(example);
  });
});

describe("exampleFor (R24, D11, D11b)", () => {
  // Red when: the example follows the server's clock or UTC instead of the user's learning day.
  it("15/12 05:00 in Vietnam is already 15/12 there (14/12 22:00 UTC): next year", () => {
    expect(exampleFor(new Date("2026-12-14T22:00:00Z"), "Asia/Ho_Chi_Minh", 4)).toBe("15/12/2027");
  });

  it("15/12 03:59 with a day starting at 04:00 is still 14/12: this year", () => {
    expect(exampleFor(new Date("2026-12-14T20:59:00Z"), "Asia/Ho_Chi_Minh", 4)).toBe("15/12/2026");
  });

  // Red when: an unknown zone throws, or falls back to a date that may be today.
  it("a zone it does not know gives next year's example, which is always accepted", () => {
    expect(exampleFor(new Date("2026-12-15T10:00:00Z"), "Not/AZone", 4)).toBe("15/12/2027");
  });
});
