// @vitest-environment jsdom
// T2.24 (US-04 AC5; DESIGN.md §2): "Không cần ôn phần này" on the answer screen, one tap, with
// "Hoàn tác" at once (no dialog), then the replacement question or the end of the session.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Current, Done, Reply, ReviewApi } from "@/lib/review-client";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { ReviewScreen } = await import("@/components/review/review-screen");

const SESSION = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const UNIT_A = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const UNIT_B = "c3d4e5f6-7a8b-4c9d-8e1f-2a3b4c5d6e7f";

const ok = <T,>(data: T): Reply<T> => ({ ok: true, data });

function step(prompt: string, unit_ids: string[], attemptId: string): Current {
  return {
    done: false,
    ungraded: [],
    position: 1,
    total: 3,
    question: {
      id: "8d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
      prompt,
      subject: { id: "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b", name: "Địa lý" },
      unit_ids,
    },
    attempt: { id: attemptId, status: "draft", answer_text: "", dont_remember: false },
  };
}

const FIRST = step("Vì sao có ngày và đêm?", [UNIT_A], "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e");
const SECOND = step("Vì sao có mùa?", [UNIT_B], "7c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f");
const DONE: Done = { done: true, ungraded: [] };

function fakeApi(over: Partial<ReviewApi> = {}): ReviewApi {
  return {
    current: vi.fn(async () => ok(FIRST)),
    open: vi.fn(async () => ok(FIRST.attempt)),
    stop: vi.fn(async () => ok({ answered: 0, total: 3 })),
    saveDraft: vi.fn(async () => ok(null)),
    submit: vi.fn(),
    regrade: vi.fn(),
    override: vi.fn(),
    drop: vi.fn(),
    skip: vi.fn(async () => ok({ session_id: SESSION, next: SECOND })),
    unskip: vi.fn(async () => ok(null)),
    read: vi.fn(),
    ...over,
  } as ReviewApi;
}

async function show(api: ReviewApi) {
  await act(async () => {
    render(<ReviewScreen sessionId={SESSION} api={api} />);
  });
  return api;
}
const press = async (name: string) => {
  await act(async () => fireEvent.click(screen.getByRole("button", { name })));
};

describe("Không cần ôn phần này (T2.24, US-04 AC5)", () => {
  beforeEach(() => {
    go.mockReset();
    window.localStorage.clear();
  });
  afterEach(cleanup);

  // Red when: the button is missing, or it asks before skipping, or the session is not named.
  it("US-04 AC5: one tap skips the unit of the question in this session, no dialog", async () => {
    const api = await show(fakeApi({ current: vi.fn().mockResolvedValueOnce(ok(FIRST)).mockResolvedValue(ok(SECOND)) }));
    await press("Không cần ôn phần này");
    expect(api.skip).toHaveBeenCalledWith(UNIT_A, SESSION);
    expect(screen.queryByRole("dialog")).toBeNull();
    // the replacement question is on screen, with the undo line
    expect(screen.getByText("Vì sao có mùa?")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Đã bỏ qua phần này.");
    expect(screen.getByRole("button", { name: "Hoàn tác" })).toBeTruthy();
  });

  // Red when: "Hoàn tác" does not send the undo for the same unit, or the line stays.
  it("US-04 AC5: Hoàn tác undoes the skip at once and the line goes", async () => {
    const api = await show(
      fakeApi({ current: vi.fn().mockResolvedValueOnce(ok(FIRST)).mockResolvedValueOnce(ok(SECOND)).mockResolvedValue(ok(FIRST)) }),
    );
    await press("Không cần ôn phần này");
    await press("Hoàn tác");
    expect(api.unskip).toHaveBeenCalledWith(UNIT_A, SESSION);
    expect(screen.queryByRole("button", { name: "Hoàn tác" })).toBeNull();
    expect(screen.getByText("Vì sao có ngày và đêm?")).toBeTruthy();
  });

  // Red when: a question with several units skips only one of them.
  it("US-04 AC5: a question of several units skips every unit and undoes every unit", async () => {
    const two = step("Hai ý?", [UNIT_A, UNIT_B], "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e");
    const api = await show(fakeApi({ current: vi.fn().mockResolvedValueOnce(ok(two)).mockResolvedValue(ok(SECOND)) }));
    await press("Không cần ôn phần này");
    expect(api.skip).toHaveBeenNthCalledWith(1, UNIT_A, SESSION);
    expect(api.skip).toHaveBeenNthCalledWith(2, UNIT_B, SESSION);
    await press("Hoàn tác");
    expect(api.unskip).toHaveBeenCalledTimes(2);
  });

  // Red when: nothing is left after the skip and the user is stranded instead of leaving.
  it("US-04 AC5: no question left closes the session and goes to Hôm nay", async () => {
    const api = await show(fakeApi({ current: vi.fn().mockResolvedValueOnce(ok(FIRST)).mockResolvedValue(ok(DONE)) }));
    await press("Không cần ôn phần này");
    expect(api.stop).toHaveBeenCalledWith(SESSION);
    expect(go).toHaveBeenCalledWith("/today");
  });

  it("US-04 AC5: a failed skip says so, keeps the question and the button", async () => {
    const api = await show(fakeApi({ skip: vi.fn(async () => ({ ok: false as const, error: "unavailable" })) as ReviewApi["skip"] }));
    await press("Không cần ôn phần này");
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByText("Vì sao có ngày và đêm?")).toBeTruthy();
    expect(api.skip).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Không cần ôn phần này" })).toBeTruthy();
  });
});
