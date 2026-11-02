// @vitest-environment jsdom
// T7.12 (US-02 AC2-AC4, AC9-AC11; US-02b AC6-AC9): the study session screen on a faked core-api.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type SessionInitial, SessionScreen } from "@/components/session-study/session-screen";
import type { ApiResult, Phase, SessionApi } from "@/lib/session-study/api";
import type { Draft } from "@/lib/session-study/drafts";
import { initialRound, type Round } from "@/lib/session-study/round";

const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const DOCS = [{ id: DOC, name: "Giáo trình", role: "Giáo trình chính" }];
const FREE = { kind: "free", text: "Buổi học tự do. Bài nộp không gắn mục đề cương." } as const;

const card = (id: string, extra: Partial<Draft> = {}): Draft => ({
  id,
  title: `Thẻ ${id}`,
  summary: `Ý của ${id}`,
  section: null,
  anchors: [],
  origin: "ai",
  status: "draft",
  version: 1,
  conflict: null,
  source: "both",
  ...extra,
});
const ok = <T,>(data: T): Promise<ApiResult<T>> => Promise.resolve({ ok: true, data });
const fail = (status: number, error: string): Promise<ApiResult<never>> =>
  Promise.resolve({ ok: false, status, error });

type Fake = { [K in keyof SessionApi]: SessionApi[K] extends (...args: infer A) => infer R ? ReturnType<typeof vi.fn<(...args: A) => R>> : SessionApi[K] };

function fakeApi(over: Partial<SessionApi> = {}): Fake {
  const api = {
    sessionId: "s1",
    submit: vi.fn(() => ok({ status: "queued" as Phase })),
    upload: vi.fn(async () => undefined),
    load: vi.fn(() => ok({ phase: "processing" as Phase, drafts: [] as Draft[] })),
    get: vi.fn((id: string) => ok(card(id, { version: 5, summary: "Bản mới trên máy chủ" }))),
    edit: vi.fn((id: string, version: number) => ok(card(id, { version: version + 1 }))),
    discard: vi.fn((id: string) => ok(card(id, { status: "retired" as const }))),
    undo: vi.fn((id: string) => ok(card(id))),
    add: vi.fn(() => ok(card("srv-new", { title: "Mới", summary: "Mới" }))),
    merge: vi.fn(() => ok(card("merged", { summary: "Đã gộp" }))),
    split: vi.fn(() => ok([card("p1"), card("p2")])),
    save: vi.fn((cards: { id: string; version: number }[]) => ok(cards.map((c) => c.id))),
    ...over,
  };
  return api as unknown as Fake;
}

