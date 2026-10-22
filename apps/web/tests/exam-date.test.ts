// T1.20, plan K10: the exam date is typed day/month/year and sent as ISO (US-01 AC2).
import { describe, expect, it } from "vitest";

import { daysLeftText, formatExamDate, parseExamDate } from "@/lib/exam-date";
import { dateFormatMessage, SUBJECT_MESSAGES } from "@/lib/subject-copy";

describe("parseExamDate (plan K10)", () => {
  it.each([
    ["15/12/2026", "2026-12-15"],
    ["1/2/2027", "2027-02-01"],
    [" 05/01/2027 ", "2027-01-05"],
    ["29/02/2028", "2028-02-29"], // a leap year
    ["15-12-2026", "2026-12-15"], // dash or dot accepted too (plan K10, flow-expert)
    ["15.12.2026", "2026-12-15"],
  ])("%j is %s", (typed, iso) => {
    expect(parseExamDate(typed)).toEqual({ value: iso });
  });

  // Red when: a date the calendar does not have, or another way of writing it, gets through
  // (new Date("31/02") would roll it into March).
  it.each([
    "31/02/2027",
    "29/02/2027", // not a leap year
    "31/04/2027",
    "0/12/2026",
    "15/13/2026",
    "15/12/26", // two-digit year
    "15/12", // no year: the sentence's example shows one (plan K10)
    "15/12-2026", // mixed separators
    "2026-12-15",
    "15 / 12 / 2026",
    "15/12/2026x",
    "",
    "   ",
    "١٥/١٢/٢٠٢٦",
  ])("%j is refused", (typed) => {
    expect(parseExamDate(typed)).toEqual({ error: "date_format" });
  });
});

describe("showing an exam date", () => {
  it("the field shows day/month/year", () => {
    expect(formatExamDate("2026-12-15")).toBe("15/12/2026");
    expect(formatExamDate("2027-02-01")).toBe("01/02/2027");
  });

  // From core-api's days_until_exam (plan K3), never computed here.
  it.each([
    [55, "còn 55 ngày"],
    [1, "còn 1 ngày"],
    [0, "thi hôm nay"],
    [-3, "đã thi"],
  ])("%i days → %s", (days, text) => {
    expect(daysLeftText(days)).toBe(text);
  });
});

describe("subject sentences (DESIGN.md §6.8; chosen by the user 22/10)", () => {
  it("US-01 AC2: each refusal says what to type", () => {
    expect(SUBJECT_MESSAGES.exam_date_not_in_future).toBe("Ngày thi phải sau hôm nay.");
    // The user's sentence (plan K7); only the example's year follows the date (R24, D12).
    expect(dateFormatMessage("15/12/2031")).toBe("Nhập ngày theo dạng ngày/tháng/năm, ví dụ 15/12/2031.");
    expect(SUBJECT_MESSAGES.name_empty).toBe("Nhập tên môn, ví dụ Mạng máy tính.");
    expect(SUBJECT_MESSAGES.saved).toBe("Đã lưu.");
  });
});
