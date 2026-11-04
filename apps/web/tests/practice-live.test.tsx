// @vitest-environment jsdom
// T8.7 (US-16 AC1-AC3, AC5, AC8; T8.5 review F1): the Luyện tập screen and the practice answer flow
// on web's /api routes (faked here), and a practice step inside the Today review session.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PracticeApi, PracticeView } from "@/lib/practice-client";
import type { QuestionListOut } from "@/lib/question-list-types";
import type { Current, Reply, ReviewApi } from "@/lib/review-client";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { PracticeLive } = await import("@/components/practice/practice-live");
const { PracticeAnswer } = await import("@/components/practice/practice-answer");
const { ReviewScreen } = await import("@/components/review/review-screen");

const SUBJECT = "0b8f1d2e-0000-4000-8000-000000000001";
const Q1 = "0b8f1d2e-0000-4000-8000-0000000000a1";
const Q2 = "0b8f1d2e-0000-4000-8000-0000000000a2";
const ATTEMPT = "0b8f1d2e-0000-4000-8000-0000000000b1";
const GRADE = "0b8f1d2e-0000-4000-8000-0000000000e1";
const SESSION = "0b8f1d2e-0000-4000-8000-0000000000d1";

const ok = <T,>(data: T): Reply<T> => ({ ok: true, data });
// DESIGN §4. Same pattern as practice-screen.test.tsx (Unicode lookarounds: JS \b is ASCII-only).
const FORBIDDEN = /(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|kém|lười|bỏ lỡ|thất bại)(?!\p{L})/iu;

const list: QuestionListOut = {
  total: 3,
  ready: 2,
  due_today: 0,
  types: [],
  questions: [
    { id: Q1, number: 1, prompt: "So sánh TCP và UDP.", origin: "bank", status: "ready", answer_source: "bank", type_name: "So sánh", line: "Sẵn sàng", waiting_sections: [], due: false },
    { id: Q2, number: 2, prompt: "Định nghĩa MSS.", origin: "generated", status: "ready", answer_source: "ai", type_name: "Định nghĩa", line: "Sẵn sàng", waiting_sections: [], due: false },
    { id: "0b8f1d2e-0000-4000-8000-0000000000a3", number: 3, prompt: "Tính thông lượng.", origin: "bank", status: "waiting", answer_source: "bank", type_name: "So sánh", line: "Chờ học: phần 3.4", waiting_sections: [], due: false },
  ],
};
const types = [
  { type_id: "t1", name: "So sánh", mastery: 0.7, attempts_counted: 10, mastery_line: "đúng 7 trên 10 lần gần nhất", sensitivity: "near" as const, sensitivity_line: "gần mốc tham khảo", reference_seconds: 180, ref_origin: "default", formula_version: "v1" },
  { type_id: "t2", name: "Định nghĩa", mastery: null, attempts_counted: 1, mastery_line: "chưa đủ dữ liệu", sensitivity: "not_enough_data" as const, sensitivity_line: "chưa đủ dữ liệu", reference_seconds: 60, ref_origin: "default", formula_version: "v1" },
];

function draftView(over: Partial<PracticeView> = {}): PracticeView {
  return {
    attempt_id: ATTEMPT,
    status: "draft",
    answer_text: "",
    dont_remember: false,
    failure: null,
    grading: null,
    question: { id: Q1, prompt: "So sánh TCP và UDP." },
    result: null,
    submitted_at: null,
    timing_ok: null,
    ...over,
  };
}
const gradedView = (): PracticeView =>
  draftView({
    status: "submitted",
    grading: "graded",
    answer_text: "TCP tin cậy hơn.",
    submitted_at: "2026-11-02T08:00:00Z",
    result: {
      grade_id: GRADE,
      overall: "partial",
      missing: ["Nêu ảnh hưởng tới độ trễ."],
      units: [
        { text: "Nêu độ tin cậy.", met: true },
        { text: "Nêu ảnh hưởng tới độ trễ.", met: false },
      ],
      reference_answer: "TCP tin cậy nhưng thêm độ trễ.",
      answer_origin: "ai",
      differs_from_card_id: null,
    },
  });

function fakeApi(over: Partial<PracticeApi> = {}): PracticeApi {
  return {
    open: vi.fn(async () => ok(draftView())),
    saveDraft: vi.fn(async () => ok(null)),
    submit: vi.fn(async () => ok(gradedView())),
    regrade: vi.fn(async () => ok(gradedView())),
    read: vi.fn(async () => ok(gradedView())),
    remove: vi.fn(async () => ok(null)),
    restore: vi.fn(async () => ok(null)),
    ...over,
  } as PracticeApi;
}

