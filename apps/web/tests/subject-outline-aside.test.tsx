// @vitest-environment jsdom
// QA 05/11 (WCAG 2.1.1): the outline list on the subject page scrolls, so the keyboard must reach it.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { SubjectOutlineAside } from "@/components/subjects/subject-chapters-aside";
import type { SyllabusNode } from "@/lib/syllabus/tree";

afterEach(cleanup);

const leaf: SyllabusNode = {
  id: "a",
  title: "1.1 Quy tắc cộng",
  from: 1,
  to: 2,
  weight: 2,
  excluded: false,
  done: false,
  part: null,
  byHand: false,
  edited: false,
  children: [],
} as SyllabusNode;

// Red when: the scrolling outline list is not focusable (axe: scrollable-region-focusable).
it("the scrolling outline list is focusable and named", () => {
  render(<SubjectOutlineAside nodes={[leaf]} subjectId="s1" />);
  const list = screen.getByRole("list", { name: "Các phần của đề cương" });
  expect(list.getAttribute("tabindex")).toBe("0");
});
