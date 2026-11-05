// @vitest-environment jsdom
// SESSION-END: "Kết thúc buổi học" hands the session in and opens a pop-up (praise, cards being made,
// "Về trang chủ", "Học tiếp môn này"); the screen has no "Học tự do" button any more.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { renderToStaticMarkup } from "react-dom/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NO_OUTLINE_COPY, NoOutlineBlock } from "@/components/session-study/empty-block";
import { END_COPY } from "@/components/session-study/session-end-dialog";
import { type SessionInitial, SessionScreen } from "@/components/session-study/session-screen";
import type { ApiResult, SessionApi } from "@/lib/session-study/api";
import { readPendingSessions } from "@/lib/session-study/pending";
import { initialRound } from "@/lib/session-study/round";

const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } as const;
const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });

function api(over: Record<string, unknown> = {}) {
  return {
    sessionId: "s1",
    pieces: vi.fn(() => ok({ pieces: [{ id: "p1", position: 0, text: "học TCP", fileCount: 0 }], submitted: false })),
    addPiece: vi.fn(),
    removePiece: vi.fn(),
    complete: vi.fn(() => ok({ status: "queued" })),
    submit: vi.fn(),
    upload: vi.fn(),
    result: vi.fn(),
    ...over,
  };
}

function show(fake: ReturnType<typeof api>, suggestion: typeof FREE | { kind: "section"; text: string; reason: string; pace: string } = FREE) {
  const initial: SessionInitial = { round: { ...initialRound }, text: "", mentions: [], files: [] };
  render(
    <SessionScreen api={fake as unknown as SessionApi} subject="Mạng máy tính" subjectId="SUBJ" stopHref="/today" docs={[]} suggestion={suggestion} nextSuggestion={FREE} initial={initial} />,
  );
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

const end = async () => {
  await screen.findByText("Phần 1");
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
  });
};

describe("session end", () => {
  // Red when: the "Học tự do" button is back in the session screen.
  it("has no Học tự do button and no Hoàn thành button, only Kết thúc buổi học", async () => {
    show(api());
    await screen.findByText("Phần 1");
    expect(screen.queryByRole("button", { name: /Học tự do/ })).toBeNull();
    expect(screen.queryByRole("button", { name: "Hoàn thành" })).toBeNull();
    expect(screen.getByRole("button", { name: "Kết thúc buổi học" })).toBeTruthy();
  });

  // Red when: ending the session shows no pop-up, or one that is not an accessible modal.
  it("opens a labelled modal with the praise, the cards notice and the two buttons", async () => {
    const fake = api();
    show(fake);
    await end();
    expect(fake.complete).toHaveBeenCalledOnce();
    const dialog = await screen.findByRole("dialog");
    expect(dialog.getAttribute("aria-labelledby")).toBeTruthy();
    expect(dialog.textContent).toContain(END_COPY.title);
    expect(dialog.textContent).toContain(END_COPY.recorded(1));
    expect(screen.getByRole("button", { name: END_COPY.home })).toBeTruthy();
    expect(screen.getByRole("button", { name: END_COPY.more })).toBeTruthy();
    // the "đã vào Kho" toast still follows: the session is remembered as pending
    expect(readPendingSessions().map((p) => p.sessionId)).toEqual(["s1"]);
  });

  // Red when: the pop-up appears before the session is in (a refusal must not look like a finish).
  it("shows no pop-up when the session is refused", async () => {
    show(api({ complete: vi.fn(() => Promise.resolve({ ok: false, status: 422, error: "nothing_submitted" })) }));
    await end();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(readPendingSessions()).toEqual([]);
  });

  // Red when: "Về trang chủ" does not go to /today.
  it("Về trang chủ goes to /today", async () => {
    show(api());
    await end();
    fireEvent.click(await screen.findByRole("button", { name: END_COPY.home }));
    expect(assign).toHaveBeenCalledWith("/today");
  });

  // Red when: "Học tiếp môn này" does not start a new session of the same subject (free study).
  it("Học tiếp môn này starts another study session of the subject", async () => {
    show(api());
    await end();
    fireEvent.click(await screen.findByRole("button", { name: END_COPY.more }));
    expect(assign).toHaveBeenCalledWith("/subjects/SUBJ/sessions/study");
  });

  // Red when: Escape leaves the learner on a finished session with no way on.
  it("Escape leaves for /today", async () => {
    show(api());
    await end();
    await screen.findByRole("dialog");
    fireEvent.keyDown(document.activeElement ?? document.body, { key: "Escape" });
    expect(assign).toHaveBeenCalledWith("/today");
  });

  // Red when: focus is not moved into the pop-up (keyboard users stay behind the modal).
  it("moves focus into the pop-up", async () => {
    show(api());
    await end();
    const dialog = await screen.findByRole("dialog");
    expect(dialog.contains(document.activeElement)).toBe(true);
  });

  // Red when: a section session loses its suggestion line (free study still shows the next section).
  it("a free study session on the next section still shows the suggestion", () => {
    show(api(), { kind: "section", text: "Nội dung học tập: 3.2 TCP", reason: "r", pace: "còn 3 chương" });
    expect(screen.getAllByText("Nội dung học tập: 3.2 TCP").length).toBeGreaterThan(0);
  });
});

