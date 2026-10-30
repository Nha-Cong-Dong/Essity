// @vitest-environment jsdom
// T9.5a (US-10 AC1, AC4-AC7, AC10; DESIGN §6.13): the Thống kê screen from fixtures.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatsScreen } from "@/components/stats/stats-screen";
import { STATS_STATE_IDS, type StatsState } from "@/lib/fixtures/stats";
import { LEVEL_FLOORS } from "@/lib/stats";

const nav = vi.hoisted(() => ({ replace: vi.fn(), query: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace }),
  usePathname: () => "/design-preview/stats",
  useSearchParams: () => new URLSearchParams(nav.query),
}));

afterEach(() => {
  cleanup();
  nav.query = "";
  nav.replace.mockReset();
});

const PRIMARY = "[data-variant='primary']";
// DESIGN §4 and §6.13. Only the words the app writes are scanned: a subject or type name is the
// user's own text. JS \b is ASCII-only, so the edges are Unicode lookarounds.
const FORBIDDEN =
  /(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|trễ|kém|lười|bỏ lỡ|thất bại|tụt|hạng|sẵn sàng thi|sẵn sàng\s*\/\s*chưa sẵn sàng)(?!\p{L})/iu;

function appCopy(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("[data-user]").forEach((el) => el.remove());
  return clone.textContent ?? "";
}

describe("banned words", () => {
  // Red when: the pattern stops matching Vietnamese words (\b never matched "trễ").
  it.each(["đã trễ", "Chuỗi ngày", "xếp hạng", "tụt hạng", "sẵn sàng thi"])("%s is caught", (text) => {
    expect(text).toMatch(FORBIDDEN);
  });
  it("lets the bank's own column through", () => {
    expect("Câu sẵn sàng").not.toMatch(FORBIDDEN);
    expect("trễnải").not.toMatch(FORBIDDEN);
  });
});

describe("every state", () => {
  // US-10 AC6, AC7. Red when: a state shows a banned word, has two primaries, or a normal state has one.
  const PRIMARIES: Record<StatsState, number> = {
    empty: 1,
    "few-days": 0,
    "full-year": 0,
    "many-subjects": 0,
    "no-exam": 0,
    "no-bank": 0,
    loading: 0,
    error: 1,
  };
  it.each(STATS_STATE_IDS)("%s: at most one primary, no banned word, no comparison arrow", (state) => {
    const { container } = render(<StatsScreen state={state} />);
    expect(container.querySelectorAll(PRIMARY).length).toBe(PRIMARIES[state]);
    expect(appCopy(container)).not.toMatch(FORBIDDEN);
    expect(container.textContent).not.toMatch(/[↑↓▲▼]/u);
    expect(container.querySelectorAll("[role=alert]").length).toBe(state === "error" ? 1 : 0);
  });
});

