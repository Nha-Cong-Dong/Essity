// T9.5a (US-10 AC4, AC5, AC6; DESIGN §6.13): the pure grid and copy of the Thống kê screen. It
// mirrors core_api/domain/stats.py (T9.4a): weeks are columns from the Monday of the first week,
// weekdays are rows, future days stay empty, and nothing is a streak.
import { describe, expect, it } from "vitest";

import { buildGrid, daysLeftText, levelFor, monthLabels, percentOf } from "@/lib/stats";

const span = (id: string, created: string, exam: string | null) => ({ id, createdOn: created, examOn: exam });
const ev = (day: string, subjectId: string, cardsSaved = 0, questionsAnswered = 0, sections: string[] = []) => ({
  day,
  subjectId,
  sections,
  cardsSaved,
  questionsAnswered,
});

describe("levelFor", () => {
  // US-10 AC5. Red when: a boundary moves, or 0 work gets a tint.
  it.each([
    [0, 0],
    [1, 1],
    [3, 1],
    [4, 2],
    [9, 2],
    [10, 3],
    [19, 3],
    [20, 4],
    [200, 4],
  ])("AC5: work %s -> level %s", (work, level) => {
    expect(levelFor(work)).toBe(level);
  });
});

describe("buildGrid", () => {
  const A = span("a", "2026-10-26", "2026-11-04"); // Monday .. Wednesday
  // US-10 AC4. Red when: columns do not start on the Monday of the first week, or a day is lost.
  it("AC4: one cell per day from creation to the exam, weeks as columns, Monday row 0", () => {
    const cells = buildGrid([A], [], "2026-10-30");
    expect(cells.length).toBe(10);
    expect(cells[0]).toMatchObject({ day: "2026-10-26", column: 0, row: 0 });
    expect(cells[6]).toMatchObject({ day: "2026-11-01", column: 0, row: 6 });
    expect(cells[7]).toMatchObject({ day: "2026-11-02", column: 1, row: 0 });
  });

  // US-10 AC4. Red when: a creation day mid-week shifts the columns.
  it("AC4: a subject created on a Thursday still puts it in row 3 of column 0", () => {
    const cells = buildGrid([span("a", "2026-10-29", null)], [], "2026-10-30");
    expect(cells.map((c) => [c.column, c.row])).toEqual([
      [0, 3],
      [0, 4],
    ]);
  });

  // US-10 AC6. Red when: days after today carry a level or the exam day is not marked.
  it("AC6: days after today are empty and future; the exam day is marked", () => {
    const cells = buildGrid([A], [ev("2026-11-03", "a", 5, 5)], "2026-10-30");
    const future = cells.filter((c) => c.future);
    expect(future.length).toBe(5);
    expect(future.every((c) => c.level === 0 && c.cardsSaved === 0)).toBe(true);
    expect(cells.filter((c) => c.examDay).map((c) => c.day)).toEqual(["2026-11-04"]);
  });

  // US-10 AC5. Red when: cards and answers are not added, or two events on a day are not merged.
  it("AC5: work is cards saved plus questions answered, merged per day", () => {
    const cells = buildGrid([A], [ev("2026-10-27", "a", 3, 1, ["s1"]), ev("2026-10-27", "a", 2, 4, ["s2", "s1"])], "2026-10-30");
    const day = cells.find((c) => c.day === "2026-10-27");
    expect(day).toMatchObject({ cardsSaved: 5, questionsAnswered: 5, level: 3, sections: ["s1", "s2"] });
  });

  // US-10 AC4. Red when: filtering by subject keeps another subject's work.
  it("AC4: a subject filter drops the other subjects", () => {
    const B = span("b", "2026-10-26", null);
    const events = [ev("2026-10-27", "a", 1), ev("2026-10-27", "b", 20)];
    expect(buildGrid([A, B], events, "2026-10-30", "a").find((c) => c.day === "2026-10-27")?.level).toBe(1);
    expect(buildGrid([A, B], events, "2026-10-30").find((c) => c.day === "2026-10-27")?.level).toBe(4);
    expect(buildGrid([A, B], events, "2026-10-30", "missing")).toEqual([]);
  });

  // US-10 §6.13. Red when: a subject without an exam keeps the grid running past today.
  it("no exam: the grid stops today and has no exam marker", () => {
    const cells = buildGrid([span("a", "2026-10-26", null)], [], "2026-10-30");
    expect(cells.at(-1)?.day).toBe("2026-10-30");
    expect(cells.some((c) => c.examDay || c.future)).toBe(false);
  });

  // domain parity. Red when: activity before creation is cut off.
  it("activity earlier than the creation day pulls the start earlier", () => {
    const cells = buildGrid([span("a", "2026-10-29", null)], [ev("2026-10-20", "a", 2)], "2026-10-30");
    expect(cells[0].day).toBe("2026-10-20");
  });
});