describe("no outline", () => {
  // Red when: the block has no way on to the textbook upload.
  it("says why and leads to the textbook upload", () => {
    const markup = renderToStaticMarkup(<NoOutlineBlock subjectId="SUBJ" subjectName="Mạng" />);
    expect(markup).toContain(NO_OUTLINE_COPY.title);
    expect(markup).toContain('href="/subjects/SUBJ/documents"');
    expect(markup).not.toContain("sessions/study");
  });
});

describe("session end, typed text and empty session", () => {
  const typeIn = (value: string) => fireEvent.change(screen.getByRole("combobox"), { target: { value } });

  // Red when: words typed but not yet "Ghi lại" are lost by ending the session.
  it("keeps the typed words as one more piece before it ends", async () => {
    const fake = api({ addPiece: vi.fn(() => ok({ id: "p2", position: 1, text: "mới gõ", fileCount: 0 })) });
    show(fake);
    await screen.findByText("Phần 1");
    typeIn("mới gõ");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    });
    expect(fake.addPiece).toHaveBeenCalledOnce();
    expect(fake.addPiece.mock.invocationCallOrder[0]).toBeLessThan(fake.complete.mock.invocationCallOrder[0]);
    expect(await screen.findByRole("dialog")).toBeTruthy();
  });

  // Red when: a refused keep still ends the session (the words would be lost).
  it("does not end when the typed words cannot be kept", async () => {
    const fake = api({ addPiece: vi.fn(() => Promise.resolve({ ok: false, status: 0, error: "network" })) });
    show(fake);
    await screen.findByText("Phần 1");
    typeIn("mới gõ");
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    });
    expect(fake.complete).not.toHaveBeenCalled();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  // Red when: a session with nothing written ends as a success (praise, cards) or loses a button.
  it("an empty session says so and still has both buttons", async () => {
    const fake = api({ pieces: vi.fn(() => ok({ pieces: [], submitted: false })) });
    show(fake);
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    });
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain(END_COPY.emptyTitle);
    expect(dialog.textContent).not.toContain(END_COPY.praise);
    expect(dialog.textContent).not.toContain(END_COPY.title);
    expect(fake.complete).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: END_COPY.home })).toBeTruthy();
    expect(screen.getByRole("button", { name: END_COPY.more })).toBeTruthy();
  });

  // Red when: a press outside the pop-up closes it or leaves the page.
  it("does nothing on a press outside, and the first focus is Về trang chủ", async () => {
    show(api());
    await end();
    const dialog = await screen.findByRole("dialog");
    expect(document.activeElement?.textContent).toBe(END_COPY.home);
    fireEvent.pointerDown(document.body);
    fireEvent.click(document.body);
    expect(screen.getByRole("dialog")).toBe(dialog);
    expect(assign).not.toHaveBeenCalled();
  });
});
