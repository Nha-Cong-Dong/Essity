// @vitest-environment jsdom
// T2.15, T2.13 (US-04, US-05, US-08; plan t2.15-t2.13-t2.16-answer-grade.md D-7, D-8, 🟡14):
// the answer screen at /review/[id]. One question at a time, the draft kept here and in core-api,
// submitting grades at once; a failed grading keeps the answer and offers "Chấm lại".
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AttemptView, Current, Reply, ReviewApi } from "@/lib/review-client";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { ReviewScreen } = await import("@/components/review/review-screen");
const { readDraft, writeDraft } = await import("@/lib/draft");

const SESSION = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const ATTEMPT = "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e";
const NEXT_ATTEMPT = "7c2d3e4f-5a6b-4c7d-8e9f-0a1b2c3d4e5f";

const ok = <T,>(data: T): Reply<T> => ({ ok: true, data });
const fail = (error: string): Reply<never> => ({ ok: false, error });

function current(over: Partial<Current> = {}): Current {
  return {
    done: false,
    ungraded: [],
    position: 1,
    total: 3,
    question: {
      id: "8d3e4f5a-6b7c-4d8e-9f0a-1b2c3d4e5f6a",
      prompt: "Vì sao có ngày và đêm?",
      subject: { id: "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b", name: "Địa lý tự nhiên" },
      unit_ids: [],
    },
    attempt: { id: ATTEMPT, status: "draft", answer_text: "", dont_remember: false },
    ...over,
  };
}

function view(over: Partial<AttemptView> = {}): AttemptView {
  return {
    status: "submitted",
    grading: "graded",
    failure: null,
    result: {
      grade_id: "0b8f1d2e-0000-4000-8000-0000000000e1",
      overall: "partial",
      understanding: 1,
      missing: ["Mặt Trời chỉ chiếu sáng một nửa Trái Đất."],
      units: [],
      reference_answer: "Trái Đất tự quay quanh trục.",
      sources: [],
      practice: false,
    },
    answer_text: "Vì Trái Đất tự quay.",
    submitted_at: "2026-10-26T14:42:00Z",
    question: { id: "0b8f1d2e-0000-4000-8000-0000000000b1", prompt: "Vì sao có ngày và đêm?" },
    ...over,
  };
}

function fakeApi(over: Partial<ReviewApi> = {}): ReviewApi {
  return {
    current: vi.fn(async () => ok(current())),
    open: vi.fn(async () => ok({ id: ATTEMPT, status: "draft", answer_text: "", dont_remember: false })),
    stop: vi.fn(async () => ok({ answered: 1, total: 3 })),
    saveDraft: vi.fn(async () => ok(null)),
    submit: vi.fn(async () => ok(view())),
    regrade: vi.fn(async () => ok(view())),
    read: vi.fn(async () => ok(view())),
    ...over,
  } as ReviewApi;
}

async function show(api: ReviewApi) {
  await act(async () => {
    render(<ReviewScreen sessionId={SESSION} api={api} />);
  });
  return api;
}

const field = () => screen.getByLabelText("Câu trả lời của bạn") as HTMLTextAreaElement;
const type = (text: string) => fireEvent.change(field(), { target: { value: text } });
const press = async (name: string | RegExp) => {
  await act(async () => fireEvent.click(screen.getByRole("button", { name })));
};

