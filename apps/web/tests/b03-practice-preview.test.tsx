// @vitest-environment jsdom
// DEMO-FIX B-03: a practice question's text shows at once from the step already fetched, while the
// attempt is still opening (core-api may draft the reference answer first: 2-5 s). Red when: the
// loading phase is an empty frame again, or the answer box shows before the attempt exists.
import { act, cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PracticeAnswer } from "@/components/practice/practice-answer";
import type { PracticeApi } from "@/lib/practice-client";

afterEach(cleanup);

describe("PracticeAnswer preview (B-03)", () => {
  it("shows the prompt while open() is pending, without an answer box", async () => {
    const api = {
      open: vi.fn(() => new Promise(() => undefined)),
      saveDraft: vi.fn(),
      read: vi.fn(),
    } as unknown as PracticeApi;
    await act(async () => {
      render(<PracticeAnswer questionId="q1" api={api} promptPreview="So sánh TCP và UDP." onNext={() => undefined} />);
    });
    expect(screen.getByRole("heading", { name: "So sánh TCP và UDP." })).toBeTruthy();
    expect(screen.queryByRole("textbox")).toBeNull();
    expect(screen.getByRole("status").textContent).toContain("Đang tải");
  });
});
