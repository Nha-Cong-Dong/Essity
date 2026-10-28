// @vitest-environment jsdom
// T5.4 (US-07 AC1, AC3): the reason under the question, written from the server's data.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { QuestionReason, type Reason } from "@/components/question-reason";

afterEach(cleanup);

// DESIGN.md §4, the words the interface never uses.
const FORBIDDEN = /lại quên|lười|bỏ lỡ|thất bại|kém|chuỗi|streak|tụt|đáng lẽ/i;

const CASES: [string, Reason, RegExp][] = [
  ["review", { kind: "review", retrievability: 0.7, days_since_last: 6 }, /còn nhớ khoảng 70%.*cách đây 6 ngày/],
  ["same day", { kind: "review", retrievability: 0.93, days_since_last: 0 }, /khoảng 93%.*hôm nay/],
  ["new", { kind: "new", retrievability: null, days_since_last: null }, /Câu mới, bạn chưa ôn lần nào/],
];

describe("QuestionReason", () => {
  // US-07 AC1. Red when: a kind of question has no reason, or it is not closed until opened.
  it.each(CASES)("AC1: a %s question has a reason, closed at first", (_name, reason, text) => {
    const { container } = render(<QuestionReason reason={reason} />);
    expect(screen.getByText("Vì sao câu này?")).toBeTruthy();
    const details = container.querySelector("details");
    expect(details?.open).toBe(false);
    expect(details?.textContent).toMatch(text);
  });

  // US-07 AC3. Red when: a sentence uses a word from the forbidden list.
  it.each(CASES)("AC3: the %s sentence has no forbidden word", (_name, reason) => {
    const { container } = render(<QuestionReason reason={reason} />);
    expect(container.textContent).not.toMatch(FORBIDDEN);
  });
});
