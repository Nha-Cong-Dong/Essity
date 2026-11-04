// @vitest-environment jsdom
// UI-A (user 05/11): the year heatmap changes its detail on a click or Enter / Space, never on hover
// or focus; no "Xem dạng danh sách"; every cell is a focusable button named with date and activity.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ActivityGrid } from "@/components/stats/activity-grid";
import type { GridCell } from "@/lib/stats";

const cell = (day: string, column: number, row: number, cards: number, questions: number): GridCell => ({
  day,
  column,
  row,
  level: cards + questions > 0 ? 1 : 0,
  future: false,
  examDay: false,
  subjects: [],
  sections: [],
  cardsSaved: cards,
  questionsAnswered: questions,
});

const CELLS = [cell("2026-11-02", 0, 0, 2, 1), cell("2026-11-03", 0, 1, 0, 0), cell("2026-11-04", 0, 2, 4, 0)];
const detail = () => (document.querySelector("[data-day-detail]") as HTMLElement).textContent ?? "";

afterEach(cleanup);

describe("ActivityGrid selection (UI-A)", () => {
  const draw = () => render(<ActivityGrid cells={CELLS} today="2026-11-04" subjects={[]} examBy={{}} />);

  it("opens on today and keeps the detail when the pointer or the focus moves over other cells", () => {
    draw();
    expect(detail()).toContain("hôm nay");
    const first = screen.getAllByRole("button").find((b) => b.getAttribute("data-day") === "2026-11-02") as HTMLElement;
    fireEvent.mouseEnter(first);
    fireEvent.mouseOver(first);
    expect(detail()).toContain("hôm nay");
    fireEvent.focus(first);
    expect(detail()).toContain("hôm nay");
  });

  it("changes the detail on a click and marks the selected cell", () => {
    draw();
    const first = screen.getAllByRole("button").find((b) => b.getAttribute("data-day") === "2026-11-02") as HTMLElement;
    fireEvent.click(first);
    expect(detail()).toContain("2 thẻ đã lưu · 1 câu đã làm");
    expect(first.getAttribute("data-pinned")).toBe("true");
    expect(first.getAttribute("aria-pressed")).toBe("true");
  });

  it("selects with Enter and Space on the focused cell", () => {
    draw();
    const [first, second] = screen.getAllByRole("button").filter((b) => b.hasAttribute("data-day"));
    fireEvent.keyDown(first, { key: "Enter" });
    expect(detail()).toContain("2 thẻ đã lưu");
    fireEvent.keyDown(second, { key: " " });
    expect(detail()).toContain("Không có ghi nhận ngày này.");
  });

  it("has no list view, and names each cell with its date and activity", () => {
    draw();
    expect(screen.queryByText("Xem dạng danh sách")).toBeNull();
    expect(document.querySelector("[data-alt-list]")).toBeNull();
    const labels = screen.getAllByRole("button").map((b) => b.getAttribute("aria-label") ?? "");
    expect(labels.some((l) => l.includes("2 thẻ đã lưu, 1 câu đã làm"))).toBe(true);
  });
});
