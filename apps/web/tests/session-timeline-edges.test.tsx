// @vitest-environment jsdom
// SESSION-V4-RESTORE tester: edge cases of the v4 study session the lane tests do not pin: the
// header and plum card name the section (or "Học tự do"), the old suggestion block stays out of
// piece mode, the note body shows under the title, "Ghi lại ngay" then a real end is not the empty
// pop-up, a part cannot be dropped while the session is being handed in, and created_at reaches the row.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { END_COPY } from "@/components/session-study/session-end-dialog";
import { type SessionInitial, SessionScreen } from "@/components/session-study/session-screen";
import { type ApiResult, type SessionApi, createSessionApi } from "@/lib/session-study/api";
import { initialRound } from "@/lib/session-study/round";

vi.mock("next/navigation", () => ({ usePathname: () => "/subjects/S/sessions/s1", useRouter: () => ({ push: vi.fn() }) }));

const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } as const;
const SECTION = { kind: "section", text: "Phần 1.2 · Quy tắc đếm", reason: "r", pace: "x" } as const;
const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });

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

async function show(fake: ReturnType<typeof api>, suggestion: typeof FREE | typeof SECTION = SECTION) {
  const initial: SessionInitial = { round: { ...initialRound }, text: "", mentions: [], files: [] };
  render(
    <SessionScreen
      api={fake as unknown as SessionApi}
      subject="Xác suất thống kê"
      subjectId="SUBJ"
      stopHref="/today"
      docs={[]}
      suggestion={suggestion as never}
      nextSuggestion={FREE}
      initial={initial}
      account={<span>acct</span>}
    />,
  );
  await act(async () => undefined);
}

const assign = vi.fn();
beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
  assign.mockReset();
  Object.defineProperty(window, "location", { configurable: true, value: { ...window.location, assign } });
  window.localStorage.clear();
});
afterEach(cleanup);

const plumCard = () => screen.getByText("Đang học").parentElement as HTMLElement;

describe("v4 session header and plum card", () => {
  // Red when: the line under "Buổi học: <môn>" shows anything but the section the suggestion opened.
  it("names the section under the title and in the plum card", async () => {
    await show(api());
    expect(screen.getByTestId("session-section").textContent).toBe(SECTION.text);
    expect(plumCard().textContent).toContain(SECTION.text);
    expect(plumCard().textContent).not.toContain("Xác suất thống kê");
  });

  // Red when: a free session loses its "Học tự do" line, or the old suggestion block comes back in piece mode.
  it("a free session says Học tự do and has no suggestion block", async () => {
    await show(api(), FREE);
    expect(screen.getByTestId("session-section").textContent).toBe("Học tự do");
    expect(plumCard().textContent).toContain("Học tự do");
    expect(screen.queryByText(FREE.text)).toBeNull();
  });
});

describe("v4 timeline rows", () => {
  // Red when: the note after the first clause is not shown under the title.
  it("shows the rest of the note under the title", async () => {
    await show(api([{ id: "a", position: 0, text: "Quy tắc nhân. Hai bước liên tiếp.", fileCount: 0 }]));
    const row = within(screen.getByRole("list", { name: "Đã học trong buổi" })).getByRole("listitem");
    expect(within(row).getByText("Quy tắc nhân")).toBeTruthy();
    expect(within(row).getByText("Hai bước liên tiếp.")).toBeTruthy();
  });

  // Red when: "Bỏ phần này" still drops a part while "Kết thúc buổi học" is handing the session in.
  it("does not drop a part while the session is being handed in", async () => {
    const fake = api([{ id: "a", position: 0, text: "Quy tắc cộng", fileCount: 0 }], { complete: vi.fn(() => new Promise(() => undefined)) });
    await show(fake);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    });
    expect(fake.complete).toHaveBeenCalled();
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Bỏ phần 1" }));
    });
    expect(fake.removePiece).not.toHaveBeenCalled();
  });
});

describe("empty end then a real end", () => {
  // Red when: after "Ghi lại ngay" the empty flag sticks, so ending with a part shows the empty pop-up again.
  it("Ghi lại ngay, write a part, end: the pop-up praises, not the empty variant", async () => {
    const fake = api([], { addPiece: vi.fn(() => ok({ id: "n", position: 0, text: "Chỉnh hợp", fileCount: 0 })) });
    await show(fake);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    });
    fireEvent.click(await screen.findByRole("button", { name: END_COPY.recordNow }));
    await act(async () => undefined);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Chỉnh hợp" } });
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    });
    expect(fake.complete).toHaveBeenCalledTimes(1);
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain(END_COPY.title);
    expect(dialog.textContent).not.toContain(END_COPY.emptyTitle);
    expect(screen.queryByRole("button", { name: END_COPY.recordNow })).toBeNull();
  });
});

describe("createSessionApi pieces", () => {
  // Red when: core-api's created_at does not reach the piece (the timeline would show no time).
  it("maps created_at to createdAt, on read and on Ghi lại", async () => {
    const at = "2026-11-08T13:05:00Z";
    const core = { id: "p", position: 0, text: "t", file_count: 2, created_at: at };
    const fn = vi.fn(async (_url: string, init: RequestInit = {}) =>
      init.method === "POST" ? Response.json(core, { status: 201 }) : Response.json({ pieces: [core], submitted: false }),
    );
    const sessionApi = createSessionApi("s1", [], fn as unknown as typeof fetch);
    expect(await sessionApi.pieces()).toEqual({ ok: true, data: { pieces: [{ id: "p", position: 0, text: "t", fileCount: 2, createdAt: at }], submitted: false } });
    expect(await sessionApi.addPiece("t", [])).toEqual({ ok: true, data: { id: "p", position: 0, text: "t", fileCount: 2, createdAt: at } });
  });
});
