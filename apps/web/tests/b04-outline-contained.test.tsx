// @vitest-environment jsdom
// DEMO-FIX B-04: the outline list scrolls inside its card. Its rows hold `sr-only` spans (position:
// absolute); without a positioned scroller they escape its clip and stretch the document (4939 px
// for a 1300 px page). Red when: the scrolling list is not `relative`.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SubjectOutlineAside } from "@/components/subjects/subject-chapters-aside";
import type { SyllabusNode } from "@/lib/syllabus/tree";

afterEach(cleanup);

describe("SubjectOutlineAside (B-04)", () => {
  it("the scrolling list is the containing block of its sr-only spans", () => {
    const nodes = [{ id: "a", title: "A", done: false, excluded: false, children: [] }] as unknown as SyllabusNode[];
    const { container } = render(<SubjectOutlineAside nodes={nodes} subjectId="s1" />);
    const ul = container.querySelector("ul[aria-label='Các phần của đề cương']") as HTMLElement;
    expect(ul.className).toMatch(/overflow-y-auto/);
    expect(ul.classList.contains("relative")).toBe(true);
  });
});