beforeEach(() => {
  go.mockReset();
  window.localStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("PracticeLive (US-16 AC1, AC3, AC8)", () => {
  // Red when: types lose their mastery/sensitivity lines, or "chưa đủ dữ liệu" is replaced by a number.
  it("AC8: each type shows the backend's neutral mastery and time lines", () => {
    render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={fakeApi()} />);
    expect(screen.getByText("đúng 7 trên 10 lần gần nhất")).toBeTruthy();
    expect(screen.getByText("gần mốc tham khảo")).toBeTruthy();
    expect(screen.getAllByText("chưa đủ dữ liệu").length).toBe(2);
  });

  // Red when: more than one primary, the primary is not the first ready row, or the label is lost.
  it("AC1: one primary on the first ready row; ready rows come before waiting ones", () => {
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={fakeApi()} />);
    const primaries = container.querySelectorAll("[data-variant='primary']");
    expect(primaries.length).toBe(1);
    expect(primaries[0].textContent).toBe("Làm câu này");
    expect(container.querySelector(`[data-question="${Q1}"] [data-variant='primary']`)).not.toBeNull();
    // V20: one flat section of unlocked questions, then the waiting ones apart.
    const section = container.querySelector("section[data-practised]") as HTMLElement;
    expect(section.querySelectorAll("[data-question]").length).toBe(2);
    expect(section.querySelector("[data-question='0b8f1d2e-0000-4000-8000-0000000000a3']")).toBeNull();
    expect(screen.getByText("Câu đã luyện tập")).toBeTruthy();
    expect(screen.getByText("Đã mở khóa 2/3 câu")).toBeTruthy();
  });

  // Red when: removing needs a dialog, or the row does not turn into the one-line note.
  it("AC3: 'Gỡ khỏi luyện tập' is one tap and calls the practice remove", async () => {
    const api = fakeApi();
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={api} />);
    await act(async () => fireEvent.click(within(container.querySelector(`[data-question="${Q2}"]`) as HTMLElement).getByRole("button", { name: "Gỡ khỏi luyện tập" })));
    expect(api.remove).toHaveBeenCalledWith(Q2);
    expect(container.querySelector(`[data-removed="${Q2}"]`)?.textContent).toContain("Đã gỡ khỏi luyện tập.");
    expect(document.activeElement?.getAttribute("data-focus")).toBe(`removed-${Q2}`);
  });

  // Red when: Hoàn tác does not call restore, or the row does not come back with focus on its button.
  it("T8.7b: 'Hoàn tác' restores the question and brings the row back", async () => {
    const api = fakeApi();
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={api} />);
    await act(async () => fireEvent.click(within(container.querySelector(`[data-question="${Q1}"]`) as HTMLElement).getByRole("button", { name: "Gỡ khỏi luyện tập" })));
    await act(async () => fireEvent.click(within(container.querySelector(`[data-removed="${Q1}"]`) as HTMLElement).getByRole("button", { name: "Hoàn tác" })));
    expect(api.restore).toHaveBeenCalledWith(Q1);
    expect(container.querySelector(`[data-question="${Q1}"]`)).not.toBeNull();
    expect(container.querySelector(`[data-removed="${Q1}"]`)).toBeNull();
  });

  it("T8.7b: a failed undo keeps the row removed and says so calmly", async () => {
    const api = fakeApi({ restore: vi.fn(async () => ({ ok: false as const, error: "unavailable" })) });
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={api} />);
    await act(async () => fireEvent.click(within(container.querySelector(`[data-question="${Q2}"]`) as HTMLElement).getByRole("button", { name: "Gỡ khỏi luyện tập" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Hoàn tác" })));
    expect(container.querySelector(`[data-removed="${Q2}"]`)).not.toBeNull();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("AC3: a failed removal keeps the row and says so calmly", async () => {
    const api = fakeApi({ remove: vi.fn(async () => ({ ok: false as const, error: "unavailable" })) });
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={api} />);
    await act(async () => fireEvent.click(within(container.querySelector(`[data-question="${Q2}"]`) as HTMLElement).getByRole("button", { name: "Gỡ khỏi luyện tập" })));
    expect(container.querySelector(`[data-question="${Q2}"]`)).not.toBeNull();
    expect(screen.getByRole("alert").textContent).toContain("Chưa gỡ được");
  });

  it("an empty bank offers the upload and no list", () => {
    const { container } = render(
      <PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={{ total: 0, ready: 0, due_today: 0, types: [], questions: [] }} types={[]} api={fakeApi()} />,
    );
    expect(container.querySelector("[data-empty]")).not.toBeNull();
    expect(container.querySelectorAll("[data-variant='primary']").length).toBe(1);
  });

  // Red when: app copy (not the user's text) uses a banned word or shows a clock.
  it("no banned word and no clock in what the screen writes", () => {
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={fakeApi()} />);
    const clone = container.cloneNode(true) as HTMLElement;
    clone.querySelectorAll("[data-user]").forEach((el) => el.remove());
    expect(clone.textContent).not.toMatch(FORBIDDEN);
    expect(container.querySelector("time")).toBeNull();
  });

  // Red when: doing a question does not open the answer flow, or "Câu tiếp" does not reload the list.
  it("AC2: 'Làm câu này' opens the question; 'Câu tiếp' returns to the list read afresh", async () => {
    const api = fakeApi();
    render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={api} listPath="/back" />);
    await act(async () => fireEvent.click(screen.getAllByRole("button", { name: "Làm câu này" })[0]));
    await waitFor(() => expect(screen.getByLabelText("Câu trả lời của bạn")).toBeTruthy());
    expect(api.open).toHaveBeenCalledWith(Q1);
    fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "TCP tin cậy hơn." } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Câu tiếp" })));
    expect(go).toHaveBeenCalledWith("/back");
  });
});

