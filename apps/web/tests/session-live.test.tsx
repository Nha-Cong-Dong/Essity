// @vitest-environment jsdom
// T7.12 (US-02 AC2-AC4, AC9-AC11; CARDS-V3): the study session screen on a faked core-api.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type SessionInitial, SessionScreen } from "@/components/session-study/session-screen";
import type { ApiResult, Phase, SessionApi } from "@/lib/session-study/api";
import { initialRound, type Round } from "@/lib/session-study/round";

const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const DOCS = [{ id: DOC, name: "Giáo trình", role: "Giáo trình chính" }];
const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn phần đề cương." } as const;

const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });
const fail = (status: number, error: string): Promise<ApiResult<never>> =>
  Promise.resolve({ ok: false, status, error });

type Fake = { [K in keyof SessionApi]: SessionApi[K] extends (...args: infer A) => infer R ? ReturnType<typeof vi.fn<(...args: A) => R>> : SessionApi[K] };

function fakeApi(over: Partial<SessionApi> = {}): Fake {
  const api = {
    sessionId: "s1",
    submit: vi.fn(() => ok({ status: "queued" as Phase })),
    upload: vi.fn(async () => undefined),
    result: vi.fn(() => ok({ phase: "processing" as Phase, title: null as string | null, cards: 0, notice: null as string | null })),
    ...over,
  };
  return api as unknown as Fake;
}

function show(api: Fake, patch: Partial<Omit<SessionInitial, "round">> & { round?: Partial<Round> } = {}, subjectId?: string) {
  const { round, ...rest } = patch;
  const initial: SessionInitial = {
    round: { ...initialRound, ...round },
    text: "",
    mentions: [],
    files: [],
    ...rest,
  };
  return render(
    <SessionScreen
      api={api as unknown as SessionApi}
      subject="Mạng máy tính"
      subjectId={subjectId}
      stopHref="/today"
      docs={DOCS}
      suggestion={FREE}
      nextSuggestion={FREE}
      initial={initial}
    />,
  );
}

