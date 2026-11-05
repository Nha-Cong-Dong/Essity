// @vitest-environment jsdom
// QA 05/11 (WCAG 2.1.1): the outline list on the subject page scrolls, so the keyboard must reach it.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { SubjectOutlineAside } from "@/components/subjects/subject-chapters-aside";
import type { SyllabusNode } from "@/lib/syllabus/tree";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

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

// Red when: the scrolling outline list is not focusable (axe: scrollable-region-focusable), or a
// list that fits becomes a pointless tab stop (UI-D).
function withHeights(scroll: number, client: number) {
  vi.spyOn(HTMLElement.prototype, "scrollHeight", "get").mockReturnValue(scroll);
  vi.spyOn(HTMLElement.prototype, "clientHeight", "get").mockReturnValue(client);
}

it("the scrolling outline list is focusable and named", () => {
  withHeights(400, 200);
  render(<SubjectOutlineAside nodes={[leaf]} subjectId="s1" />);
  const list = screen.getByRole("list", { name: "Các phần của đề cương" });
  expect(list.getAttribute("tabindex")).toBe("0");
});

it("a list that fits is not a tab stop", () => {
  withHeights(100, 100);
  render(<SubjectOutlineAside nodes={[leaf]} subjectId="s1" />);
  const list = screen.getByRole("list", { name: "Các phần của đề cương" });
  expect(list.hasAttribute("tabindex")).toBe(false);
});
