// @vitest-environment jsdom
// PRACTICE-PREREQ: the "Kiến thức nền" box of an unlocked question: one chip per card, a chip
// opens the card in a drawer (title, text, "Mở trong Kho"), Esc and X close it, no cards no box.
// Red when: the box shows with no cards, a chip does not open the drawer, or Esc does not close it.
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PracticeAnswer } from "@/components/practice/practice-answer";
import { PrereqBox } from "@/components/practice/prereq-box";
import type { PracticeApi } from "@/lib/practice-client";

vi.mock("@/components/markdown/markdown", () => ({ Markdown: ({ text }: { text: string }) => <div>{text}</div> }));

afterEach(cleanup);

const cards = [
  { id: "c1", title: "Ba bước bắt tay TCP", summary: "SYN, SYN-ACK, ACK." },
  { id: "c2", title: "UDP không kết nối", summary: "Không đảm bảo thứ tự." },
];

describe("PrereqBox", () => {
  it("renders nothing without cards", () => {
    const { container } = render(<PrereqBox cards={[]} />);
    expect(container.querySelector("[data-prereq-box]")).toBeNull();
  });

  it("shows a titled box with one chip per card", () => {
    render(<PrereqBox cards={cards} />);
    const box = screen.getByRole("region", { name: "Kiến thức nền" });
    expect(within(box).getAllByRole("button").map((b) => b.textContent)).toEqual(cards.map((c) => c.title));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("a chip opens the drawer with the card text and a vault link; Esc closes it", async () => {
    render(<PrereqBox cards={cards} vaultHref="/kho-kien-thuc?subject=s1" />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "UDP không kết nối" })));
    const drawer = await screen.findByRole("dialog", { name: "UDP không kết nối" });
    expect(within(drawer).getByText("Không đảm bảo thứ tự.")).toBeTruthy();
    expect(within(drawer).getByRole("link", { name: "Mở trong Kho" }).getAttribute("href")).toBe("/kho-kien-thuc?subject=s1");
    await act(async () => fireEvent.keyDown(drawer, { key: "Escape" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("the X button closes the drawer", async () => {
    render(<PrereqBox cards={cards} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Ba bước bắt tay TCP" })));
    const drawer = await screen.findByRole("dialog");
    await act(async () => fireEvent.click(within(drawer).getByRole("button", { name: "Đóng" })));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("PracticeAnswer with prerequisites", () => {
  const api = {
    open: vi.fn(async () => ({
      ok: true,
      data: {
        attempt_id: "a1", status: "draft", answer_text: "", dont_remember: false, failure: null, grading: null,
        question: { id: "q1", prompt: "So sánh TCP và UDP." }, result: null, submitted_at: null, timing_ok: null,
      },
    })),
    saveDraft: vi.fn(),
    read: vi.fn(),
  } as unknown as PracticeApi;

  it("draws the box under the question when cards are given, and hides it otherwise", async () => {
    await act(async () => {
      render(<PracticeAnswer questionId="q1" api={api} prerequisites={cards} onNext={() => undefined} />);
    });
    expect(await screen.findByRole("region", { name: "Kiến thức nền" })).toBeTruthy();
    cleanup();
    await act(async () => {
      render(<PracticeAnswer questionId="q1" api={api} onNext={() => undefined} />);
    });
    expect(screen.queryByRole("region", { name: "Kiến thức nền" })).toBeNull();
  });
});
