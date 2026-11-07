// @vitest-environment jsdom
// SCREENS-V4-B (mockups subject-detail.html): the empty "Ôn tập hôm nay" is a number block plus an outlined CTA.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { ReviewStack } from "@/components/subjects/review-stack";

afterEach(cleanup);

// Red when: the empty review is only a sentence with a face, no number and no way on.
it("empty review shows 0 thẻ đến hạn, the sentence and a link to the Kho", () => {
  render(<ReviewStack subjectId="s1" cards={[]} />);
  expect(screen.getByText("thẻ đến hạn")).toBeTruthy();
  expect(screen.getByText("Tuyệt vời, không có kiến thức nào cần ôn hôm nay")).toBeTruthy();
  expect(screen.getByText("Mở Kho").closest("a")?.getAttribute("href")).toBe("/kho-kien-thuc");
});