describe("ReviewScreen (T2.15)", () => {
  beforeEach(() => {
    go.mockReset();
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  // US-04 AC1. Red when: the screen shows more than the current question, or no progress.
  it("US-04 AC1: shows the current question, its subject and where the session is", async () => {
    await show(fakeApi());
    expect(screen.getByRole("heading", { name: "Vì sao có ngày và đêm?" })).toBeTruthy();
    expect(screen.getByText("Địa lý tự nhiên")).toBeTruthy();
    expect(screen.getByText("Câu 1 / 3")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Gửi" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Không nhớ" })).toBeTruthy();
  });

  it("opens the draft when the question has none yet", async () => {
    const api = await show(fakeApi({ current: vi.fn(async () => ok(current({ attempt: null }))) }));
    expect(api.open).toHaveBeenCalledWith(SESSION);
    expect(field()).toBeTruthy();
  });

  // Plan 🟡14. Red when: text this device never got to core-api is replaced by core-api's older draft.
  it("US-04 AC3: text kept on this device that core-api never got wins, and is sent", async () => {
    writeDraft(ATTEMPT, { text: "gõ lúc mất mạng", dontRemember: false, synced: false, base: "cũ" });
    const api = await show(
      fakeApi({
        current: vi.fn(async () =>
          ok(current({ attempt: { id: ATTEMPT, status: "draft", answer_text: "cũ", dont_remember: false } })),
        ),
      }),
    );
    expect(field().value).toBe("gõ lúc mất mạng");
    await waitFor(() =>
      expect(api.saveDraft).toHaveBeenCalledWith(ATTEMPT, { answer_text: "gõ lúc mất mạng", dont_remember: false }),
    );
  });

  it("core-api's draft is shown when this device has nothing newer", async () => {
    writeDraft(ATTEMPT, { text: "đã đồng bộ", dontRemember: false, synced: true, base: "đã đồng bộ" });
    await show(
      fakeApi({
        current: vi.fn(async () =>
          ok(current({ attempt: { id: ATTEMPT, status: "draft", answer_text: "từ máy khác", dont_remember: false } })),
        ),
      }),
    );
    expect(field().value).toBe("từ máy khác");
  });

  // US-04 AC3, PLAN T2.15 (debounce ~1.5 s). Red when: a keystroke is not kept on this device at
  // once, or core-api gets a save per keystroke.
  it("US-04 AC3: typing is kept here at once and saved to core-api after a pause", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = await show(fakeApi());
    type("T");
    type("TCP");
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "TCP", synced: false });
    expect(api.saveDraft).not.toHaveBeenCalled();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(api.saveDraft).toHaveBeenCalledOnce();
    expect(api.saveDraft).toHaveBeenCalledWith(ATTEMPT, { answer_text: "TCP", dont_remember: false });
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "TCP", synced: true });
    expect(screen.getByText(/^Đã lưu nháp lúc \d\d:\d\d$/)).toBeTruthy();
  });

  // US-04 AC3. Red when: a dropped connection shows an error, or the draft is never sent later.
  it("US-04 AC3: offline, the draft stays here and is sent when the connection is back", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const saveDraft = vi.fn(async () => fail("offline")) as ReviewApi["saveDraft"];
    const api = await show(fakeApi({ saveDraft }));
    type("dở dang");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(screen.getByText("Đã lưu trên máy này, sẽ đồng bộ khi có mạng")).toBeTruthy();
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "dở dang", synced: false });
    vi.mocked(api.saveDraft).mockResolvedValue(ok(null));
    await act(async () => {
      window.dispatchEvent(new Event("online"));
    });
    await waitFor(() => expect(api.saveDraft).toHaveBeenCalledTimes(2));
    expect(readDraft(ATTEMPT)).toMatchObject({ synced: true });
  });

  // Review 🟠1. Red when: a save that finishes after more typing marks the older text as the
  // base, so a reload hides the newer text behind the server's draft.
  it("text typed while a save is in flight is still sent after a reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let finish: (reply: Reply<null>) => void = () => {};
    const saveDraft = vi.fn(
      () => new Promise<Reply<null>>((resolve) => (finish = resolve)),
    ) as ReviewApi["saveDraft"];
    await show(fakeApi({ saveDraft }));
    type("TCP");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    type("TCP tin cậy");
    await act(async () => finish(ok(null)));
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "TCP tin cậy", synced: false, base: "TCP" });
    cleanup();
    const again = await show(
      fakeApi({
        current: vi.fn(async () =>
          ok(current({ attempt: { id: ATTEMPT, status: "draft", answer_text: "TCP", dont_remember: false } })),
        ),
      }),
    );
    expect(field().value).toBe("TCP tin cậy");
    await waitFor(() =>
      expect(again.saveDraft).toHaveBeenCalledWith(ATTEMPT, { answer_text: "TCP tin cậy", dont_remember: false }),
    );
  });

  // Review 🟡2. Red when: unsent text overwrites a draft another device saved since (the check
  // `start.text === local.text` before sending is dropped).
  it("a draft changed from another device is shown and not overwritten", async () => {
    writeDraft(ATTEMPT, { text: "gõ ở đây", dontRemember: false, synced: false, base: "cũ" });
    const api = await show(
      fakeApi({
        current: vi.fn(async () =>
          ok(current({ attempt: { id: ATTEMPT, status: "draft", answer_text: "máy khác", dont_remember: false } })),
        ),
      }),
    );
    expect(field().value).toBe("máy khác");
    expect(api.saveDraft).not.toHaveBeenCalled();
  });

  // Red when: a graded answer stays editable, or its device copy outlives the submit.
  it("submitting shows the answer read-only, clears this device's copy and offers Câu tiếp", async () => {
    const api = await show(fakeApi());
    type("Vì Trái Đất tự quay.");
    await press("Gửi");
    expect(api.submit).toHaveBeenCalledWith(ATTEMPT, { answer_text: "Vì Trái Đất tự quay.", dont_remember: false });
    expect(screen.queryByLabelText("Câu trả lời của bạn")).toBeNull();
    expect(screen.getByText("Vì Trái Đất tự quay.")).toBeTruthy();
    expect(readDraft(ATTEMPT)).toBeNull();
    // T2.16: the result shows in the right column
    expect(screen.getByText("Đúng một phần")).toBeTruthy();
    expect(screen.getByText("Mặt Trời chỉ chiếu sáng một nửa Trái Đất.")).toBeTruthy();
    expect(screen.getByText("Trái Đất tự quay quanh trục.")).toBeTruthy();
    const next = screen.getByRole("button", { name: /Câu tiếp/ });
    expect(document.activeElement).toBe(next);
  });

  // US-04 AC2. Red when: "Không nhớ" sends the typed text, or is not marked as forgotten.
  it("US-04 AC2: Không nhớ submits as forgotten and says so", async () => {
    const api = await show(
      fakeApi({ submit: vi.fn(async () => ok(view({ answer_text: "" }))) as ReviewApi["submit"] }),
    );
    type("nửa chừng");
    await press("Không nhớ");
    // Review 🟡3: a half-written answer is not kept (and cannot be over the 4000 limit).
    expect(api.submit).toHaveBeenCalledWith(ATTEMPT, { answer_text: "", dont_remember: true });
    expect(screen.getByText("Bạn chọn Không nhớ.")).toBeTruthy();
  });

  // PLAN T2.15 "Xong khi" (23/10b), US-05. Red when: a failed grading loses the answer or hides
  // "Chấm lại".
  it.each([
    ["unavailable", "Chưa chấm được. Câu trả lời của bạn đã được lưu."],
    ["invalid", "Chưa chấm được. Câu trả lời của bạn đã được lưu."],
    ["disabled", "Chấm bài đang tạm tắt. Câu trả lời của bạn đã được lưu."],
  ] as const)("grading failed (%s): the answer stays and Chấm lại grades it", async (failure, text) => {
    const api = await show(
      fakeApi({
        submit: vi.fn(async () =>
          ok(view({ grading: "failed", failure, result: null })),
        ) as ReviewApi["submit"],
      }),
    );
    type("Vì Trái Đất tự quay.");
    await press("Gửi");
    expect(screen.getByText(text)).toBeTruthy();
    expect(screen.getByText("Vì Trái Đất tự quay.")).toBeTruthy();
    // plan D-7: "Câu tiếp" is never blocked by an ungraded answer
    expect(screen.getByRole("button", { name: /Câu tiếp/ })).toBeTruthy();
    await press("Chấm lại");
    expect(api.regrade).toHaveBeenCalledWith(ATTEMPT);
    expect(screen.queryByText(text)).toBeNull();
  });

  // Red when: a submit that never reached core-api (or timed out) loses what was typed.
  it("a submit that fails keeps the answer in the box to send again", async () => {
    const submit = vi.fn(async () => fail("offline")) as ReviewApi["submit"];
    const api = await show(fakeApi({ submit }));
    type("giữ lại");
    await press("Gửi");
    expect(field().value).toBe("giữ lại");
    expect(screen.getByText("Chưa gửi được. Câu trả lời vẫn ở đây, bạn gửi lại nhé.")).toBeTruthy();
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "giữ lại" });
    vi.mocked(api.submit).mockResolvedValue(ok(view()));
    await press("Gửi");
    expect(screen.queryByLabelText("Câu trả lời của bạn")).toBeNull();
  });

  // Plan 🟡9. Red when: "in_progress" (another tab is grading) is shown as a failure, or never read again.
  it("a grading still running elsewhere is read again until it has a result", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const read = vi.fn(async () => ok(view())) as ReviewApi["read"];
    const api = await show(
      fakeApi({
        submit: vi.fn(async () => ok(view({ grading: "in_progress", result: null }))) as ReviewApi["submit"],
        read,
      }),
    );
    type("x");
    await press("Gửi");
    expect(screen.getByText("Đang chấm dựa trên tài liệu của bạn…")).toBeTruthy();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2100);
    });
    expect(api.read).toHaveBeenCalledWith(ATTEMPT);
    expect(screen.queryByText("Đang chấm dựa trên tài liệu của bạn…")).toBeNull();
  });

  it("a grading that keeps running says to go on (DESIGN.md §6.5)", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const running = vi.fn(async () => ok(view({ grading: "in_progress", result: null })));
    await show(fakeApi({ submit: running as ReviewApi["submit"], read: running as ReviewApi["read"] }));
    type("x");
    await press("Gửi");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(30_000);
    });
    expect(screen.getByText("Câu trả lời đã được lưu. Đang chấm, bạn cứ làm câu tiếp theo.")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Câu tiếp/ })).toBeTruthy();
  });

  it("Câu tiếp shows the next question", async () => {
    const api = await show(fakeApi());
    type("x");
    await press("Gửi");
    vi.mocked(api.current).mockResolvedValue(
      ok(
        current({
          position: 2,
          question: { ...current().question, prompt: "Vì sao có mùa?" },
          attempt: { id: NEXT_ATTEMPT, status: "draft", answer_text: "", dont_remember: false },
        }),
      ),
    );
    await press(/Câu tiếp/);
    expect(screen.getByRole("heading", { name: "Vì sao có mùa?" })).toBeTruthy();
    expect(screen.queryByText("Vì sao có ngày và đêm?")).toBeNull();
    expect(screen.getByText("Câu 2 / 3")).toBeTruthy();
    expect(field().value).toBe("");
  });

  // Plan D-8, US-08 AC2. Red when: the last question does not close the session.
  it("after the last question, with everything graded, the session closes and Hôm nay shows", async () => {
    const api = await show(fakeApi({ current: vi.fn(async () => ok(current({ position: 3, total: 3 }))) }));
    type("x");
    await press("Gửi");
    vi.mocked(api.current).mockResolvedValue(ok({ done: true as const, ungraded: [] }));
    await press("Về trang chính");
    expect(api.stop).toHaveBeenCalledWith(SESSION);
    expect(go).toHaveBeenCalledWith("/today");
  });

  // Plan D-7. Red when: answers left ungraded at the end are dropped silently, or the way out is blocked.
  it("answers left ungraded at the end are listed, each with Chấm lại, and the way out stays", async () => {
    const read = vi.fn(async () =>
      ok(view({ grading: "failed", failure: null, result: null, question: { id: "0b8f1d2e-0000-4000-8000-0000000000b1", prompt: "Vì sao có mùa?" } })),
    ) as ReviewApi["read"];
    const api = await show(
      fakeApi({ current: vi.fn(async () => ok({ done: true as const, ungraded: [NEXT_ATTEMPT] })), read }),
    );
    expect(screen.getByText("Còn 1 câu chưa chấm")).toBeTruthy();
    expect(await screen.findByText("Vì sao có mùa?")).toBeTruthy();
    await press("Chấm lại");
    expect(api.regrade).toHaveBeenCalledWith(NEXT_ATTEMPT);
    expect(await screen.findByText("Đã chấm")).toBeTruthy();
    await press("Về trang chính");
    expect(api.stop).toHaveBeenCalledWith(SESSION);
    expect(go).toHaveBeenCalledWith("/today");
  });

  // US-08 AC2, plan D-8. Red when: "Dừng tại đây" is missing, or a failed stop traps the user.
  it.each([
    ["stops", ok({ answered: 0, total: 3 })],
    ["still leaves when stop fails", fail("offline")],
  ])("Dừng tại đây %s and goes to Hôm nay", async (_, reply) => {
    const api = await show(fakeApi({ stop: vi.fn(async () => reply) as ReviewApi["stop"] }));
    await press("Dừng tại đây");
    expect(api.stop).toHaveBeenCalledWith(SESSION);
    expect(go).toHaveBeenCalledWith("/today");
  });

  // DESIGN.md §6.4. Red when: a failed load shows a blank page or a guess.
  it("a question that cannot load says so, keeps the answers, and tries again", async () => {
    const api = await show(fakeApi({ current: vi.fn(async () => fail("unavailable")) as ReviewApi["current"] }));
    expect(screen.getByText("Không tải được câu tiếp theo.")).toBeTruthy();
    expect(screen.getByText("Các câu trả lời trước đã được lưu.")).toBeTruthy();
    vi.mocked(api.current).mockResolvedValue(ok(current()));
    await press("Thử lại");
    expect(screen.getByRole("heading", { name: "Vì sao có ngày và đêm?" })).toBeTruthy();
  });

  it.each(["session_ended", "session_not_found"])("a session that is over or not yours (%s) says so", async (code) => {
    await show(fakeApi({ current: vi.fn(async () => fail(code)) as ReviewApi["current"] }));
    expect(screen.getByText("Phiên ôn này đã kết thúc.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Về trang chính" })).toBeTruthy();
  });

  it("a session ended in another tab while answering says so instead of losing the answer silently", async () => {
    const submit = vi.fn(async () => fail("session_ended")) as ReviewApi["submit"];
    await show(fakeApi({ submit }));
    type("x");
    await press("Gửi");
    expect(screen.getByText("Phiên ôn này đã kết thúc.")).toBeTruthy();
  });
});

