// @vitest-environment jsdom
// T4.18 (US-02 AC11): the polling of a saved session's state, with the route faked.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionProgress } from "@/components/session-progress";
import { FIRST_DELAY_MS, MAX_DELAY_MS, nextDelay, progressLine } from "@/lib/session-progress";

const ID = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const state = (over: object) => ({
  session_id: ID,
  state: "processing",
  step: null,
  percent: null,
  reason: null,
  ...over,
});
const answer = (body: object, status = 200) => Response.json(body, { status });

const fetchMock = vi.fn<(url: string) => Promise<Response>>();

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("fetch", (url: string) => fetchMock(url));
});
afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

const tick = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

describe("nextDelay", () => {
  it("grows from 2 s and stops at 15 s", () => {
    expect([0, 1, 2].map(nextDelay)).toEqual([FIRST_DELAY_MS, 3000, 4500]);
    expect(nextDelay(50)).toBe(MAX_DELAY_MS);
  });
});

describe("progressLine", () => {
  it("has a sentence for every state, step and reason", () => {
    const steps = ["reading_notes", "splitting_units", "anchoring", "writing_questions"] as const;
    const lines = steps.map((step) => progressLine(state({ step }) as never));
    expect(new Set(lines).size).toBe(4);
    expect(progressLine(state({ state: "waiting" }) as never)).toMatch(/chờ/);
    expect(progressLine(state({ state: "done" }) as never)).toMatch(/Đã soạn xong/);
    for (const reason of ["unreadable", "llm_unavailable", "internal_error"])
      expect(progressLine(state({ state: "failed", reason }) as never)).toMatch(/Chưa/);
  });
});

describe("SessionProgress", () => {
  it("shows the step, polls with backoff, and stops once done", async () => {
    fetchMock
      .mockResolvedValueOnce(answer(state({ state: "waiting" })))
      .mockResolvedValueOnce(answer(state({ step: "anchoring", percent: 60 })))
      .mockResolvedValue(answer(state({ state: "done", percent: 100 })));
    const onDone = vi.fn();
    render(<SessionProgress sessionId={ID} onDone={onDone} />);
    await tick(0);
    expect(screen.getByText(/chờ/)).toBeTruthy();
    await tick(2000);
    expect(screen.getByText("Đang đối chiếu với trang tài liệu")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-valuenow")).toBe("60");
    await tick(2999);
    expect(fetchMock).toHaveBeenCalledTimes(2); // the second wait is 3 s
    await tick(1);
    expect(screen.getByText(/Đã soạn xong/)).toBeTruthy();
    expect(onDone).toHaveBeenCalledTimes(1);
    await tick(60_000);
    expect(fetchMock).toHaveBeenCalledTimes(3); // no read after the end state
    expect(fetchMock).toHaveBeenCalledWith(`/api/sessions/${ID}/progress`);
  });

  it("stops at failed and says why", async () => {
    fetchMock.mockResolvedValue(answer(state({ state: "failed", reason: "unreadable" })));
    render(<SessionProgress sessionId={ID} />);
    await tick(0);
    expect(screen.getByText(/Chưa đọc được/)).toBeTruthy();
    await tick(60_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows the server's state when opened again, not a fresh start", async () => {
    fetchMock.mockResolvedValue(answer(state({ state: "done", percent: 100 })));
    render(<SessionProgress sessionId={ID} />);
    await tick(0);
    expect(screen.getByText(/Đã soạn xong/)).toBeTruthy();
  });

  it("keeps trying after a failed read and gives up with a sentence after five", async () => {
    fetchMock
      .mockRejectedValueOnce(new TypeError("net"))
      .mockResolvedValueOnce(answer(state({ step: "reading_notes", percent: 5 })));
    render(<SessionProgress sessionId={ID} />);
    await tick(0);
    await tick(2000);
    expect(screen.getByText("Đang đọc ghi chú của bạn")).toBeTruthy();
    cleanup();
    fetchMock.mockReset();
    fetchMock.mockRejectedValue(new TypeError("net"));
    render(<SessionProgress sessionId={ID} />);
    await tick(60_000);
    expect(screen.getByText(/Chưa xem được/)).toBeTruthy();
  });

  it("stops on 404, goes to login on 401, and unmounting stops the reads", async () => {
    fetchMock.mockResolvedValue(answer({ error: "session_not_found" }, 404));
    render(<SessionProgress sessionId={ID} />);
    await tick(60_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Chưa xem được/)).toBeTruthy();
    cleanup();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(answer({ error: "signed_out" }, 401));
    const onSignedOut = vi.fn();
    render(<SessionProgress sessionId={ID} onSignedOut={onSignedOut} />);
    await tick(0);
    expect(onSignedOut).toHaveBeenCalledTimes(1);
    cleanup();
    fetchMock.mockReset();
    fetchMock.mockResolvedValue(answer(state({ step: "anchoring", percent: 10 })));
    const view = render(<SessionProgress sessionId={ID} />);
    await tick(0);
    view.unmount();
    await tick(60_000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it.each([403, 500, 503])("stops polling after five reads that answer %i", async (status) => {
    fetchMock.mockImplementation(async () => answer({ error: "x" }, status));
    render(<SessionProgress sessionId={ID} />);
    await tick(120_000);
    expect(fetchMock).toHaveBeenCalledTimes(5);
    expect(screen.getByText(/Chưa xem được/)).toBeTruthy();
  });
});
