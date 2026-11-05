// @vitest-environment jsdom
// Q4b (QA, CARDS-V3): a session whose "Hoàn thành" is refused tells why (not "mạng chập chờn" for
// everything) and lets the learner drop the piece that blocks it.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { completeProblem, type SessionInitial, SessionScreen, SUBMIT_COPY } from "@/components/session-study/session-screen";
import type { ApiResult, SessionApi } from "@/lib/session-study/api";
import { initialRound } from "@/lib/session-study/round";

const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } as const;
const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });
const fail = (status: number, error: string): Promise<ApiResult<never>> => Promise.resolve({ ok: false, status, error });

function api(over: Record<string, unknown> = {}) {
  return {
    sessionId: "s1",
    pieces: vi.fn(() => ok({ pieces: [{ id: "p1", position: 0, text: "học @Giao trinh", fileCount: 0 }], submitted: false })),
    addPiece: vi.fn(),
    removePiece: vi.fn(() => ok(null)),
    complete: vi.fn(() => fail(422, "mention_not_found")),
    submit: vi.fn(),
    upload: vi.fn(),
    result: vi.fn(),
    ...over,
  };
}

function show(fake: ReturnType<typeof api>) {
  const initial: SessionInitial = { round: { ...initialRound }, text: "", mentions: [], files: [] };
  render(
    <SessionScreen
      api={fake as unknown as SessionApi}
      subject="Mạng máy tính"
      subjectId="SUBJ"
      stopHref="/today"
      docs={[{ id: DOC, name: "Giáo trình", role: "Giáo trình chính" }]}
      suggestion={FREE}
      nextSuggestion={FREE}
      initial={initial}
    />,
  );
}

beforeEach(() => {
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(cleanup);

describe("completeProblem", () => {
  // Red when: every refusal is blamed on the network again.
  it("blames the network only for a dropped connection", () => {
    expect(completeProblem(0, "network")).toBe(SUBMIT_COPY.network);
    expect(completeProblem(422, "mention_not_found")).toBe(SUBMIT_COPY.mentionPiece);
    expect(completeProblem(422, "scope_not_found")).toBe(SUBMIT_COPY.mentionPiece);
    expect(completeProblem(422, "nothing_submitted")).toBe(SUBMIT_COPY.nothing);
    expect(completeProblem(409, "session_confirmed")).toBe(SUBMIT_COPY.closed);
    expect(completeProblem(503, "unavailable")).toBe(SUBMIT_COPY.other);
  });
});

describe("pieces of a session", () => {
  it("says why Hoàn thành was refused and keeps the piece", async () => {
    const fake = api();
    show(fake);
    await act(async () => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    await act(async () => undefined);
    expect(screen.getAllByText(SUBMIT_COPY.mentionPiece).length).toBeGreaterThan(0);
    expect(screen.queryByText(SUBMIT_COPY.network)).toBeNull();
    expect(screen.getByText("học @Giao trinh")).toBeTruthy();
  });

  it("drops a piece with its own button and clears the message", async () => {
    const fake = api();
    show(fake);
    await act(async () => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Kết thúc buổi học" }));
    await act(async () => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Bỏ phần 1" }));
    await act(async () => undefined);
    expect(fake.removePiece).toHaveBeenCalledWith("p1");
    expect(screen.queryByText("học @Giao trinh")).toBeNull();
    expect(screen.queryByText(SUBMIT_COPY.mentionPiece)).toBeNull();
  });
});
