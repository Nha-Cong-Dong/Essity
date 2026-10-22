// T1.18, US-11 AC3: what the baseline screen accepts before anything is sent (DESIGN.md §6.2).
import { describe, expect, it } from "vitest";

import { BASELINE_MESSAGES } from "@/lib/baseline-copy";
import { parseDays, parseGpa } from "@/lib/baseline-input";

describe("parseGpa (US-11 AC3)", () => {
  // Red when: the comma is no longer turned into a dot (core-api only reads dots, plan B7).
  it.each([
    ["2,85", "2.85"],
    ["2.85", "2.85"],
    ["0", "0"],
    ["4", "4"],
    ["4.00", "4.00"],
    [" 3.5 ", "3.5"],
  ])("AC3: %j is sent as %j", (typed, sent) => {
    expect(parseGpa(typed)).toEqual({ value: sent });
  });

  // Red when: the range check goes (a 4.5 or a "-1" would reach core-api).
  it.each(["4.5", "4.01", "-1", "abc", "", "  ", "1e0", "2..5", ".5", "2.", "0x2", "٣"])(
    "AC3: %j is outside the 4-point scale",
    (typed) => {
      expect(parseGpa(typed)).toEqual({ error: "gpa_range" });
    },
  );

  // Red when: 2.857 is rounded to 2.86 (a quietly changed baseline, plan B7) or read as out of range.
  it.each(["2.857", "3,141", "0.001"])("AC3: %j has more than two decimals", (typed) => {
    expect(parseGpa(typed)).toEqual({ error: "gpa_decimals" });
  });

  it("AC3: 4.001 is out of range before it is too precise", () => {
    expect(parseGpa("4.001")).toEqual({ error: "gpa_range" });
  });
});

describe("parseDays (US-11 AC1, AC3)", () => {
  it.each([
    ["0", 0],
    ["12", 12],
    ["365", 365],
    [" 7 ", 7],
  ])("AC1: %j is %i days", (typed, days) => {
    expect(parseDays(typed)).toEqual({ value: days });
  });

  // Red when: a day count outside 0–365, or not a whole number, gets through.
  it.each(["-1", "366", "1.5", "1,5", "abc", "", "1e2", "٣"])("AC3: %j is refused", (typed) => {
    expect(parseDays(typed)).toEqual({ error: "days_range" });
  });
});

describe("baseline sentences (DESIGN.md §6.2, chosen by the user 22/10)", () => {
  it("AC3: each refusal says what to type", () => {
    expect(BASELINE_MESSAGES.gpa_range).toBe("GPA thang 4 nằm trong khoảng 0 đến 4.");
    expect(BASELINE_MESSAGES.gpa_decimals).toBe("GPA nhập tối đa 2 chữ số sau dấu chấm, ví dụ 2.85.");
    expect(BASELINE_MESSAGES.days_range).toBe("Số ngày là số nguyên từ 0 đến 365.");
  });
});
