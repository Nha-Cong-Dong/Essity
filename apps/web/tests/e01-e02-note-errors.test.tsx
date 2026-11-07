// @vitest-environment jsdom
// PREDEPLOY-FIX-A E-01 (expired cookie on a note is a sign-in, not "mạng chập chờn") and E-02
// (note over 2000 chars: maxLength, counter, "dài quá" for core-api's validation error).
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { completeProblem, noteProblem, type SessionInitial, SessionScreen, SUBMIT_COPY } from "@/components/session-study/session-screen";
import { NOTE_MAX } from "@/components/session-study/session-mention-box";
import { go } from "@/lib/navigate";
import type { ApiResult, SessionApi } from "@/lib/session-study/api";
import { initialRound } from "@/lib/session-study/round";

vi.mock("@/lib/navigate", () => ({ go: vi.fn() }));

const FREE = { kind: "free", text: "Buổi học tự do." } as const;
const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });
const fail = (status: number, error: string): Promise<ApiResult<never>> => Promise.resolve({ ok: false, status, error });

function show(over: Record<string, unknown>, text = "") {
  const fake = {
    sessionId: "s1",
    pieces: vi.fn(() => ok({ pieces: [], submitted: false })),
    addPiece: vi.fn(),
    removePiece: vi.fn(() => ok(null)),
    complete: vi.fn(),
    submit: vi.fn(),
    upload: vi.fn(),
    result: vi.fn(),
    ...over,
  };
  const initial: SessionInitial = { round: { ...initialRound }, text, mentions: [], files: [] };
  render(<SessionScreen api={fake as unknown as SessionApi} subject="Mạng" subjectId="SUBJ" stopHref="/today" docs={[]} suggestion={FREE} nextSuggestion={FREE} initial={initial} />);
  return fake;
}

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
  vi.mocked(go).mockClear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("E-01 signed-out note", () => {
  it("maps 401 to the expired copy, never to the network copy", () => {
    expect(noteProblem(401, "signed_out")).toBe(SUBMIT_COPY.expired);
    expect(completeProblem(401, "signed_out")).toBe(SUBMIT_COPY.expired);
    expect(noteProblem(0, "network")).toBe(SUBMIT_COPY.network);
  });

  it("E-01 Ghi lại with an expired cookie says so and goes to /login", async () => {
    const fake = show({ addPiece: vi.fn(() => fail(401, "signed_out")) }, "ghi chú");
    await act(async () => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Ghi lại" }));
    await act(async () => undefined);
    expect(fake.addPiece).toHaveBeenCalled();
    expect(screen.getAllByText(SUBMIT_COPY.expired).length).toBeGreaterThan(0);
    expect(screen.queryByText(SUBMIT_COPY.network)).toBeNull();
    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(go).toHaveBeenCalledWith("/login");
  });
});

describe("E-02 long note", () => {
  it("E-02 maps core-api validation (400/422) to tooLong, not network", () => {
    expect(noteProblem(400, "unavailable")).toBe(SUBMIT_COPY.tooLong);
    expect(noteProblem(422, "invalid_request")).toBe(SUBMIT_COPY.tooLong);
    expect(noteProblem(503, "unavailable")).toBe(SUBMIT_COPY.network);
  });

  it("E-02 the field has maxLength and a counter near the limit", async () => {
    show({}, "x".repeat(1850));
    await act(async () => undefined);
    const field = screen.getByRole("combobox");
    expect(field.getAttribute("maxlength")).toBe(String(NOTE_MAX));
    expect(screen.getByTestId("note-counter").textContent).toContain("1850/2000");
  });

  it("E-02 no counter for a short note", async () => {
    show({}, "ngắn");
    await act(async () => undefined);
    expect(screen.queryByTestId("note-counter")).toBeNull();
  });

  it("E-02 a 400 on Ghi lại shows the too-long copy", async () => {
    show({ addPiece: vi.fn(() => fail(400, "unavailable")) }, "ghi chú");
    await act(async () => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Ghi lại" }));
    await act(async () => undefined);
    expect(screen.getAllByText(SUBMIT_COPY.tooLong).length).toBeGreaterThan(0);
  });
});
