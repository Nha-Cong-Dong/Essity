// @vitest-environment jsdom
// FIX-CHUNK (QA-FINAL 05/11): a session whose cards could not be made was forgotten in silence;
// the learner never learned it failed. Now a toast says so and points back to the subject.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SessionReadyToast } from "@/components/session-study/session-ready-toast";
import { readPendingSessions, rememberPendingSession } from "@/lib/session-study/pending";

const ITEM = { sessionId: "s-1", subjectId: "subj-1", subject: "Xác suất thống kê" };

function answer(body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })),
  );
}

beforeEach(() => {
  window.localStorage.clear();
  rememberPendingSession(ITEM);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SessionReadyToast on a failed session (FIX-CHUNK)", () => {
  // Red when: a failed submission is dropped with no word to the learner.
  it("says the cards could not be made and links to the subject", async () => {
    answer({ submission_status: "failed", cards: 0 });
    render(<SessionReadyToast />);
    const link = await screen.findByRole("link", { name: /Chưa tạo được thẻ cho buổi học môn Xác suất thống kê/ });
    expect(link.getAttribute("href")).toBe("/subjects/subj-1");
    expect(readPendingSessions()).toEqual([]);
  });

  it("still says how many cards went in when the session is done", async () => {
    answer({ submission_status: "done", cards: 3 });
    render(<SessionReadyToast />);
    expect(await screen.findByRole("link", { name: /Đã thêm 3 thẻ vào Kho/ })).toBeTruthy();
  });
});
