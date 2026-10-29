// @vitest-environment jsdom
// T4.13a (US-02 AC1, AC4, AC5, AC11): the "Ghi buổi học" page, with the two calls faked.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Card, CallResult, ConfirmRange } from "@/lib/log-session";

const SESSION = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const DOC = "5a0b1c2d-3e4f-4a5b-8c6d-7e8f9a0b1c2d";
const describe_ =
  vi.fn<(subject: string, text: string) => Promise<CallResult<Card>>>();
const confirm =
  vi.fn<
    (
      id: string,
      ranges: ConfirmRange[],
      on?: string | null,
    ) => Promise<CallResult<{ session_id: string }>>
  >();
const go = vi.fn();

vi.mock("@/lib/log-session", async (original) => ({
  ...(await original<typeof import("@/lib/log-session")>()),
  describeSession: (s: string, t: string) => describe_(s, t),
  confirmSession: (id: string, r: ConfirmRange[], on?: string | null) =>
    confirm(id, r, on),
}));
vi.mock("@/lib/navigate", () => ({ go: (path: string) => go(path) }));

const { LogSession } = await import("@/components/log-session");

afterEach(() => {
  cleanup();
  describe_.mockReset();
  confirm.mockReset();
  go.mockReset();
});

const DOCS = [{ document_id: DOC, short_name: "giáo trình", page_count: 120 }];
const card = (over: Partial<Card>): Card =>
  ({
    session_id: SESSION,
    card: "confirm",
    studied_on: null,
    question: null,
    candidate_document_ids: [],
    documents: DOCS,
    ranges: [],
    ...over,
  }) as Card;
const RANGE = {
  document_id: DOC,
  short_name: "giáo trình",
  start_page: 43,
  end_page: 58,
  depth: "deep",
  sections: ["Tán xạ"],
  start_label: null,
  end_label: null,
};

async function tell(text = "học tiếp giáo trình") {
  render(<LogSession subjectId="s1" subjectName="Vật lý" />);
  fireEvent.change(screen.getByLabelText("Kể lại buổi học"), {
    target: { value: text },
  });
  await act(async () =>
    fireEvent.click(screen.getByRole("button", { name: "Gửi" })),
  );
}

describe("Ghi buổi học", () => {
  // Red when: an empty sentence reaches core-api.
  it("US-02 AC1: sending nothing calls nothing and says so", async () => {
    await tell("  ");
    expect(describe_).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain("Kể một câu");
  });

  // Red when: one press on Lưu does not save the card as proposed.
  it("US-02 AC4: a right card is one press on Lưu", async () => {
    describe_.mockResolvedValue({
      ok: true,
      data: card({ ranges: [RANGE] as Card["ranges"] }),
    });
    confirm.mockResolvedValue({ ok: true, data: { session_id: SESSION } });
    await tell();
    expect(screen.getByText("tr. 43–58")).toBeTruthy();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Lưu" })),
    );
    expect(confirm).toHaveBeenCalledWith(
      SESSION,
      [{ document_id: DOC, start_page: 43, end_page: 58, depth: "deep" }],
      null,
    );
    expect(screen.getByText(/Đã lưu buổi học/)).toBeTruthy();
  });

  // Red when: the manual form is missing, is not filled in, or the sentence is lost.
  it("US-02 AC4: Chỉnh khoảng trang opens the form filled in; a bad range is refused, a good one saved", async () => {
    describe_.mockResolvedValue({
      ok: true,
      data: card({ ranges: [RANGE] as Card["ranges"] }),
    });
    confirm.mockResolvedValue({ ok: true, data: { session_id: SESSION } });
    await tell("học tiếp giáo trình");
    fireEvent.click(screen.getByRole("button", { name: "Chỉnh khoảng trang" }));
    expect((screen.getByLabelText("Trang từ") as HTMLInputElement).value).toBe(
      "43",
    );
    expect(screen.getByText("học tiếp giáo trình")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Trang đến"), {
      target: { value: "999" },
    });
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Lưu" })),
    );
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain(
      "không có nhiều trang",
    );
    fireEvent.change(screen.getByLabelText("Trang đến"), {
      target: { value: "60" },
    });
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Lưu" })),
    );
    expect(confirm.mock.calls[0][1][0]).toMatchObject({
      start_page: 43,
      end_page: 60,
    });
  });

  // Red when: a card=manual (extraction failed or over budget) leaves the learner without a form.
  it("US-02 AC4, AC11: card manual shows an empty range form", async () => {
    describe_.mockResolvedValue({ ok: true, data: card({ card: "manual" }) });
    await tell();
    expect((screen.getByLabelText("Trang từ") as HTMLInputElement).value).toBe(
      "",
    );
    expect(screen.getByRole("button", { name: "Lưu" })).toBeTruthy();
  });

  // Red when: a clarifying question guesses a record instead of asking.
  it("US-02 AC5: card clarify asks one question and nothing is saved", async () => {
    describe_.mockResolvedValue({
      ok: true,
      data: card({ card: "clarify", question: "Chương 4 của tài liệu nào?" }),
    });
    await tell();
    expect(screen.getByText("Chương 4 của tài liệu nào?")).toBeTruthy();
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "giáo trình" }));
    expect(screen.getByLabelText("Tài liệu")).toBeTruthy();
  });

  // Red when: a failed call drops the sentence the learner wrote.
  it("a failed call keeps the sentence and says so", async () => {
    describe_.mockResolvedValue({ ok: false, code: "unavailable" });
    await tell("câu của tôi");
    expect(
      (screen.getByLabelText("Kể lại buổi học") as HTMLTextAreaElement).value,
    ).toBe("câu của tôi");
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("a signed-out session goes to /login", async () => {
    describe_.mockResolvedValue({ ok: false, code: "signed_out" });
    await tell();
    expect(go).toHaveBeenCalledWith("/login");
  });

  // Red when: a failed save loses the card, so Lưu cannot be pressed again.
  it("a failed save keeps the card and says so", async () => {
    describe_.mockResolvedValue({
      ok: true,
      data: card({ ranges: [RANGE] as Card["ranges"] }),
    });
    confirm.mockResolvedValue({ ok: false, code: "unavailable" });
    await tell();
    await act(async () =>
      fireEvent.click(screen.getByRole("button", { name: "Lưu" })),
    );
    expect(screen.getByRole("alert").textContent).toContain("Chưa lưu được");
    expect(screen.getByRole("button", { name: "Lưu" })).toBeTruthy();
  });
});