describe("PracticeAnswer (US-16 AC2, AC5)", () => {
  async function answer(api: PracticeApi) {
    await act(async () => {
      render(<PracticeAnswer questionId={Q1} api={api} onNext={() => undefined} />);
    });
    fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "TCP tin cậy hơn." } });
  }

  // Red when: the hidden time is not sent, or it is sent as something other than whole milliseconds.
  it("AC5: sends the time the tab was hidden as hidden_ms", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(1_000_000);
    const api = fakeApi();
    await act(async () => {
      render(<PracticeAnswer questionId={Q1} api={api} onNext={() => undefined} />);
    });
    fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "TCP tin cậy hơn." } });
    const hidden = (value: boolean) => {
      Object.defineProperty(document, "hidden", { configurable: true, get: () => value });
      document.dispatchEvent(new Event("visibilitychange"));
    };
    hidden(true);
    vi.setSystemTime(1_004_500);
    hidden(false);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    expect(api.submit).toHaveBeenCalledWith(ATTEMPT, { answer_text: "TCP tin cậy hơn.", dont_remember: false, hidden_ms: 4500 });
  });

  it("AC5: a visible tab sends 0", async () => {
    const api = fakeApi();
    await answer(api);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    expect(api.submit).toHaveBeenCalledWith(ATTEMPT, { answer_text: "TCP tin cậy hơn.", dont_remember: false, hidden_ms: 0 });
  });

  // Red when: a rubric point or the reference answer is missing, the AI answer is not labelled, or
  // the result shows a score, a clock or a banned word.
  it("AC2: the result shows the missing rubric points, the reference, the AI label and no clock", async () => {
    const api = fakeApi();
    await answer(api);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    expect((await screen.findAllByText("Nêu ảnh hưởng tới độ trễ.")).length).toBeGreaterThan(0);
    expect(screen.getByText("TCP tin cậy nhưng thêm độ trễ.")).toBeTruthy();
    expect(screen.getByText("đáp án do AI soạn")).toBeTruthy();
    const own = document.querySelector("[data-practice-extras]") as HTMLElement;
    expect(own.textContent).not.toMatch(FORBIDDEN);
    expect(document.querySelector("time")).toBeNull();
    expect(document.querySelectorAll("[data-variant='primary']").length).toBe(1);
  });

  // Red when: a rubric point is not listed, or a met point is not told apart from a missed one.
  it("T8.7b: the result lists every rubric point with Đúng or Thiếu, in an accessible list", async () => {
    const api = fakeApi();
    await answer(api);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    const list = await screen.findByRole("list", { name: "theo từng ý" });
    const items = within(list).getAllByRole("listitem").map((li) => li.textContent);
    expect(items).toEqual(["Nêu độ tin cậy.Đúng", "Nêu ảnh hưởng tới độ trễ.Thiếu"]);
  });

  it("T8.7b: Hoàn tác on the result calls restore and offers 'Gỡ khỏi luyện tập' again", async () => {
    const api = fakeApi();
    await answer(api);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Gỡ khỏi luyện tập" })));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Hoàn tác" })));
    expect(api.restore).toHaveBeenCalledWith(Q1);
    expect(screen.getByRole("button", { name: "Gỡ khỏi luyện tập" })).toBeTruthy();
  });

  it("AC3: the result offers 'Gỡ khỏi luyện tập' in one tap", async () => {
    const api = fakeApi();
    await answer(api);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Gỡ khỏi luyện tập" })));
    expect(api.remove).toHaveBeenCalledWith(Q1);
    expect(screen.getByText("Đã gỡ khỏi luyện tập.")).toBeTruthy();
  });

  // Red when: a failed send loses the text or hides it behind the result.
  it("a failed send keeps the answer and says so without an error word", async () => {
    const api = fakeApi({ submit: vi.fn(async () => ({ ok: false as const, error: "offline" })) });
    await answer(api);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    expect((screen.getByLabelText("Câu trả lời của bạn") as HTMLTextAreaElement).value).toBe("TCP tin cậy hơn.");
    expect(screen.getByRole("alert").textContent).toContain("Chưa gửi được");
  });

  it("a grading that failed offers 'Chấm lại' and never blocks 'Câu tiếp'", async () => {
    const failed = draftView({ status: "submitted", grading: "failed", failure: "unavailable", answer_text: "x" });
    const api = fakeApi({ submit: vi.fn(async () => ok(failed)) });
    await answer(api);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    expect(await screen.findByRole("button", { name: "Chấm lại" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Câu tiếp" })).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Chấm lại" })));
    expect(api.regrade).toHaveBeenCalledWith(ATTEMPT);
    expect((await screen.findAllByText("Nêu ảnh hưởng tới độ trễ.")).length).toBeGreaterThan(0);
  });

  it("an already submitted attempt opens on its result, not on an empty box", async () => {
    const api = fakeApi({ open: vi.fn(async () => ok(gradedView())) });
    await act(async () => {
      render(<PracticeAnswer questionId={Q1} api={api} onNext={() => undefined} />);
    });
    expect(screen.queryByLabelText("Câu trả lời của bạn")).toBeNull();
    expect(await screen.findByText("TCP tin cậy hơn.")).toBeTruthy();
  });
});

