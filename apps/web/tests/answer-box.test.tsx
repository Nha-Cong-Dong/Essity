// @vitest-environment jsdom
// T2.15 (US-04, DESIGN.md §3.4, §6.4): the ruled answer box. Sending empty is stopped here
// (US-04 AC4); "Không nhớ" is one tap (AC2); the save line never shows an error (AC3).
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AnswerBox, type AnswerBoxProps } from "@/components/review/answer-box";
import { ANSWER_MAX } from "@/lib/review-client";

afterEach(cleanup);

function box(props: Partial<AnswerBoxProps> = {}) {
  const all: AnswerBoxProps = {
    id: "answer",
    value: "",
    onChange: vi.fn(),
    onSubmit: vi.fn(),
    onForgot: vi.fn(),
    save: { state: "idle", at: null },
    pending: null,
    ...props,
  };
  render(<AnswerBox {...all} />);
  return all;
}

describe("AnswerBox (T2.15)", () => {
  // Red when: an empty answer reaches the API, or the user is not pointed at "Không nhớ".
  it("US-04 AC4: Gửi with nothing written sends nothing and says to use Không nhớ", () => {
    const props = box({ value: "   \n " });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(props.onSubmit).not.toHaveBeenCalled();
    const field = screen.getByLabelText("Câu trả lời của bạn");
    expect(field.getAttribute("aria-invalid")).toBe("true");
    const hint = screen.getByText("Ô trả lời đang trống. Nếu không nhớ, chọn Không nhớ.");
    expect(field.getAttribute("aria-describedby")).toContain(hint.closest("[id]")?.id);
  });

  it("Gửi sends what is written", () => {
    const props = box({ value: "TCP bắt tay ba bước" });
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(props.onSubmit).toHaveBeenCalledOnce();
  });

  // Red when: the shortcut DESIGN.md §6.4 promises does nothing, or Enter alone sends.
  it("Ctrl+Enter and Cmd+Enter send; Enter alone is a new line", () => {
    const props = box({ value: "TCP" });
    const field = screen.getByLabelText("Câu trả lời của bạn");
    fireEvent.keyDown(field, { key: "Enter" });
    expect(props.onSubmit).not.toHaveBeenCalled();
    fireEvent.keyDown(field, { key: "Enter", ctrlKey: true });
    fireEvent.keyDown(field, { key: "Enter", metaKey: true });
    expect(props.onSubmit).toHaveBeenCalledTimes(2);
  });

  it("US-04 AC2: Không nhớ is one tap, even with nothing written", () => {
    const props = box();
    fireEvent.click(screen.getByRole("button", { name: "Không nhớ" }));
    expect(props.onForgot).toHaveBeenCalledOnce();
  });

  it("typing goes up to the screen", () => {
    const props = box();
    fireEvent.change(screen.getByLabelText("Câu trả lời của bạn"), { target: { value: "a" } });
    expect(props.onChange).toHaveBeenCalledWith("a");
  });

  // Plan 🟡15, 🟢18: ai-service takes 4000 characters. Red when: an old, longer draft is sent
  // and refused forever, or the box lets more be typed.
  it("an answer over 4000 characters is counted, flagged and not sent", () => {
    const props = box({ value: "a".repeat(ANSWER_MAX + 1) });
    const field = screen.getByLabelText("Câu trả lời của bạn");
    expect(field.getAttribute("maxlength")).toBe(String(ANSWER_MAX));
    expect(screen.getByText(/4\.001\s*\/\s*4\.000/)).toBeTruthy();
    expect(field.getAttribute("aria-invalid")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Gửi" }));
    expect(props.onSubmit).not.toHaveBeenCalled();
  });

  it("the counter stays hidden for a short answer", () => {
    box({ value: "ngắn" });
    expect(screen.queryByText(/\/\s*4\.000/)).toBeNull();
  });

  // US-04 AC3, DESIGN.md §6.4: saving, saved at a time, kept on this device; never an error.
  it.each([
    ["saving", null, "Đang lưu…"],
    ["saved", new Date(2026, 9, 26, 21, 42).getTime(), "Đã lưu nháp lúc 21:42"],
    ["local", null, "Đã lưu trên máy này, sẽ đồng bộ khi có mạng"],
  ] as const)("the save line says %s", (state, at, text) => {
    box({ value: "x", save: { state, at } });
    expect(screen.getByText(text)).toBeTruthy();
  });

  it("while sending, the buttons wait and nothing can be sent twice", () => {
    const props = box({ value: "x", pending: "submit" });
    const send = screen.getByRole("button", { name: "Gửi" });
    expect(send.getAttribute("aria-busy")).toBe("true");
    fireEvent.click(send);
    fireEvent.keyDown(screen.getByLabelText("Câu trả lời của bạn"), { key: "Enter", ctrlKey: true });
    fireEvent.click(screen.getByRole("button", { name: "Không nhớ" }));
    expect(props.onSubmit).not.toHaveBeenCalled();
    expect(props.onForgot).not.toHaveBeenCalled();
  });

  it("the box takes focus when the question shows (DESIGN.md §6.4)", () => {
    box();
    expect(document.activeElement).toBe(screen.getByLabelText("Câu trả lời của bạn"));
  });
});
