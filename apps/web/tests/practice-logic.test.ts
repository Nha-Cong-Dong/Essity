// T8.7a (US-16 AC2, AC5; DESIGN §6.12): the pure copy and ordering of the Luyện tập screen.
import { describe, expect, it } from "vitest";

import { masteryText, orderedRows, summaryLine, timingLine, type PracticeQuestion } from "@/lib/practice";

const q = (id: string, status: PracticeQuestion["status"], extra: Partial<PracticeQuestion> = {}): PracticeQuestion => ({
  id,
  number: Number(id.slice(1)),
  summary: id,
  origin: "bank",
  status,
  answerSource: "bank",
  practiced: false,
  mastered: false,
  ...extra,
});

describe("masteryText", () => {
  // US-16 AC2. Red when: a type with under 3 attempts shows a ratio, or a half point loses its comma.
  it.each([
    [0, 0, "chưa đủ dữ liệu"],
    [2, 2, "chưa đủ dữ liệu"],
    [3, 3, "đúng 3 trên 3 lần gần nhất"],
    [7, 10, "đúng 7 trên 10 lần gần nhất"],
    [6.5, 10, "đúng 6,5 trên 10 lần gần nhất"],
    [4, 7, "đúng 4 trên 7 lần gần nhất"],
  ])("AC2: %s of %s attempts", (score, attempts, text) => {
    expect(masteryText({ score, attempts })).toBe(text);
  });
});

describe("timingLine", () => {
  // US-16 AC5. Red when: a reference is shown without being measured, or a clock appears.
  it("AC5: words plus the reference minutes", () => {
    expect(timingLine({ kind: "faster", refMinutes: 3 })).toBe("thường nhanh hơn mốc tham khảo · khoảng 3 phút mỗi câu");
    expect(timingLine({ kind: "unmeasured" })).toBe("chưa đo");
    expect(timingLine({ kind: "unknown" })).toBe("chưa đủ dữ liệu");
  });
});

describe("orderedRows and summaryLine", () => {
  // US-16 AC1. Red when: waiting rows come before ready ones, or the summary disagrees with the rows.
  it("AC1: ready first (never-attempted before practiced), then waiting; removed rows drop out", () => {
    const rows = [q("q1", "waiting"), q("q2", "ready", { practiced: true }), q("q3", "ready"), q("q4", "ready")];
    expect(orderedRows(rows, new Set(["q4"])).map((r) => r.id)).toEqual(["q3", "q2", "q1"]);
  });
  it("AC1: counts ready, practiced and mastered", () => {
    const rows = [q("q1", "ready"), q("q2", "ready", { practiced: true, mastered: true }), q("q3", "waiting")];
    expect(summaryLine(rows, new Set())).toBe("2 câu sẵn sàng · 1 đã luyện · 1 đã thuộc");
    expect(summaryLine(rows, new Set(["q1"]))).toBe("1 câu sẵn sàng · 1 đã luyện · 1 đã thuộc");
  });
});
