// @vitest-environment jsdom
// T4.13b (US-02 AC13): notebook photos on "Ghi buổi học", with the two session calls and the
// upload faked. Files are chosen before the sentence, sent once the draft exists, and Lưu waits.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CallResult, Card, ConfirmRange } from "@/lib/log-session";
import type { NoteRef, NoteState } from "@/lib/note-upload";

const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const SESSION_2 = "c3d4e5f6-7a8b-4c9d-8e0f-2a3b4c5d6e7f";
const NOTE: NoteRef = { sha256: "ab".repeat(32), mime: "image/jpeg", size_bytes: 3 };

const describe_ = vi.fn<(subject: string, text: string) => Promise<CallResult<Card>>>();
const confirm =
  vi.fn<
    (
      id: string,
      ranges: ConfirmRange[],
      on?: string | null,
      notes?: NoteRef[],
    ) => Promise<CallResult<{ session_id: string }>>
  >();
const upload = vi.fn<(session: string, file: File, on: (state: NoteState) => void) => Promise<void>>();

vi.mock("@/lib/log-session", async (original) => ({
  ...(await original<typeof import("@/lib/log-session")>()),
  describeSession: (s: string, t: string) => describe_(s, t),
  confirmSession: (id: string, r: ConfirmRange[], on?: string | null, notes?: NoteRef[]) =>
    confirm(id, r, on, notes),
}));
vi.mock("@/lib/note-upload", async (original) => ({
  ...(await original<typeof import("@/lib/note-upload")>()),
  uploadNote: (s: string, f: File, on: (state: NoteState) => void) => upload(s, f, on),
}));
vi.mock("@/lib/navigate", () => ({ go: () => undefined }));

const { LogSession } = await import("@/components/log-session");

afterEach(() => {
  cleanup();
  for (const mock of [describe_, confirm, upload]) mock.mockReset();
});

const noteOnly = (session_id = SESSION): Card =>
  ({
    session_id,
    card: "note_only",
    studied_on: null,
    ranges: [],
    documents: [],
    candidate_document_ids: [],
    question: null,
  }) as unknown as Card;

const photo = (name = "trang 5.jpg") => new File(["abc"], name, { type: "image/jpeg" });

function choose(...files: File[]) {
  fireEvent.change(screen.getByLabelText("Chọn ảnh vở hoặc file ghi chú"), { target: { files } });
}

async function send(text = "xem video về DNS") {
  fireEvent.change(screen.getByLabelText("Kể lại buổi học"), { target: { value: text } });
  await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
}

const lưu = () => screen.getByRole("button", { name: "Lưu" }) as HTMLButtonElement;
const ready = (on: (state: NoteState) => void) => on({ kind: "ready", note: NOTE });