describe("blocks", () => {
  // US-10 AC1. Red when: a metric from the card is missing or a verdict appears.
  it("AC1: each subject shows exam countdown, syllabus, bank and retention as words", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const block = container.querySelector("[data-subject-block]") as HTMLElement;
    expect(within(block).getByText(/Thi 15\/12\/2026 · còn 46 ngày/)).toBeTruthy();
    expect(within(block).getByText("23/52 mục")).toBeTruthy();
    expect(within(block).getByText("310/820 trang")).toBeTruthy();
    expect(within(block).getByText("Đã thuộc 3 / 18 câu sẵn sàng")).toBeTruthy();
    expect(within(block).getByText("72%")).toBeTruthy();
    expect(container.textContent).not.toMatch(/Sẵn sàng\b.*Chưa sẵn sàng/);
  });

  // US-10 AC10. Red when: skipped cards vanish or turn into a judgement.
  it("AC10: skipped cards are a neutral count", () => {
    render(<StatsScreen state="full-year" />);
    expect(screen.getByText(/Đã bỏ qua 4 thẻ/)).toBeTruthy();
  });

  // DESIGN §6.13. Red when: a subject with no bank hides the gap, or no exam counts down.
  it("no bank says so; no exam does not count down", () => {
    render(<StatsScreen state="no-bank" />);
    expect(screen.getByText("Chưa có bộ câu hỏi.")).toBeTruthy();
    cleanup();
    render(<StatsScreen state="no-exam" />);
    expect(screen.getByText("Chưa đặt ngày thi")).toBeTruthy();
    expect(screen.queryByText(/còn \d+ ngày/)).toBeNull();
    expect(document.querySelector("[data-exam='true']")).toBeNull();
  });

  // Plan: the bars repeat a number, so they are hidden from a screen reader.
  it("the thin bars are decoration", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const bars = container.querySelectorAll("[data-coverage-bar]");
    expect(bars.length).toBeGreaterThan(0);
    bars.forEach((bar) => expect(bar.getAttribute("aria-hidden")).toBe("true"));
  });

  // US-10 AC4. Red when: the filter does not narrow the blocks, or the select loses its label.
  it("AC4: ?subject= shows one block; the select changes it by URL", () => {
    nav.query = "state=many-subjects&subject=0b8f1d2e-0000-4000-8000-000000000002";
    const { container } = render(<StatsScreen state="many-subjects" />);
    expect(container.querySelectorAll("[data-subject-block]").length).toBe(1);
    const select = screen.getByLabelText("Môn") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "" } });
    expect(nav.replace).toHaveBeenCalledWith("/design-preview/stats?state=many-subjects", { scroll: false });
  });

  // US-10 §6.13. Red when: many subjects with a new one asks for a primary in every block.
  it("many subjects: a scope with no recorded day gets the one primary, in the grid panel", () => {
    nav.query = "subject=0b8f1d2e-0000-4000-8000-000000000102";
    const { container } = render(<StatsScreen state="many-subjects" />);
    const primaries = container.querySelectorAll(PRIMARY);
    expect(primaries.length).toBe(1);
    expect(primaries[0].closest("#activity")).not.toBeNull();
  });
});

