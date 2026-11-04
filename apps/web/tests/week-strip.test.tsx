import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { WeekStrip, weekFromCells } from "@/components/today-v2/week-strip";

describe("week strip (V21)", () => {
  it("covers Monday to Sunday of the learning day's week and counts activity (cards saved + questions answered) per day", () => {
    const week = weekFromCells([{ day: "2026-11-02", cardsSaved: 2, questionsAnswered: 1 }], "2026-11-04");
    expect(week.map((c) => c.day)).toEqual([
      "2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-07", "2026-11-08",
    ]);
    expect(week.map((c) => c.count)).toEqual([3, 0, 0, 0, 0, 0, 0]);
  });

  it("marks today and shows no streak wording", () => {
    const week = weekFromCells([], "2026-11-08");
    const html = renderToStaticMarkup(<WeekStrip cells={week} today="2026-11-08" />);
    expect(html).toContain("Hoạt động mỗi ngày");
    expect(html).not.toContain("Mỗi cột");
    expect(html).toMatch(/aria-current="date"[^>]*>.*?CN/);
    expect(html).not.toMatch(/chuỗi|streak/i);
  });

  it("an all-zero week says so in one line and marks today with a dot, not an outline", () => {
    const html = renderToStaticMarkup(<WeekStrip cells={weekFromCells([], "2026-11-08")} today="2026-11-08" />);
    expect(html).toContain("data-week-empty");
    expect(html).not.toContain("outline-ink");
    const busy = renderToStaticMarkup(<WeekStrip cells={weekFromCells([{ day: "2026-11-02", cardsSaved: 1, questionsAnswered: 0 }], "2026-11-04")} today="2026-11-04" />);
    expect(busy).not.toContain("data-week-empty");
  });
});