describe("a practice step in the Today review session (T8.5 review F1)", () => {
  const practiceStep = (over: Partial<Current["question"]> = {}): Current => ({
    done: false,
    ungraded: [],
    position: 2,
    total: 3,
    question: {
      id: Q1,
      kind: "practice",
      prompt: "So sánh TCP và UDP.",
      subject: { id: SUBJECT, name: "Mạng" },
      unit_ids: [],
      reason: { kind: "review", retrievability: 0.7, days_since_last: 6 },
      ...over,
    },
    attempt: null,
  });

  // Red when: the screen asks core-api for a card attempt on a practice question (a 409 dead end).
  it("answers it through /v1/practice, never opens a card attempt, and 'Câu tiếp' loads the next step", async () => {
    const current = vi.fn(async () => ok(practiceStep()));
    const review = { current, open: vi.fn(), stop: vi.fn() } as unknown as ReviewApi;
    const practice = fakeApi();
    await act(async () => {
      render(<ReviewScreen sessionId={SESSION} api={review} practice={practice} />);
    });
    expect(await screen.findByLabelText("Câu trả lời của bạn")).toBeTruthy();
    expect(practice.open).toHaveBeenCalledWith(Q1);
    expect(review.open).not.toHaveBeenCalled();
    expect(screen.getByText("Câu 2 / 3")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "TCP tin cậy hơn." } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Câu tiếp" })));
    expect(current).toHaveBeenCalledTimes(2);
  });
});

// V20: a due question gives the screen one primary, "Vào luyện tập ngay", and the count of today.
describe("PracticeLive due today (V20)", () => {
  it("shows the due count and a button that opens the first due question", () => {
    const due = {
      ...list,
      due_today: 1,
      questions: list.questions.map((q, i) => ({ ...q, due: i === 0 && q.status === "ready", unlocked_at: "2026-11-02T00:00:00Z" })),
    };
    render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={due} types={types} api={fakeApi()} />);
    expect(screen.getByText("Hôm nay cần luyện 1 câu.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Vào luyện tập ngay" })).toBeTruthy();
  });
});

// V22 g2: the chip shows a readable kind name, never a raw key.
describe("kindChip", () => {
  it("keeps a readable name and hides a spaceless key", async () => {
    const { kindChip } = await import("@/components/practice/practice-live");
    expect(kindChip("So sánh")).toBe("So sánh");
    expect(kindChip("Định nghĩa ngắn")).toBe("Định nghĩa ngắn");
    expect(kindChip("so_sanh_hai_giao_thuc_van_chuyen_nang_cao_tinh_toan")).toBeNull();
    expect(kindChip("  ")).toBeNull();
  });
});

describe("practice row labels and suggestion (V22 g2)", () => {
  // Red when: the origin label, the section line or the unlock date is dropped, or the suggestion is not on the first ready row.
  it("shows Câu sinh thêm, the line and the suggested row", () => {
    const { container } = render(<PracticeLive subjectId={SUBJECT} subjectName="Mạng" list={list} types={types} api={fakeApi()} />);
    expect(container.textContent).toContain("Câu sinh thêm");
    expect(container.textContent).toContain("Câu gốc");
    expect(container.textContent).toContain("Sẵn sàng");
    const why = container.querySelectorAll("[data-why]");
    expect(why.length).toBe(1);
    expect(why[0].closest(`[data-question="${Q1}"]`)).not.toBeNull();
  });
});
