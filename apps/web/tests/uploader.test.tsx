// @vitest-environment jsdom
// T4.6 (US-01 AC7): the upload step's rows, with the upload itself faked.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UploadState } from "@/lib/upload-client";

const SUBJECT = "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b";
const upload = vi.fn<(subject: string, file: File, on: (s: UploadState) => void) => Promise<void>>();

vi.mock("@/lib/upload-client", async (original) => ({
  ...(await original<typeof import("@/lib/upload-client")>()),
  uploadPdf: (subject: string, file: File, on: (s: UploadState) => void) => upload(subject, file, on),
}));

const { Uploader } = await import("@/components/subjects/uploader");

afterEach(() => {
  cleanup();
  upload.mockReset();
});

const input = () => document.querySelector('input[type="file"]') as HTMLInputElement;
const choose = (...files: File[]) => fireEvent.change(input(), { target: { files } });

describe("Uploader (US-01 AC7)", () => {
  // Red when: a PNG or an oversized file is sent, or its refusal is not shown at the row.
  it("refuses a non-PDF without calling the upload, and says so", async () => {
    render(<Uploader subjectId={SUBJECT} />);
    await act(async () => choose(new File(["x"], "vo.png", { type: "image/png" })));
    expect(upload).not.toHaveBeenCalled();
    expect(screen.getByText("vo.png")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toBe("Chỉ nhận file PDF.");
  });

  it("shows progress and then \"Đang đọc tài liệu…\"", async () => {
    let on: (s: UploadState) => void = () => {};
    let finish: () => void = () => {};
    upload.mockImplementation((_s, _f, cb) => {
      on = cb;
      return new Promise<void>((resolve) => (finish = resolve));
    });
    render(<Uploader subjectId={SUBJECT} />);
    await act(async () => choose(new File(["%PDF"], "Slide MMT.pdf", { type: "application/pdf" })));
    expect(upload).toHaveBeenCalledWith(SUBJECT, expect.any(File), expect.any(Function));
    act(() => on({ kind: "uploading", percent: 64 }));
    expect(screen.getByText("đang tải 64%")).toBeTruthy();
    expect((screen.getByRole("progressbar") as HTMLProgressElement).value).toBe(64);
    act(() => on({ kind: "done" }));
    finish();
    expect(screen.getByText("Đang đọc tài liệu…")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  // Red when: the quota's refusal reaches the user as a generic failure.
  it("shows the quota refusal by its code", async () => {
    upload.mockImplementation(async (_s, _f, cb) => cb({ kind: "failed", code: "storage_quota_exceeded" }));
    render(<Uploader subjectId={SUBJECT} />);
    await act(async () => choose(new File(["%PDF"], "a.pdf", { type: "application/pdf" })));
    expect(screen.getByRole("alert").textContent).toContain("1 GB");
  });

  // Red when: one file that throws stops the files after it.
  it("a thrown upload fails its row and the next file still goes", async () => {
    upload.mockRejectedValueOnce(new Error("boom"));
    upload.mockImplementationOnce(async (_s, _f, cb) => cb({ kind: "done" }));
    render(<Uploader subjectId={SUBJECT} />);
    await act(async () =>
      choose(
        new File(["%PDF"], "a.pdf", { type: "application/pdf" }),
        new File(["%PDF"], "b.pdf", { type: "application/pdf" }),
      ),
    );
    expect(upload).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("alert").textContent).toContain("Chưa tải được");
    expect(screen.getByText("Đang đọc tài liệu…")).toBeTruthy();
  });

  // Red when: the row stays on "Đang đọc tài liệu…" after the document is indexed (REALFIX 1).
  it("flips from reading to read once the document is indexed", async () => {
    vi.useFakeTimers();
    try {
      let status = "uploaded";
      const fetchMock = vi.fn(async () => new Response(JSON.stringify({ status }), { status: 200 }));
      vi.stubGlobal("fetch", fetchMock);
      upload.mockImplementation(async (_s, _f, cb) => cb({ kind: "done", documentId: "d1" }));
      render(<Uploader subjectId={SUBJECT} />);
      await act(async () => choose(new File(["%PDF"], "a.pdf", { type: "application/pdf" })));
      expect(screen.getByText("Đang đọc tài liệu…")).toBeTruthy();
      await act(async () => void (await vi.advanceTimersByTimeAsync(3100)));
      expect(screen.getByText("Đang đọc tài liệu…")).toBeTruthy();
      status = "indexed";
      await act(async () => void (await vi.advanceTimersByTimeAsync(3100)));
      expect(screen.getByText("Đã đọc xong")).toBeTruthy();
    } finally {
      vi.useRealTimers();
      vi.unstubAllGlobals();
    }
  });

  // Red when: a file put in the "Giáo trình chính" tab stays an auxiliary document, so the Đề cương
  // page says "Chưa có đề cương" while stats already count its sections. The role is sent right after
  // the confirm, before any polling, so leaving the screen early loses nothing.
  it.each([
    ["main", "textbook"],
    ["bank", "question_bank"],
  ] as const)("a file of the %s tab gets the %s role as soon as it is stored", async (tab, role) => {
    const patches: unknown[] = [];
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") patches.push([url, JSON.parse(String(init.body))]);
      return new Response("{}", { status: 200 });
    });
    vi.stubGlobal("fetch", fetchMock);
    try {
      upload.mockImplementation(async (_s, _f, cb) => cb({ kind: "done", documentId: "d1" }));
      const view = render(<Uploader subjectId={SUBJECT} fixedRole={tab} />);
      await act(async () => choose(new File(["%PDF"], "a.pdf", { type: "application/pdf" })));
      view.unmount(); // the learner leaves before any poll
      expect(patches).toEqual([["/api/documents/d1", { role }]]);
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("says so when the subject already has a main textbook (409 textbook_exists)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ error: "textbook_exists" }), { status: 409 })),
    );
    try {
      upload.mockImplementation(async (_s, _f, cb) => cb({ kind: "done", documentId: "d1" }));
      render(<Uploader subjectId={SUBJECT} fixedRole="main" />);
      await act(async () => choose(new File(["%PDF"], "a.pdf", { type: "application/pdf" })));
      expect(screen.getByRole("alert").textContent).toContain("đã có giáo trình chính");
      expect(screen.queryByText("#giáo trình chính")).toBeNull();
    } finally {
      vi.unstubAllGlobals();
    }
  });

  it("a file of the supplementary tab is not patched", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(async () => new Response("{}", { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    try {
      upload.mockImplementation(async (_s, _f, cb) => cb({ kind: "done", documentId: "d1" }));
      render(<Uploader subjectId={SUBJECT} fixedRole="supplementary" />);
      await act(async () => choose(new File(["%PDF"], "a.pdf", { type: "application/pdf" })));
      expect(fetchMock.mock.calls.every(([, init]) => init?.method !== "PATCH")).toBe(true);
    } finally {
      vi.unstubAllGlobals();
    }
  });
});
