// @vitest-environment jsdom
// T7.5 (US-01 AC4, AC5; US-13 AC1, AC4, AC9): the role of an uploaded file and the outline screen on
// the real API, with the browser's calls faked.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { OutlineOut } from "@/lib/syllabus/api";

const api = vi.hoisted(() => ({
  patchDocument: vi.fn(),
  putTextbook: vi.fn(),
  patchSection: vi.fn(),
  readOutline: vi.fn(),
}));

vi.mock("@/lib/syllabus/api", async (original) => ({
  ...(await original<typeof import("@/lib/syllabus/api")>()),
  ...api,
}));

const { DocRole } = await import("@/components/syllabus/doc-role");
const { SyllabusLive } = await import("@/components/syllabus/syllabus-live");

const SUBJECT = "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b";
const DOC = "c3d4e5f6-7a8b-4c9d-8e1f-2a3b4c5d6e7f";
const ok = { ok: true, data: {} };

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  Object.values(api).forEach((mock) => mock.mockReset());
});

const role = (name: string) => screen.getByRole("radio", { name }) as HTMLInputElement;
const flush = () => act(async () => void (await vi.advanceTimersByTimeAsync(0)));

describe("DocRole (US-01 AC4, AC5)", () => {
  // Red when: the first file is not made the main textbook, or the call is wrong.
  it("a first file is set as the main textbook through PATCH role textbook", async () => {
    api.patchDocument.mockResolvedValue(ok);
    render(<DocRole subjectId={SUBJECT} documentId={DOC} name="GT.pdf" initialRole="main" />);
    await flush();
    expect(api.patchDocument).toHaveBeenCalledWith(DOC, { role: "textbook" });
    expect(role("Giáo trình chính").checked).toBe(true);
  });

  // Red when: a file not read yet is refused for good instead of waiting.
  it("document_not_ready waits and tries again until the file is read", async () => {
    api.patchDocument
      .mockResolvedValueOnce({ ok: false, code: "document_not_ready" })
      .mockResolvedValueOnce(ok);
    render(<DocRole subjectId={SUBJECT} documentId={DOC} name="GT.pdf" initialRole="main" />);
    await flush();
    expect(screen.getByRole("status").textContent).toContain("khi đọc xong");
    await act(async () => void (await vi.advanceTimersByTimeAsync(3100)));
    expect(api.patchDocument).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("status").textContent).toBe("");
  });

  // Red when: an existing textbook is replaced without the learner agreeing, or the card count is lost.
  it("textbook_exists asks first; a card count asks again; only then confirm: true is sent", async () => {
    api.patchDocument.mockResolvedValue({ ok: false, code: "textbook_exists" });
    api.putTextbook
      .mockResolvedValueOnce({ ok: false, code: "textbook_has_cards", cards: 7 })
      .mockResolvedValueOnce(ok);
    render(<DocRole subjectId={SUBJECT} documentId={DOC} name="GT2.pdf" initialRole="supplementary" />);
    await act(async () => fireEvent.click(role("Giáo trình chính")));
    await flush();
    expect(api.putTextbook).not.toHaveBeenCalled();
    expect(screen.getByRole("group", { name: "Đổi giáo trình chính" }).textContent).toContain("đã có giáo trình chính");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Đổi giáo trình chính" })));
    await flush();
    expect(api.putTextbook).toHaveBeenLastCalledWith(SUBJECT, DOC, false);
    expect(screen.getByRole("group", { name: "Đổi giáo trình chính" }).textContent).toContain("7 thẻ");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Vẫn đổi" })));
    await flush();
    expect(api.putTextbook).toHaveBeenLastCalledWith(SUBJECT, DOC, true);
    expect(screen.queryByRole("group", { name: "Đổi giáo trình chính" })).toBeNull();
    expect(role("Giáo trình chính").checked).toBe(true);
  });

  it("declining the replacement keeps the old role and sends nothing more", async () => {
    api.patchDocument.mockResolvedValue({ ok: false, code: "textbook_exists" });
    render(<DocRole subjectId={SUBJECT} documentId={DOC} name="GT2.pdf" initialRole="supplementary" />);
    await act(async () => fireEvent.click(role("Giáo trình chính")));
    await flush();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Giữ giáo trình cũ" })));
    expect(role("Tài liệu phụ").checked).toBe(true);
    expect(api.putTextbook).not.toHaveBeenCalled();
  });

  it("a question bank is PATCHed as question_bank; a refusal shows a retry", async () => {
    api.patchDocument.mockResolvedValueOnce({ ok: false, code: "unavailable" }).mockResolvedValueOnce(ok);
    render(<DocRole subjectId={SUBJECT} documentId={DOC} name="CH.pdf" initialRole="supplementary" />);
    await act(async () => fireEvent.click(role("Bộ câu hỏi")));
    await flush();
    expect(api.patchDocument).toHaveBeenCalledWith(DOC, { role: "question_bank" });
    expect(screen.getByRole("alert").textContent).toContain("Chưa đổi được vai trò");
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Thử lại" })));
    await flush();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

type Section = OutlineOut["sections"][number];
const sec = (over: Partial<Section> & { id: string }): Section => ({
  parent_id: null, title: `${over.id} Mục`, first_page: 1, last_page: 10, weight: 10, unit: "page", source: "bookmark",
  excluded: false, excluded_effective: false, progress: 0, studied: false, children: [], ...over,
});
const outline = (sections: Section[], over: Partial<OutlineOut> = {}): OutlineOut => ({
  subject_id: SUBJECT, document: { id: DOC, page_count: 100, short_name: "Giáo trình MMT" }, progress: 0,
  reason: null, temporary: false, sections, ...over,
});
const TREE = [sec({ id: "1", last_page: 20, weight: 20, children: [sec({ id: "1.1" }), sec({ id: "1.2", first_page: 11, last_page: 20 })] })];

describe("SyllabusLive (US-13)", () => {
  it("US-13 AC9: a chunk10 outline is labelled tạm and says it can be edited", () => {
    render(
      <SyllabusLive
        subjectId={SUBJECT}
        subjectName="Mạng"
        initial={outline([sec({ id: "1", source: "chunk10" })], { temporary: true })}
      />,
    );
    expect(document.body.textContent).toContain("tạm: chia khối 10 trang");
    expect(document.querySelector("[data-notice=chunk10]")).not.toBeNull();
  });

  it("US-13 AC1: no textbook offers the upload; not read yet shows the wait and polls", async () => {
    const { unmount } = render(
      <SyllabusLive subjectId={SUBJECT} subjectName="Mạng" initial={outline([], { document: null, reason: "no_textbook" })} />,
    );
    expect(screen.getByRole("link", { name: "Tải giáo trình" }).getAttribute("href")).toBe(`/subjects/${SUBJECT}/upload`);
    unmount();
    api.readOutline.mockResolvedValue({ ok: true, data: outline(TREE) });
    render(<SyllabusLive subjectId={SUBJECT} subjectName="Mạng" initial={outline([], { reason: "not_indexed" })} />);
    expect(document.body.textContent).toContain("Đang đọc mục lục");
    await act(async () => void (await vi.advanceTimersByTimeAsync(4100)));
    expect(api.readOutline).toHaveBeenCalledWith(SUBJECT);
    expect(screen.getByRole("tree")).not.toBeNull();
  });

  // Red when: marking a leaf studied is not sent to core-api, or core-api's answer is not shown.
  it("US-13 AC4: marking a leaf studied PATCHes it and shows core-api's answer", async () => {
    const after = outline([
      sec({ id: "1", last_page: 20, weight: 20, progress: 0.5, children: [sec({ id: "1.1", studied: true, progress: 1 }), sec({ id: "1.2", first_page: 11, last_page: 20 })] }),
    ]);
    api.patchSection.mockResolvedValue({ ok: true, data: after });
    render(<SyllabusLive subjectId={SUBJECT} subjectName="Mạng" initial={outline(TREE)} />);
    fireEvent.keyDown(document.querySelector("[data-node='1.1']")!, { key: "Enter" });
    await flush();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /Đánh dấu đã học/ })));
    await flush();
    expect(api.patchSection).toHaveBeenCalledWith("1.1", { studied: true });
    expect(document.querySelector("[data-totals]")!.textContent).toContain("đã học 1/2 mục");
  });

  // Red when: a refused range stays on screen as if it were saved, or the refusal is silent.
  it("US-13 AC4: a range core-api refuses is undone with a visible message", async () => {
    api.patchSection.mockResolvedValue({ ok: false, code: "outside_parent" });
    api.readOutline.mockResolvedValue({ ok: true, data: outline(TREE) });
    render(<SyllabusLive subjectId={SUBJECT} subjectName="Mạng" initial={outline(TREE)} />);
    fireEvent.keyDown(document.querySelector("[data-node='1.1']")!, { key: "Enter" });
    await flush();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /Sửa khoảng trang/ })));
    const [from, to] = Array.from(document.querySelectorAll<HTMLInputElement>("[data-panel='1.1'] input"));
    fireEvent.change(from!, { target: { value: "2" } });
    fireEvent.change(to!, { target: { value: "9" } });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Lưu" })));
    await flush();
    expect(api.patchSection).toHaveBeenCalledWith("1.1", { first_page: 2, last_page: 9 });
    expect(document.querySelector("[data-save-failure]")!.textContent).toContain("ngoài mục cha");
    expect(document.querySelector("[data-node='1.1']")!.textContent).toContain("tr. 1–10");
  });
});
