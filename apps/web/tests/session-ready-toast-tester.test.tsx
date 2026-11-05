// @vitest-environment jsdom
// FIX-CHUNK tester edges: the failed toast must not swallow the "done, no cards" case, and two
// waiting sessions (one failed, one done) each get their own toast.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionReadyToast } from "@/components/session-study/session-ready-toast";
import { readPendingSessions, rememberPendingSession } from "@/lib/session-study/pending";

const A = { sessionId: "s-a", subjectId: "subj-a", subject: "Giải tích" };
const B = { sessionId: "s-b", subjectId: "subj-b", subject: "Hóa sinh" };

function answers(bySession: Record<string, unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const id = Object.keys(bySession).find((key) => url.includes(`/api/sessions/${key}/`));
      return new Response(JSON.stringify(id ? bySession[id] : {}), { status: 200 });
    }),
  );
}

beforeEach(() => {
  window.localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SessionReadyToast, FIX-CHUNK tester edges", () => {
  // Red when: a session that finished with zero cards is told it failed (cards 0 read as null),
  // or loses its link to the syllabus.
  it("done with zero cards is not reported as a failure", async () => {
    rememberPendingSession(A);
    answers({ "s-a": { submission_status: "done", cards: 0 } });
    render(<SessionReadyToast />);
    const link = await screen.findByRole("link", { name: /Chưa tìm thấy nội dung để làm thẻ/ });
    expect(link.getAttribute("href")).toBe("/subjects/subj-a/syllabus");
    expect(screen.queryByText(/Chưa tạo được thẻ/)).toBeNull();
  });

  // Red when: one failed session hides or replaces the toast of another session that is done,
  // or the failed one stays in the waiting list (asked again forever).
  it("a failed and a done session each get their own toast", async () => {
    rememberPendingSession(A);
    rememberPendingSession(B);
    answers({
      "s-a": { submission_status: "failed", cards: 0 },
      "s-b": { submission_status: "done", cards: 2 },
    });
    render(<SessionReadyToast />);
    const failed = await screen.findByRole("link", { name: /Chưa tạo được thẻ cho buổi học môn Giải tích/ });
    expect(failed.getAttribute("href")).toBe("/subjects/subj-a");
    const done = await screen.findByRole("link", { name: /Đã thêm 2 thẻ vào Kho cho buổi học môn Hóa sinh/ });
    // FIX-CHUNK live check: /kho-kien-thuc/<id> is a 404; the Kho takes ?subject= and ?session=.
    expect(done.getAttribute("href")).toBe("/kho-kien-thuc?subject=subj-b&session=s-b");
    expect(readPendingSessions()).toEqual([]);
  });

  // Red when: a session still being read is shown as failed, or dropped from the waiting list.
  it("a session still processing shows nothing and keeps waiting", async () => {
    rememberPendingSession(A);
    answers({ "s-a": { submission_status: "processing", cards: 0 } });
    render(<SessionReadyToast />);
    await vi.waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());
    await new Promise((resolve) => setTimeout(resolve, 50)); // let the answer be read
    expect(screen.queryByRole("link")).toBeNull();
    expect(readPendingSessions().map((s) => s.sessionId)).toEqual(["s-a"]);
  });
});