describe("activity grid", () => {
  const cells = (container: HTMLElement) => [...container.querySelectorAll<HTMLButtonElement>("[data-day]")];

  // US-10 AC4, AC6. Red when: a day has no readable label, or the grid has more than one tab stop.
  it("AC4: every day is a labelled button; one tab stop", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const all = cells(container);
    expect(all.length).toBeGreaterThan(300);
    expect(all.every((c) => (c.getAttribute("aria-label") ?? "").length > 5)).toBe(true);
    expect(all.filter((c) => c.tabIndex === 0).length).toBe(1);
    expect(all.find((c) => c.tabIndex === 0)?.getAttribute("data-today")).toBe("true");
  });

  // US-10 AC6. Red when: an empty day carries a warning, or a future day carries a tint.
  it("AC6: future days are empty; the exam day is a marked cell; today is marked", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const all = cells(container);
    expect(all.filter((c) => c.dataset.future === "true").every((c) => c.dataset.level === "0")).toBe(true);
    expect(all.filter((c) => c.dataset.exam === "true").length).toBeGreaterThanOrEqual(1);
    expect(all.filter((c) => c.dataset.today === "true").length).toBe(1);
    expect(container.querySelectorAll("[role=grid]").length).toBe(1);
  });

  // US-10 AC4. Red when: pressing a day does not show its numbers, or live announcements fire on hover.
  it("AC4: click pins a day and says it once; hover only changes the panel", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const day = cells(container).find((c) => c.dataset.level === "4") as HTMLButtonElement;
    const panel = container.querySelector("[data-day-detail]") as HTMLElement;
    fireEvent.mouseEnter(day);
    expect(panel.textContent).toMatch(/thẻ đã lưu · \d+ câu đã làm/);
    expect(container.querySelector("[role=status]")?.textContent).toBe("");
    fireEvent.mouseLeave(day);
    fireEvent.click(day);
    expect(container.querySelector("[role=status]")?.textContent).toBe(day.getAttribute("aria-label"));
  });

  // US-10 AC4. Red when: arrows leave the grid, skip the week step, or the focus ring is lost.
  it("AC4: arrows move by day and by week; focus stays on a cell", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const byDay = (day: string) => container.querySelector(`[data-day="${day}"]`) as HTMLButtonElement;
    const today = byDay("2026-10-30");
    today.focus();
    fireEvent.keyDown(today, { key: "ArrowUp" });
    expect(document.activeElement).toBe(byDay("2026-10-29"));
    fireEvent.keyDown(byDay("2026-10-29"), { key: "ArrowLeft" });
    expect(document.activeElement).toBe(byDay("2026-10-22"));
    expect(byDay("2026-10-22").tabIndex).toBe(0);
    expect(today.tabIndex).toBe(-1);
  });

  // US-10 AC4. Red when: the previous/next buttons stop moving the pinned day.
  it("AC4: Ngày trước and Ngày sau move the pinned day", () => {
    const { container } = render(<StatsScreen state="few-days" />);
    const panel = container.querySelector("[data-day-detail]") as HTMLElement;
    expect(panel.textContent).toMatch(/hôm nay/);
    fireEvent.click(within(panel).getByRole("button", { name: "Ngày trước" }));
    expect(panel.textContent).toMatch(/Thứ năm, 29\/10/);
    expect(panel.textContent).not.toMatch(/hôm nay/);
    fireEvent.click(within(panel).getByRole("button", { name: "Ngày sau" }));
    expect(panel.textContent).toMatch(/hôm nay/);
  });

  // US-10 AC4 (accessible alternative). Red when: the list shows empty days or drops the caption.
  it("AC4: the list alternative is a captioned table of the days with work", () => {
    const { container } = render(<StatsScreen state="few-days" />);
    const list = container.querySelector("[data-alt-list]") as HTMLElement;
    expect(list.getAttribute("role")).toBe("region");
    expect(list.querySelector("caption")).not.toBeNull();
    expect(list.querySelectorAll("tbody tr").length).toBe(2);
    expect(within(list).getByText("Thứ năm, 29/10")).toBeTruthy();
  });

  // US-10 AC5, §6.13. Red when: the legend invents thresholds instead of reading LEVEL_FLOORS.
  it("the legend prints the thresholds of LEVEL_FLOORS", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    expect(container.querySelector("[data-legend]")?.textContent).toContain(`${LEVEL_FLOORS.join(" · ")} việc mỗi ngày`);
  });

  // US-10 §6.13. Red when: a today with no work reads as a lack.
  it("an empty today is a plain fact", () => {
    const { container } = render(<StatsScreen state="no-exam" />);
    const today = cells(container).find((c) => c.dataset.today === "true") as HTMLButtonElement;
    expect(today).toBeTruthy();
    fireEvent.mouseEnter(cells(container).find((c) => c.dataset.level === "0" && c.dataset.future === "false") as HTMLElement);
    expect((container.querySelector("[data-day-detail]") as HTMLElement).textContent).toMatch(/Không có ghi nhận|không có|thẻ đã lưu/);
  });
});

describe("states", () => {
  // DESIGN §6.13. Red when: loading shows data or a primary, or error loses focus/alert.
  it("loading is a busy skeleton; error is an alert with the one primary", () => {
    const loading = render(<StatsScreen state="loading" />);
    expect(loading.container.querySelector("[aria-busy=true]")).not.toBeNull();
    expect(loading.container.querySelector("[data-day]")).toBeNull();
    loading.unmount();
    const error = render(<StatsScreen state="error" />);
    expect(screen.getByRole("alert").textContent).toContain("Không tải được thống kê.");
    expect(document.activeElement).toBe(screen.getByRole("alert"));
    expect(error.container.querySelector(PRIMARY)?.textContent).toBe("Thử lại");
  });

  it("empty says the grid arrives after the first week", () => {
    render(<StatsScreen state="empty" />);
    expect(screen.getByText("Thống kê hiện sau tuần học đầu tiên. Nộp bài ở một buổi học để bắt đầu.")).toBeTruthy();
  });
});
