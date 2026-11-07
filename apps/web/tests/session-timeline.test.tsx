// @vitest-environment jsdom
// SESSION-V4-RESTORE: the study session as the v4 mockup (session.html): app shell, composer that says
// WHERE the learner studied, "Đã học trong buổi" timeline (newest first) with an empty state from the
// start, no manual page-range form, no "Thẻ theo phần" block.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type SessionInitial, SessionScreen } from "@/components/session-study/session-screen";
import type { ApiResult, SessionApi } from "@/lib/session-study/api";
import { hhmm, pieceSources, pieceTitle } from "@/lib/session-study/piece-view";
import { initialRound } from "@/lib/session-study/round";

vi.mock("next/navigation", () => ({ usePathname: () => "/subjects/S/sessions/s1", useRouter: () => ({ push: vi.fn() }) }));

const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } as const;
const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });
const iso = (h: number, m: number) => new Date(2026, 10, 8, h, m).toISOString();

function api(pieces: unknown[] = [], over: Record<string, unknown> = {}) {
  return {
    sessionId: "s1",
    pieces: vi.fn(() => ok({ pieces, submitted: false })),
    addPiece: vi.fn(),
    removePiece: vi.fn(() => ok(null)),
    complete: vi.fn(() => ok({ status: "queued" })),
    submit: vi.fn(),
    upload: vi.fn(),
    result: vi.fn(),
    ...over,
  };
}

async function show(fake: ReturnType<typeof api>) {
  const initial: SessionInitial = { round: { ...initialRound }, text: "", mentions: [], files: [] };
  render(
    <SessionScreen
      api={fake as unknown as SessionApi}
      subject="Xác suất thống kê"
      subjectId="SUBJ"
      stopHref="/today"
      docs={[{ id: "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d", name: "Giáo trình", role: "Giáo trình chính" }]}
      suggestion={{ kind: "section", text: "Phần 1.2 · Quy tắc đếm", pace: "x" } as never}
      nextSuggestion={FREE}
      initial={initial}
      account={<span>acct</span>}
    />,
  );
  await act(async () => undefined);
}

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

describe("piece view helpers", () => {
  it("hhmm is the local HH:MM of the piece", () => {
    expect(hhmm(iso(20, 5))).toBe("20:05");
    expect(hhmm("not a date")).toBe("");
  });
  it("title is the first clause, clamped", () => {
    expect(pieceTitle("Quy tắc nhân. Việc gồm hai bước.")).toBe("Quy tắc nhân");
    expect(pieceTitle("a".repeat(100)).length).toBeLessThanOrEqual(61);
    expect(pieceTitle("")).toBe("");
  });
  it("sources come from page ranges in the note", () => {
    expect(pieceSources("học trang 20–25 @slide, tr. 14")).toEqual(["tr.20–25", "tr.14"]);
    expect(pieceSources("không có trang")).toEqual([]);
  });
});

describe("study session screen (v4)", () => {
  it("shows the empty timeline from the start, in the app shell, with no manual form", async () => {
    await show(api([]));
    expect(screen.getByRole("heading", { name: "Buổi học: Xác suất thống kê" })).toBeTruthy();
    expect(screen.getAllByText("Phần 1.2 · Quy tắc đếm").length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Đã học trong buổi" })).toBeTruthy();
    expect(screen.getByText("Chưa có gì được ghi lại")).toBeTruthy();
    expect(screen.getByText("Mỗi lần bấm Ghi lại sẽ thành một dòng ở đây.")).toBeTruthy();
    expect(screen.getByText("acct")).toBeTruthy();
    expect(screen.queryByText("Thẻ theo phần")).toBeNull();
    expect(screen.queryByRole("link", { name: "Dừng" })).toBeNull();
    // never a manual page-range form
    expect(screen.queryByLabelText(/từ trang|đến trang/i)).toBeNull();
    expect(screen.queryByText(/nhập thủ công/i)).toBeNull();
  });

  it("lists pieces newest first with time, title, note, source", async () => {
    await show(
      api([
        { id: "a", position: 0, text: "Quy tắc cộng. Hai phương án không trùng nhau, trang 12.", fileCount: 0, createdAt: iso(19, 58) },
        { id: "b", position: 1, text: "Quy tắc nhân. Hai bước liên tiếp.", fileCount: 1, createdAt: iso(20, 23) },
      ]),
    );
    const rows = within(screen.getByRole("list", { name: "Đã học trong buổi" })).getAllByRole("listitem");
    expect(rows).toHaveLength(2);
    expect(within(rows[0]).getByText("20:23")).toBeTruthy();
    expect(within(rows[0]).getByText("Quy tắc nhân")).toBeTruthy();
    expect(within(rows[1]).getByText("Nguồn tr.12")).toBeTruthy();
    expect(within(rows[1]).getByRole("button", { name: /Bỏ phần/ })).toBeTruthy();
    expect(screen.queryByText("Chưa có gì được ghi lại")).toBeNull();
    expect(screen.getByText("2 lần ghi")).toBeTruthy();
  });

  it("Ghi lại puts the new part on top at once", async () => {
    const fake = api([], {
      addPiece: vi.fn(() => ok({ id: "n", position: 0, text: "Chỉnh hợp. Có thứ tự.", fileCount: 0, createdAt: iso(21, 7) })),
    });
    await show(fake);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Chỉnh hợp. Có thứ tự." } });
    fireEvent.click(screen.getByRole("button", { name: "Ghi lại" }));
    await act(async () => undefined);
    expect(screen.getByText("21:07")).toBeTruthy();
    expect(screen.getByText("Chỉnh hợp")).toBeTruthy();
    expect(screen.queryByText("Chưa có gì được ghi lại")).toBeNull();
  });
});
