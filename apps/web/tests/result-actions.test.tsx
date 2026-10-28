// @vitest-environment jsdom
// T2.19 (US-09 AC1, AC3, AC4; DESIGN.md §6.5): "Chấm sai" and "Bỏ câu này" on the result screen.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AttemptView, Current, Reply, ReviewApi } from "@/lib/review-client";

vi.mock("@/lib/navigate", () => ({ go: vi.fn() }));

const { ReviewScreen } = await import("@/components/review/review-screen");

const ATTEMPT = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
const GRADE = "a1b2c3d4-5e6f-4a7b-8c9d-0e1f2a3b4c5d";
const QUESTION = "8d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a";

const ok = <T,>(data: T): Reply<T> => ({ ok: true, data });
const fail = (error: string): Reply<never> => ({ ok: false, error });

const current: Current = {
  done: false,
  ungraded: [],
  position: 1,
  total: 3,
  question: {
    id: QUESTION,
    prompt: "Vì sao có ngày và đêm?",
    subject: { id: "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b", name: "Địa lý tự nhiên" },
    unit_ids: ["b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e"],
    reason: { kind: "review", retrievability: 0.7, days_since_last: 6 },
  },
  attempt: { id: ATTEMPT, status: "draft", answer_text: "", dont_remember: false },
};

function view(overall: "partial" | "correct" = "partial"): AttemptView {
  return {
    status: "submitted",
    grading: "graded",
    failure: null,
    result: {
      grade_id: GRADE,
      overall,
      understanding: 1,
      missing: [],
      units: [],
      reference_answer: "Trái Đất tự quay quanh trục.",
      sources: [],
      practice: false,
    },
    answer_text: "Vì Trái Đất tự quay.",
    submitted_at: "2026-10-26T14:42:00Z",
    question: { id: QUESTION, prompt: "Vì sao có ngày và đêm?" },
  };
}

function fakeApi(over: Partial<ReviewApi> = {}): ReviewApi {
  return {
    current: vi.fn(async () => ok(current)),
    open: vi.fn(async () => ok(current.attempt)),
    stop: vi.fn(async () => ok({ answered: 1, total: 3 })),
    saveDraft: vi.fn(async () => ok(null)),
    submit: vi.fn(async () => ok(view())),
    regrade: vi.fn(async () => ok(view())),
    override: vi.fn(async () => ok(view("correct"))),
    drop: vi.fn(async () => ok(null)),
    skip: vi.fn(async () => ok({ session_id: null, next: null })),
    unskip: vi.fn(async () => ok(null)),
    read: vi.fn(async () => ok(view())),
    ...over,
  } as ReviewApi;
}

const press = async (name: string) => {
  await act(async () => fireEvent.click(screen.getByRole("button", { name })));
};

async function graded(api: ReviewApi) {
  await act(async () => {
    render(<ReviewScreen sessionId="5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d" api={api} />);
  });
  fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "Vì Trái Đất tự quay." } });
  await press("Gửi");
  await screen.findByText("Đúng một phần");
}

describe("Chấm sai, Bỏ câu này (T2.19, US-09)", () => {
  beforeEach(() => window.localStorage.clear());
  afterEach(cleanup);

  // Red when: the two quiet buttons are missing, or "Chấm sai" opens a dialog or asks twice.
  it("US-09 AC1: Chấm sai swaps in place for the two choices, no dialog", async () => {
    await graded(fakeApi());
    expect(screen.getByRole("button", { name: "Bỏ câu này" })).toBeTruthy();
    await press("Chấm sai");
    expect(screen.getByRole("button", { name: "Thực ra tôi đúng" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thực ra tôi sai" })).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Câu tiếp" })).toBeTruthy();
  });

  // Red when: the choice misses the current grade, or the verdict line stays as it was.
  it("US-09 AC1, AC3: one choice sends the override and the verdict changes at once", async () => {
    const api = fakeApi();
    await graded(api);
    await press("Chấm sai");
    await press("Thực ra tôi đúng");
    expect(api.override).toHaveBeenCalledWith(GRADE, "correct");
    expect(screen.getByRole("status").textContent).toBe("Đã cập nhật kết quả và lịch ôn.");
    expect(screen.queryByText("Đúng một phần")).toBeNull();
  });

  it("US-09 AC1: a failed override says so and keeps the choices", async () => {
    await graded(fakeApi({ override: vi.fn(async () => fail("unavailable")) as ReviewApi["override"] }));
    await press("Chấm sai");
    await press("Thực ra tôi sai");
    expect(screen.getByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thực ra tôi sai" })).toBeTruthy();
  });

  // Red when: Bỏ câu này asks again, misses the question id, or hides "Câu tiếp".
  it("US-09 AC4: Bỏ câu này is one tap, confirms in a line and keeps Câu tiếp", async () => {
    const api = fakeApi();
    await graded(api);
    await press("Bỏ câu này");
    expect(api.drop).toHaveBeenCalledWith(QUESTION);
    expect(screen.getByRole("status").textContent).toBe("Câu này sẽ không xuất hiện lại.");
    expect(screen.queryByRole("button", { name: "Bỏ câu này" })).toBeNull();
    expect(screen.getByRole("button", { name: "Câu tiếp" })).toBeTruthy();
  });
});