function show(api: Fake, patch: Partial<Omit<SessionInitial, "round">> & { round?: Partial<Round> } = {}) {
  const { round, ...rest } = patch;
  const initial: SessionInitial = {
    round: { ...initialRound, ...round },
    drafts: [],
    text: "",
    mentions: [],
    files: [],
    scope: [],
    saved: "free",
    resumed: false,
    ...rest,
  };
  return render(
    <SessionScreen
      api={api as unknown as SessionApi}
      subject="Mạng máy tính"
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
const review = { round: { phase: "review" as const } };
const cards = () => within(screen.getByRole("list", { name: "Thẻ nháp" }));

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
  // US-02 AC1, AC14; US-02b AC6, AC7, AC9. Red when: the sentence is not sent, the cards the
  // reading made do not appear, an edit does not reach core-api with the version it saw, or Save
  // does not end in "Học tiếp hay dừng?".
  it("sends the sentence, shows the cards, saves an edit, and asks to go on or stop", async () => {
    const api = fakeApi({ load: vi.fn(() => ok({ phase: "done" as Phase, drafts: [card("u1"), card("u2")] })) });
    show(api);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "Tối nay học mục 3.2" } });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(api.submit).toHaveBeenCalledWith("Tối nay học mục 3.2", [], []);
    await tick(2600);
    expect(await screen.findByText("Thẻ u1")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Sửa thẻ Thẻ u1" }));
    fireEvent.change(screen.getByLabelText("Nội dung thẻ Thẻ u1"), { target: { value: "Ý đã sửa" } });
    await tick(900);
    expect(api.edit).toHaveBeenCalledWith("u1", 1, { title: "Thẻ u1", content: "Ý đã sửa" });

    fireEvent.click(screen.getByRole("button", { name: "Đúng rồi, lưu" }));
    await tick(50);
    expect(api.save).toHaveBeenCalledWith([
      { id: "u1", version: 2 },
      { id: "u2", version: 1 },
    ]);
    expect(await screen.findByText("Học tiếp hay dừng?")).toBeTruthy();
  });

  // US-02 AC4. Red when: a refused @ does not show on its chip, or the sentence is lost.
  it("a refused mention takes the learner back to the form with the sentence kept", async () => {
    const api = fakeApi({
      submit: vi.fn(() => Promise.resolve({ ok: false as const, status: 422, error: "scope_not_found", docId: DOC })),
    });
    show(api, { text: "học @Giáo trình mục 9.9", mentions: [{ docId: DOC, name: "Giáo trình", start: 4, end: 14 }] });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(50);
    expect(await screen.findByText(/Chưa rõ phần sau Giáo trình/)).toBeTruthy();
    expect((screen.getByRole("combobox") as HTMLTextAreaElement).value).toBe("học @Giáo trình mục 9.9");
  });

  // US-02 AC11, AC14. Red when: a dropped network leaves the learner on "Đang chờ" forever.
  it("a send that does not get through goes back to the form with a neutral line", async () => {
    show(fakeApi({ submit: vi.fn(() => fail(0, "network")) }), { text: "x" });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    await tick(50);
    expect(await screen.findByText(/Chưa gửi được/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Gửi" })).toBeTruthy();
  });

  // US-02 AC15; US-02b AC10. Red when: pending_ai does not say manual edits still work, or the cards
  // never arrive after the AI is back.
  it("pending_ai says editing by hand still works, and the cards come when the read ends", async () => {
    const api = fakeApi();
    show(api, { round: { phase: "processing", submission: "pending_ai" } });
    expect(screen.getByText(/vẫn thêm và sửa thẻ\s+bằng tay được/)).toBeTruthy();
    api.load.mockImplementation(() => ok({ phase: "done" as Phase, drafts: [card("late")] }));
    await tick(2600);
    expect(await screen.findByText("Thẻ late")).toBeTruthy();
  });

  // US-02 AC1; US-02b AC8 (resume). Red when: reopening drops the cards or the note that they were kept.
  it("opens on the cards that were kept", () => {
    show(fakeApi(), { ...review, drafts: [card("u1")], resumed: true });
    expect(screen.getByText(/Buổi học đang dở/)).toBeTruthy();
    expect(screen.getByText("Thẻ u1")).toBeTruthy();
  });

  // US-02b AC7. Red when: a stale edit is not told as "đã đổi ở nơi khác", Save goes on past it,
  // or "Tải lại thẻ" does not bring the server's card.
  it("a 409 shows the card as changed elsewhere, blocks Save and reloads", async () => {
    const api = fakeApi({ edit: vi.fn(() => fail(409, "unit_changed_elsewhere")) });
    show(api, { ...review, drafts: [card("u1")] });
    fireEvent.click(screen.getByRole("button", { name: "Sửa thẻ Thẻ u1" }));
    fireEvent.change(screen.getByLabelText("Nội dung thẻ Thẻ u1"), { target: { value: "Chữ của tôi" } });
    await tick(900);
    expect(await screen.findByText("Thẻ này đã đổi ở nơi khác.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Đúng rồi, lưu" }));
    await tick(50);
    expect(api.save).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Tải lại thẻ" }));
    await tick(50);
    expect(api.get).toHaveBeenCalledWith("u1");
    expect(await screen.findByText("Bản mới trên máy chủ")).toBeTruthy();
    expect(screen.queryByText("Thẻ này đã đổi ở nơi khác.")).toBeNull();
  });

  // US-02b AC9. Red when: a 409 on Save is shown as a plain failure, or the changed card is not marked.
  it("a 409 on Save marks the card that changed", async () => {
    const api = fakeApi({
      save: vi.fn(() => fail(409, "unit_changed_elsewhere")),
      get: vi.fn((id: string) => ok(card(id, { version: 9 }))),
    });
    show(api, { ...review, drafts: [card("u1")] });
    fireEvent.click(screen.getByRole("button", { name: "Đúng rồi, lưu" }));
    await tick(50);
    expect(await screen.findByText("Thẻ này đã đổi ở nơi khác.")).toBeTruthy();
    expect(screen.queryByText("Chưa lưu được. Các thẻ nháp vẫn còn nguyên.")).toBeNull();
  });

  // US-02b AC6, AC8. Red when: a discard is not sent, a failed one stays hidden, or undo is not sent.
  it("discard and undo go to core-api; a failed discard brings the card back", async () => {
    const api = fakeApi();
    show(api, { ...review, drafts: [card("u1"), card("u2")] });
    fireEvent.click(cards().getAllByRole("button", { name: "Bỏ thẻ" })[0]);
    await tick(50);
    expect(api.discard).toHaveBeenCalledWith("u1");
    fireEvent.click(screen.getByRole("button", { name: "Hoàn tác" }));
    await tick(50);
    expect(api.undo).toHaveBeenCalledWith("u1");

    api.discard.mockImplementation(() => fail(0, "network"));
    fireEvent.click(cards().getAllByRole("button", { name: "Bỏ thẻ" })[0]);
    await tick(50);
    expect(await screen.findByText("Thẻ u1")).toBeTruthy();
    expect(screen.getByText("Chưa bỏ được thẻ. Thử lại sau.")).toBeTruthy();
  });

  // US-02b AC6. Red when: a card added by hand is sent before it has a title and a text, or twice.
  it("adds a card by hand once it is titled and written", async () => {
    const api = fakeApi();
    show(api, { ...review, drafts: [card("u1")] });
    fireEvent.click(screen.getByRole("button", { name: "Thêm thẻ" }));
    fireEvent.change(screen.getByLabelText("Tên thẻ"), { target: { value: "Mới" } });
    await tick(900);
    expect(api.add).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Nội dung thẻ/), { target: { value: "Nội dung mới" } });
    fireEvent.change(screen.getByLabelText(/Nội dung thẻ/), { target: { value: "Nội dung mới hơn" } });
    await tick(900);
    expect(api.add).toHaveBeenCalledTimes(1);
    expect(api.add).toHaveBeenCalledWith("Mới", "Nội dung mới hơn");
  });

  // US-02b AC6, AC9. Red when: text typed while the add is in flight is lost (the timer still names
  // the local id), or Save sends the old text.
  it("keeps what is typed while a new card is being added, also for Save", async () => {
    let land: (card: Draft) => void = () => undefined;
    const api = fakeApi({ add: vi.fn(() => new Promise<ApiResult<Draft>>((r) => { land = (d) => r({ ok: true, data: d }); })) });
    show(api, { ...review, drafts: [card("u1")] });
    fireEvent.click(screen.getByRole("button", { name: "Thêm thẻ" }));
    fireEvent.change(screen.getByLabelText("Tên thẻ"), { target: { value: "Mới" } });
    fireEvent.change(screen.getByLabelText(/Nội dung thẻ/), { target: { value: "Bản một" } });
    await tick(900);
    expect(api.add).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText(/Nội dung thẻ/), { target: { value: "Bản hai" } });
    await act(async () => { land(card("srv1", { title: "Mới", summary: "Bản một", version: 1 })); });
    await tick(900);
    expect(api.edit).toHaveBeenCalledWith("srv1", 1, { title: "Mới", content: "Bản hai" });
    fireEvent.change(screen.getByLabelText(/Nội dung thẻ/), { target: { value: "Bản ba" } });
    fireEvent.click(screen.getByRole("button", { name: "Đúng rồi, lưu" }));
    await tick(50);
    expect(api.edit).toHaveBeenLastCalledWith("srv1", 2, { title: "Mới", content: "Bản ba" });
    expect(api.save).toHaveBeenCalled();
  });

  // US-02b AC8. Red when: a card dropped while its add is in flight stays on the server as a draft.
  it("drops the server copy of a card discarded before its add landed", async () => {
    let land: (card: Draft) => void = () => undefined;
    const api = fakeApi({ add: vi.fn(() => new Promise<ApiResult<Draft>>((r) => { land = (d) => r({ ok: true, data: d }); })) });
    show(api, { ...review, drafts: [card("u1")] });
    fireEvent.click(screen.getByRole("button", { name: "Thêm thẻ" }));
    fireEvent.change(screen.getByLabelText("Tên thẻ"), { target: { value: "Mới" } });
    fireEvent.change(screen.getByLabelText(/Nội dung thẻ/), { target: { value: "Nội dung" } });
    await tick(900);
    fireEvent.click(cards().getAllByRole("button", { name: "Bỏ thẻ" })[1]);
    await act(async () => { land(card("srv1")); });
    await tick(50);
    expect(api.discard).toHaveBeenCalledWith("srv1");
  });

  // US-02b AC6 and a11y (T7.12a review): the split box closes when the split took effect, only then.
  it("split closes its box on success and stays open on a refusal", async () => {
    const api = fakeApi({ split: vi.fn(() => fail(422, "bad_split")) });
    show(api, { ...review, drafts: [card("u1", { summary: "Câu một. Câu hai." })] });
    fireEvent.click(screen.getByRole("button", { name: "Tách" }));
    fireEvent.click(screen.getByRole("button", { name: "Tách thẻ" }));
    await tick(50);
    expect(await screen.findByText("Chưa tách được thẻ. Thử lại sau.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Tách thẻ" })).toBeTruthy();
    api.split.mockImplementation(() => ok([card("p1"), card("p2")]));
    fireEvent.click(screen.getByRole("button", { name: "Tách thẻ" }));
    await tick(50);
    expect(await screen.findByText("Thẻ p2")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Tách thẻ" })).toBeNull();
    expect(api.split).toHaveBeenLastCalledWith("u1", 1, expect.arrayContaining([expect.objectContaining({ content: "Câu một." })]));
  });

  // US-02b AC6. Red when: the merged card does not replace the two.
  it("merge shows the card core-api made from the two", async () => {
    const api = fakeApi();
    show(api, { ...review, drafts: [card("u1"), card("u2")] });
    fireEvent.click(cards().getAllByRole("button", { name: "Gộp" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Gộp vào đây" }));
    await tick(50);
    expect(api.merge).toHaveBeenCalledWith(["u2", "u1"]);
    expect(await screen.findByText("Đã gộp")).toBeTruthy();
    expect(screen.queryByText("Thẻ u2")).toBeNull();
  });

  // a11y fix (T7.12a review): leaving the editor with Esc leaves the keyboard on the card.
  it("puts the focus back on the card after editing with Esc", async () => {
    show(fakeApi(), { ...review, drafts: [card("u1")] });
    fireEvent.click(screen.getByRole("button", { name: "Sửa thẻ Thẻ u1" }));
    fireEvent.keyDown(screen.getByLabelText("Nội dung thẻ Thẻ u1"), { key: "Escape" });
    await tick(50);
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Sửa thẻ Thẻ u1" }));
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
    expect(screen.getByText("Viết vài dòng mô tả buổi học rồi gửi.")).toBeTruthy();
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