describe("copy helpers", () => {
  // US-10 AC1. Red when: the exam countdown turns negative or loses its unit.
  it.each([
    [60, "còn 60 ngày"],
    [1, "còn 1 ngày"],
    [0, "thi hôm nay"],
    [-3, "đã thi"],
  ])("AC1: days left %s", (n, text) => {
    expect(daysLeftText(n)).toBe(text);
  });

  it("percentOf rounds and guards zero", () => {
    expect(percentOf(23, 52)).toBe(44);
    expect(percentOf(0, 0)).toBeNull();
  });

  // US-10 AC4. Red when: a month label lands on a column that does not hold that month's first week.
  it("monthLabels names the first column of each month", () => {
    const cells = buildGrid([span("a", "2026-10-26", "2026-12-15")], [], "2026-10-30");
    expect(monthLabels(cells).map((m) => [m.column, m.label])).toEqual([
      [0, "Th10"],
      [1, "Th11"],
      [6, "Th12"],
    ]);
  });
});

import { cellLabel, dayLabel, levelLegend, sectionsText } from "@/lib/stats";

describe("day copy", () => {
  const cells = buildGrid([span("a", "2026-10-26", "2026-11-04")], [ev("2026-10-28", "a", 12, 8, ["Mục 1.1"])], "2026-10-30");
  const at = (day: string) => cells.find((c) => c.day === day)!;

  it("dayLabel names the weekday and the day/month", () => {
    expect(dayLabel("2026-10-28")).toBe("Thứ tư, 28/10");
    expect(dayLabel("2026-11-01")).toBe("Chủ nhật, 1/11");
  });

  // US-10 AC4, AC6. Red when: an empty day reads as a failure, or the numbers drop out of the label.
  it("AC4: cell labels carry the numbers; empty and future days are neutral", () => {
    expect(cellLabel(at("2026-10-28"), "2026-10-30")).toBe("Thứ tư, 28/10: 12 thẻ đã lưu, 8 câu đã làm");
    expect(cellLabel(at("2026-10-27"), "2026-10-30")).toBe("Thứ ba, 27/10: không có ghi nhận");
    expect(cellLabel(at("2026-10-30"), "2026-10-30")).toMatch(/^Hôm nay, /);
    expect(cellLabel(at("2026-11-02"), "2026-10-30")).toBe("Thứ hai, 2/11: chưa tới ngày này");
    expect(cellLabel(at("2026-11-04"), "2026-10-30")).toBe("Thứ tư, 4/11: ngày thi, chưa tới ngày này");
  });

  // US-10 AC5 §6.13. Red when: the legend invents thresholds instead of reading LEVEL_FLOORS.
  it("the legend prints the thresholds from LEVEL_FLOORS", () => {
    expect(levelLegend()).toBe("1 · 4 · 10 · 20 việc mỗi ngày trở lên");
  });

  it("sectionsText lists at most five and counts the rest", () => {
    expect(sectionsText(["a", "b"])).toBe("a, b");
    expect(sectionsText(["a", "b", "c", "d", "e", "f", "g"])).toBe("a, b, c, d, e và 2 mục khác");
  });
});