// Tester (T2.15, 26/10): the `base` a device copy is written over (lib/draft, review 🟠1). Each
// test names the change in components/review/review-screen.tsx that turns it red.
describe("ReviewScreen draft base (T2.15, tester)", () => {
  beforeEach(() => {
    go.mockReset();
    window.localStorage.clear();
  });
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  const serverDraft = (answer_text: string) =>
    vi.fn(async () => ok(current({ attempt: { id: ATTEMPT, status: "draft", answer_text, dont_remember: false } })));

  // Red when: `show` stops setting `baseRef` to core-api's text, or `change` writes another base:
  // text typed offline over core-api's draft "cũ" is then hidden behind "cũ" on reload.
  it("text typed offline over core-api's draft is kept over that draft after a reload", async () => {
    const saveDraft = vi.fn(async () => fail("offline")) as ReviewApi["saveDraft"];
    await show(fakeApi({ current: serverDraft("cũ"), saveDraft }));
    type("cũ và mới");
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "cũ và mới", synced: false, base: "cũ" });
    cleanup();
    const again = await show(fakeApi({ current: serverDraft("cũ") }));
    expect(field().value).toBe("cũ và mới");
    await waitFor(() =>
      expect(again.saveDraft).toHaveBeenCalledWith(ATTEMPT, { answer_text: "cũ và mới", dont_remember: false }),
    );
  });

  // Red when: a save that succeeds no longer moves `baseRef` to the saved text: what is typed
  // next is written over the old base, and a reload before the next save shows core-api's text.
  it("text typed after a save is kept over the saved text after a reload", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await show(fakeApi());
    type("TCP");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "TCP", synced: true });
    type("TCP tin cậy");
    expect(readDraft(ATTEMPT)).toMatchObject({ text: "TCP tin cậy", synced: false, base: "TCP" });
    cleanup();
    await show(fakeApi({ current: serverDraft("TCP") }));
    expect(field().value).toBe("TCP tin cậy");
  });

  // Red when: the check `attemptRef.current !== attemptId` after a draft save is dropped: a save
  // of the previous question finishing after "Câu tiếp" writes the new question's text under the
  // old attempt's key and moves the new question's base to the old text.
  it("a draft save finishing after Câu tiếp touches neither question's device copy", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    let finish: (reply: Reply<null>) => void = () => {};
    const saveDraft = vi.fn(
      () => new Promise<Reply<null>>((resolve) => (finish = resolve)),
    ) as ReviewApi["saveDraft"];
    const api = await show(fakeApi({ saveDraft }));
    type("câu một");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    await press("Gửi");
    vi.mocked(api.current).mockResolvedValue(
      ok(current({ position: 2, attempt: { id: NEXT_ATTEMPT, status: "draft", answer_text: "", dont_remember: false } })),
    );
    await press(/Câu tiếp/);
    type("câu hai");
    await act(async () => finish(ok(null)));
    expect(readDraft(ATTEMPT)).toBeNull();
    expect(readDraft(NEXT_ATTEMPT)).toMatchObject({ text: "câu hai", synced: false, base: "" });
  });
});