const tick = (ms: number) =>
  act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  // jsdom has neither; the screen asks for reduced motion before it scrolls to a changed card.
  vi.stubGlobal("matchMedia", () => ({ matches: false }));
  Element.prototype.scrollIntoView = vi.fn();
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("study session on core-api", () => {
  // US-02 AC1, AC14; CARDS-V3. Red when: the sentence is not sent, the poll does not end in the
  // confirmation with the count, the session name and the Kho link, or "Học tiếp hay dừng?" is missing.
  it("sends the sentence, polls the result and confirms the cards that went into the Kho", async () => {
    const api = fakeApi({ result: vi.fn(() => ok({ phase: "done" as Phase, title: "TCP flow control", cards: 4, notice: null })) });
    show(api, {}, "SUBJ");
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Tối nay học phần 3.2" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(api.submit).toHaveBeenCalledWith("Tối nay học phần 3.2", [], []);
    await tick(2600);
    // The polite live region says it too, so the text is found twice.
    expect((await screen.findAllByText("Đã thêm 4 thẻ vào Kho.")).length).toBeGreaterThan(0);
    expect(screen.getByText("Buổi học: TCP flow control")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Xem trong Kho kiến thức" }).getAttribute("href")).toBe("/kho-kien-thuc?subject=SUBJ&session=s1");
    expect(screen.getByText("Học tiếp hay dừng?")).toBeTruthy();
    expect(screen.queryByText(/nháp/)).toBeNull();
  });

  // CARDS-V3. Red when: a done read with no card is silent, or does not point to the outline.
  it("a done read with no card says so and points to the outline", async () => {
    const api = fakeApi({ result: vi.fn(() => ok({ phase: "done" as Phase, title: null, cards: 0, notice: "no_content_found" })) });
    show(api, { round: { phase: "processing", submission: "processing" } }, "SUBJ");
    await tick(2600);
    // The polite live region says it too, so the text is found twice.
    expect((await screen.findAllByText("Chưa tìm thấy nội dung để làm thẻ.")).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: "Chọn mục từ đề cương" }).getAttribute("href")).toBe("/subjects/SUBJ/syllabus");
    expect(screen.queryByText(/Đã thêm 0 thẻ/)).toBeNull();
  });

  // CARDS-V3. Red when: a failed read keeps polling or loses the retry.
  it("a failed read stays in processing with Thử lại", async () => {
    const api = fakeApi({ result: vi.fn(() => ok({ phase: "failed" as Phase, title: null, cards: 0, notice: null })) });
    show(api, { round: { phase: "processing", submission: "processing" } });
    await tick(2600);
    expect(await screen.findByText(/Chưa đọc được bài nộp/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Thử lại" })).toBeTruthy();
    const calls = api.result.mock.calls.length;
    await tick(6000);
    expect(api.result.mock.calls.length).toBe(calls);
  });

  // US-02 AC4. Red when: a refused @ does not show on its chip, or the sentence is lost.
  it("a refused mention takes the learner back to the form with the sentence kept", async () => {
    const api = fakeApi({
      submit: vi.fn(() => Promise.resolve({ ok: false as const, status: 422, error: "scope_not_found", docId: DOC })),
    });
    show(api, { text: "học @Giáo trình phần 9.9", mentions: [{ docId: DOC, name: "Giáo trình", start: 4, end: 14 }] });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(50);
    expect(await screen.findByText(/Chưa rõ phần sau Giáo trình/)).toBeTruthy();
    expect((screen.getByRole("combobox") as HTMLTextAreaElement).value).toBe("học @Giáo trình phần 9.9");
  });

  // US-02 AC11, AC14. Red when: a dropped network leaves the learner on "Đang chờ" forever.
  it("a send that does not get through goes back to the form with a neutral line", async () => {
    show(fakeApi({ submit: vi.fn(() => fail(0, "network")) }), { text: "x" });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(50);
    expect(await screen.findByText(/Chưa gửi được/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Gửi" })).toBeTruthy();
  });

  // US-02 AC15. Red when: pending_ai drops its waiting line, or the result never arrives once the AI is back.
  it("pending_ai keeps its waiting line, and the result comes when the read ends", async () => {
    const api = fakeApi();
    show(api, { round: { phase: "processing", submission: "pending_ai" } });
    expect(screen.getByText(/hết lượt AI/)).toBeTruthy();
    api.result.mockImplementation(() => ok({ phase: "done" as Phase, title: "Buổi 1", cards: 2, notice: null }));
    await tick(2600);
    // The polite live region says it too, so the text is found twice.
    expect((await screen.findAllByText("Đã thêm 2 thẻ vào Kho.")).length).toBeGreaterThan(0);
  });

  // CARDS-V3. Red when: a reopened finished session shows the form again instead of its result.
  it("opens on the result of a finished session", () => {
    show(fakeApi(), { round: { phase: "done", result: { cards: 3, title: "TCP", notice: null } } });
    expect(screen.getAllByText("Đã thêm 3 thẻ vào Kho.").length).toBeGreaterThan(0);
  });

  // a11y fix (T7.12a review): aria-controls names the list only while it exists.
  it("aria-controls points at the @ list only while it is open", () => {
    show(fakeApi());
    const box = screen.getByRole("combobox") as HTMLTextAreaElement;
    expect(box.getAttribute("aria-controls")).toBeNull();
    fireEvent.change(box, { target: { value: "học @", selectionStart: 5 } });
    box.setSelectionRange(5, 5);
    fireEvent.select(box);
    const id = box.getAttribute("aria-controls");
    expect(id).not.toBeNull();
    expect(document.getElementById(id as string)).not.toBeNull();
    fireEvent.keyDown(box, { key: "Escape" });
    expect(box.getAttribute("aria-controls")).toBeNull();
  });

  // US-02 AC3. Red when: choosing one document twice shows no word about how each @ reads.
  it("a document chosen twice gets one line on how each @ reads", () => {
    const two = [
      { docId: DOC, name: "Giáo trình", start: 4, end: 14 },
      { docId: DOC, name: "Giáo trình", start: 24, end: 34 },
    ];
    show(fakeApi(), { text: "học @Giáo trình 3.1 và @Giáo trình 3.2", mentions: two });
    expect(screen.getByText(/Giáo trình có mặt nhiều lần/)).toBeTruthy();
  });

  // US-02 AC2. Red when: a send with neither words nor files reaches core-api.
  it("needs some words or a file to send", () => {
    const api = fakeApi();
    show(api);
    expect(screen.getByText("Chọn file")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(api.submit).not.toHaveBeenCalled();
    expect(screen.getByText("Chưa có gì để gửi. Viết vài dòng hoặc thêm file rồi gửi.")).toBeTruthy();
  });
});

describe("files on the study session (T7.12c)", () => {
  const REF = { sha256: "a".repeat(64), mime: "image/png" as const, size_bytes: 3 };
  type Report = (state: unknown) => void;
  const pick = (files: File[]) => fireEvent.change(screen.getByLabelText("Chọn file bài nộp"), { target: { files } });
  const ready = async (_file: File, report: Report) => report({ kind: "ready", ref: REF });

  // US-02 AC1, AC13. Red when: a picked file is not uploaded, the send leaves out what was uploaded,
  // or a send with files and no sentence is refused.
  it("uploads a picked photo and sends it with the submission, no sentence needed", async () => {
    const api = fakeApi({
      upload: vi.fn(async (_file: File, report: Report) => {
        report({ kind: "uploading", percent: 40 });
        report({ kind: "ready", ref: REF });
      }),
    });
    show(api);
    pick([new File(["abc"], "trang-1.png", { type: "image/png" })]);
    await tick(10);
    expect(api.upload).toHaveBeenCalledTimes(1);
    expect(await screen.findByText("Đã tải")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(10);
    expect(api.submit).toHaveBeenCalledWith("", [], [REF]);
  });

  // US-02 AC13. Red when: a failed file is handed in, or its failure is silent.
  it("a file that failed is told in words and never handed in", async () => {
    const api = fakeApi({ upload: vi.fn(async (_file: File, report: Report) => report({ kind: "failed", code: "offline" })) });
    show(api, { text: "học bài" });
    pick([new File(["abc"], "trang-1.png", { type: "image/png" })]);
    expect(await screen.findByText(/Chưa tải được/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(10);
    expect(api.submit).toHaveBeenCalledWith("học bài", [], []);
  });

  // US-02 AC13. Red when: "Thử lại" does not upload the same file again.
  it("Thử lại uploads the same file again", async () => {
    let attempt = 0;
    const api = fakeApi({
      upload: vi.fn(async (_file: File, report: Report) => {
        attempt += 1;
        report(attempt === 1 ? { kind: "failed", code: "offline" } : { kind: "ready", ref: REF });
      }),
    });
    show(api);
    pick([new File(["abc"], "trang-1.png", { type: "image/png" })]);
    fireEvent.click(await screen.findByRole("button", { name: "Thử lại trang-1.png" }));
    expect(await screen.findByText("Đã tải")).toBeTruthy();
    expect(api.upload).toHaveBeenCalledTimes(2);
  });

  // US-02 AC13 (neutral copy). Red when: a wrong type is silent, or it blocks the rest.
  it("a wrong type shows the neutral line and the other file still goes", async () => {
    const api = fakeApi({
      upload: vi.fn(async (file: File, report: Report) =>
        report(file.name.endsWith(".exe") ? { kind: "failed", code: "unsupported" } : { kind: "ready", ref: REF }),
      ),
    });
    show(api);
    pick([new File(["x"], "a.exe"), new File(["abc"], "b.png", { type: "image/png" })]);
    expect(await screen.findByText(/Định dạng này chưa dùng được/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(10);
    expect(api.submit).toHaveBeenCalledWith("", [], [REF]);
  });

  // US-02 AC13. Red when: the same file picked twice is sent twice.
  it("the same file twice is handed in once", async () => {
    const api = fakeApi({ upload: vi.fn(ready) });
    show(api);
    pick([new File(["abc"], "a.png", { type: "image/png" }), new File(["abc"], "b.png", { type: "image/png" })]);
    await tick(10);
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(10);
    expect(api.submit).toHaveBeenCalledWith("", [], [REF]);
  });
});
