// @vitest-environment jsdom
// V19: the practice tile of the subject screen.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { SubjectPracticeBlock } from "@/components/subjects/subject-practice-block";

afterEach(cleanup);
const ID = "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b";

// Red when: the due count or the button to the practice screen is missing.
it("shows the due count and a Luyện tập button to the practice screen", () => {
  const { container } = render(<SubjectPracticeBlock subjectId={ID} total={10} ready={6} dueToday={4} />);
  expect(screen.getByText("4 câu cần luyện hôm nay")).toBeTruthy();
  expect(container.querySelector("a")?.getAttribute("href")).toBe(`/subjects/${ID}/practice`);
});

it("without a bank it leads to the upload", () => {
  const { container } = render(<SubjectPracticeBlock subjectId={ID} total={0} ready={0} dueToday={0} />);
  expect(container.querySelector("a")?.getAttribute("href")).toBe(`/subjects/${ID}/upload`);
});
