// @vitest-environment jsdom
// T7.13 (US-15 AC6, AC7, US-03 AC7): the subject block with the endpoint behind its button, the
// error path, "Ôn riêng môn này", and the preview that never calls the API.
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const go = vi.fn();
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { SubjectSuggestion } = await import("@/components/subjects/subject-suggestion");
const ID = "0b8f1d2e-0000-4000-8000-000000000001";
const NEXT = {
  label: "3.2",
  title: "TCP flow control",
  pages: null,
  reason: "Mục chưa học đầu tiên trong đề cương.",
  pace: { sections_left: 3, pages_left: null, days_left: 5, text: "còn 3 mục, 5 ngày" },
};

function show(props: Partial<React.ComponentProps<typeof SubjectSuggestion>> = {}) {
  render(<SubjectSuggestion subjectId={ID} subjectName="Mạng" state={{ kind: "not_suggested" }} {...props} />);
}

describe("subject block (T7.13)", () => {
  beforeEach(() => go.mockReset());
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  // Red when: a failed answer leaves the button on "Đang tính…" or hides the error.
  it("US-15 AC6: a failing endpoint ends in a message and the button is back", async () => {
    const resolve = vi.fn(async () => {
      throw new Error("suggestion 500");
    });
    show({ resolve });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gợi ý cho hôm nay" })));
    expect(screen.getByRole("alert").textContent).toContain("Chưa tính được gợi ý");
    expect(screen.getByRole("button", { name: "Gợi ý cho hôm nay" })).toBeTruthy();
    expect(screen.queryByText("Đang tính…")).toBeNull();
  });

  // Red when: the answer is not shown in the shape of a suggestion that was there already.
  it("US-15 AC6: the answer shows the section and no reason is asked", async () => {
    show({ resolve: async () => ({ kind: "suggested", next: NEXT }) });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gợi ý cho hôm nay" })));
    expect(screen.getByText("Hôm nay nên học: mục 3.2")).toBeTruthy();
    expect(screen.queryByText(/không phải ngày/i)).toBeNull();
  });

  // Red when: a finished answer to the button still shows the button.
  it("US-15 AC7: the answer can be finished", async () => {
    show({ resolve: async () => ({ kind: "finished" }) });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Gợi ý cho hôm nay" })));
    expect(screen.getByText(/học hết đề cương/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Gợi ý cho hôm nay" })).toBeNull();
  });

  // Red when: "Ôn riêng môn này" does not ask for this subject's session, or goes to a made-up route.
  it("US-03 AC7: Ôn riêng môn này opens this subject's review session", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ id: "6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e" })));
    show();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Ôn riêng môn này" })));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/review-sessions");
    expect(JSON.parse(String((init as RequestInit).body))).toEqual({ subject_id: ID });
    expect(go).toHaveBeenCalledWith("/review/6b1c2d3e-4f5a-4b6c-8d7e-9f0a1b2c3d4e");
  });

  // Red when: the design preview's start button reaches the real API.
  it("a preview start button never calls the API", async () => {
    const spy = vi.fn();
    vi.stubGlobal("fetch", spy);
    show({ preview: true });
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Ôn riêng môn này" })));
    expect(spy).not.toHaveBeenCalled();
    expect(go).not.toHaveBeenCalled();
  });

  // Red when: the Luyện tập link points at a page that does not exist yet.
  it("US-03 AC7: no Luyện tập link when the practice screen is off", () => {
    show({ state: { kind: "finished" }, practiceLink: false });
    expect(screen.queryByRole("button", { name: "Luyện tập" })).toBeNull();
    cleanup();
    show({ state: { kind: "finished" } });
    expect(screen.getByRole("button", { name: "Luyện tập" })).toBeTruthy();
  });
});
