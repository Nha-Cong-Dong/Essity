// @vitest-environment jsdom
// T9.5a (US-10 AC1, AC4-AC7, AC10; DESIGN §6.13): the Thống kê screen from fixtures.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StatsScreen as Screen } from "@/components/stats/stats-screen";
import { STATS_STATE_IDS, statsFixture, type StatsState } from "@/lib/fixtures/stats";
import { buildGrid } from "@/lib/stats";

const nav = vi.hoisted(() => ({ replace: vi.fn(), query: "" }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: nav.replace, refresh: nav.replace }),
  usePathname: () => "/design-preview/stats",
  useSearchParams: () => new URLSearchParams(nav.query),
}));


/** What /design-preview/stats passes: the fixture as a view, the grid for the ?subject= in nav.query. */
function StatsScreen({ state }: { state: StatsState }) {
  const data = statsFixture(state);
  const wanted = new URLSearchParams(nav.query).get("subject") ?? "";
  const chosen = data.subjects.find((s) => s.id === wanted)?.id;
  const view = { today: data.today, subjects: data.subjects, cells: buildGrid(data.subjects, data.events, data.today, chosen), totals: { unitsLearned: 7, unitsTotal: 20, sessions: 3, cardsSaved: 11, cardsReviewed: 42, practiceDone: 9 } };
  const mode = state === "loading" || state === "error" ? state : "ready";
  return <Screen view={view} subject={chosen ?? ""} mode={mode} />;
}

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

describe("overall stats (I1, I2)", () => {
  // Red when: per-subject blocks come back, or the totals / seven weekday labels go missing.
  it("shows totals and no per-subject block", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const kpis = [...container.querySelectorAll("[data-kpi]")].map((k) => k.textContent);
    expect(kpis).toHaveLength(3);
    expect(kpis.join("|")).toContain("42");
    expect(container.querySelector("[data-subject-block]")).toBeNull();
    expect(container.querySelector("#stats-subject")).toBeNull();
    expect(container.querySelector("[data-trend]")).not.toBeNull();
  });
  it("labels all seven weekdays", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    const text = container.querySelector("[data-activity-grid]")?.textContent ?? "";
    for (const d of ["T2", "T3", "T4", "T5", "T6", "T7", "CN"]) expect(text).toContain(d);
  });
});

describe("UI-NITS-0811: charts always render", () => {
  const noData = { today: "2026-10-30", subjects: [], cells: [], totals: undefined } as never;
  it("UI-NITS-0811: no subjects and no cells still draws the trend and the year chart, each with Chưa có số liệu", () => {
    const { container } = render(<Screen view={noData} mode="ready" />);
    expect(container.querySelector("[data-trend]")).not.toBeNull();
    const empties = container.querySelectorAll("[data-empty-chart]");
    expect(empties.length).toBe(2);
    for (const e of empties) expect(e.textContent).toContain("Chưa có số liệu");
    expect(container.querySelector("#activity")).not.toBeNull();
    expect(container.querySelectorAll(PRIMARY).length).toBe(1);
  });
  it("UI-NITS-0811: a state with subjects but no days marks the charts as empty too", () => {
    const { container } = render(<StatsScreen state="empty" />);
    expect(container.querySelector("[data-trend]")).not.toBeNull();
    expect(container.querySelectorAll("[data-empty-chart]").length).toBeGreaterThan(0);
  });
  it("UI-NITS-0811: a full year has no empty-chart notes", () => {
    const { container } = render(<StatsScreen state="full-year" />);
    expect(container.querySelectorAll("[data-empty-chart]").length).toBe(0);
  });
});