describe("note drop on Ghi buổi học (T4.13b)", () => {
  // Red when: a file chosen first is sent before the draft exists, or never sent after.
  it("waits for the draft session, then sends the files chosen, and Lưu sends the notes", async () => {
    describe_.mockResolvedValue({ ok: true, data: noteOnly() });
    upload.mockImplementation(async (_s, _f, on) => ready(on));
    confirm.mockResolvedValue({ ok: true, data: { session_id: SESSION } });
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(photo());
    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByText("trang 5.jpg", { selector: "b" })).toBeTruthy();

    await send();
    expect(upload).toHaveBeenCalledTimes(1);
    expect(upload.mock.calls[0].slice(0, 2)).toEqual([SESSION, expect.any(File)]);

    await act(async () => fireEvent.click(lưu()));
    expect(confirm).toHaveBeenCalledWith(SESSION, [], null, [NOTE]);
    expect(screen.getByText(/Đã lưu buổi học/)).toBeTruthy();
  });

  // Red when: Lưu can be pressed while a photo is still on its way.
  it("Lưu waits while a file is uploading", async () => {
    describe_.mockResolvedValue({ ok: true, data: noteOnly() });
    let report: (state: NoteState) => void = () => undefined;
    upload.mockImplementation(async (_s, _f, on) => {
      report = on;
      on({ kind: "uploading", percent: 40 });
    });
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(photo());
    await send();
    expect(screen.getByText("đang tải 40%")).toBeTruthy();
    expect(lưu().disabled).toBe(true);
    await act(async () => ready(report));
    expect(lưu().disabled).toBe(false);
  });

  // Red when: a file the app refuses is sent, or dropped without a word.
  it("a type not allowed is said at once and never sent", async () => {
    describe_.mockResolvedValue({ ok: true, data: noteOnly() });
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(new File(["x"], "a.gif", { type: "image/gif" }));
    expect(screen.getByRole("alert").textContent).toContain("Chỉ nhận ảnh");
    await send();
    expect(upload).not.toHaveBeenCalled();
  });

  // Red when: a failed upload blocks Lưu for good, or its failure is sent as a note.
  it("a failed file says why and is not confirmed", async () => {
    describe_.mockResolvedValue({ ok: true, data: noteOnly() });
    upload.mockImplementation(async (_s, _f, on) => on({ kind: "failed", code: "storage_quota_exceeded" }));
    confirm.mockResolvedValue({ ok: true, data: { session_id: SESSION } });
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(photo());
    await send();
    expect(screen.getByRole("alert").textContent).toContain("dung lượng");
    await act(async () => fireEvent.click(lưu()));
    expect(confirm).toHaveBeenCalledWith(SESSION, [], null, []);
  });

  // Red when: a file can be taken off the list but still reaches confirm.
  it("a file dropped from the list is not confirmed", async () => {
    describe_.mockResolvedValue({ ok: true, data: noteOnly() });
    upload.mockImplementation(async (_s, _f, on) => ready(on));
    confirm.mockResolvedValue({ ok: true, data: { session_id: SESSION } });
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(photo());
    await send();
    fireEvent.click(screen.getByRole("button", { name: /Bỏ/ }));
    await act(async () => fireEvent.click(lưu()));
    expect(confirm).toHaveBeenCalledWith(SESSION, [], null, []);
  });

  // Red when: correcting the sentence leaves the photos on the old draft, where confirm would not
  // find them on the new one.
  it("a corrected sentence is a new draft: the files go to it again", async () => {
    describe_
      .mockResolvedValueOnce({ ok: true, data: noteOnly(SESSION) })
      .mockResolvedValueOnce({ ok: true, data: noteOnly(SESSION_2) });
    upload.mockImplementation(async (_s, _f, on) => ready(on));
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(photo());
    await send();
    fireEvent.click(screen.getByRole("button", { name: "Sửa bằng một câu" }));
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gửi" })));
    expect(upload.mock.calls.map((call) => call[0])).toEqual([SESSION, SESSION_2]);
  });

  it("the same file twice is one note", async () => {
    describe_.mockResolvedValue({ ok: true, data: noteOnly() });
    upload.mockImplementation(async (_s, _f, on) => ready(on));
    confirm.mockResolvedValue({ ok: true, data: { session_id: SESSION } });
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(photo("a.jpg"), photo("b.jpg"));
    await send();
    await act(async () => fireEvent.click(lưu()));
    expect(confirm.mock.calls[0][3]).toEqual([NOTE]);
  });

  it("core-api's refusal of a note at Lưu names the file problem, not a generic one", async () => {
    describe_.mockResolvedValue({ ok: true, data: noteOnly() });
    upload.mockImplementation(async (_s, _f, on) => ready(on));
    confirm.mockResolvedValue({ ok: false, code: "upload_incomplete" });
    render(<LogSession subjectId="s1" subjectName="Vật lý" />);
    choose(photo());
    await send();
    await act(async () => fireEvent.click(lưu()));
    expect(screen.getAllByRole("alert").some((a) => a.textContent?.includes("chưa lên đến nơi"))).toBe(true);
  });
});
