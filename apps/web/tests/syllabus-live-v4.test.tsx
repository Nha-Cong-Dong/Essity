// @vitest-environment jsdom
// C2-SYLLABUS-V4: SyllabusLive (the real screen) is built from the v4 blocks. Behaviour is in syllabus-live.test.tsx.
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SyllabusLive } from "@/components/syllabus/syllabus-live";
import type { OutlineOut } from "@/lib/syllabus/api";

afterEach(cleanup);

const SUBJECT = "9e4f5a6b-7c8d-4e9f-8a1b-2c3d4e5f6a7b";
type Section = OutlineOut["sections"][number];
const sec = (id: string, over: Partial<Section> = {}): Section => ({
  id, parent_id: null, title: `${id} Phần`, first_page: 1, last_page: 10, weight: 10, unit: "page", source: "bookmark",
  excluded: false, excluded_effective: false, progress: 0, studied: false, learned: false, children: [], ...over,
});
const outline = (sections: Section[], over: Partial<OutlineOut> = {}): OutlineOut => ({
  subject_id: SUBJECT, document: { id: "c3d4e5f6-7a8b-4c9d-8e1f-2a3b4c5d6e7f", page_count: 100, short_name: "GT" }, progress: 0,
  reason: null, temporary: false, remaining_chapters: 0, sections, ...over,
});

describe("SyllabusLive on v4 blocks", () => {
  it("ready: back arrow link, one plum field with the totals, tree in a white sheet", () => {
    const { container } = render(<SyllabusLive subjectId={SUBJECT} subjectName="Mạng" initial={outline([sec("1")])} />);
    expect(container.querySelector("a[href='/subjects/" + SUBJECT + "'] svg")).not.toBeNull();
    expect(container.querySelectorAll("[data-tier='field']")).toHaveLength(1);
    expect(container.querySelector("[data-tier='field'] [data-totals]")).not.toBeNull();
    expect(container.querySelector("[data-nx][data-tier='sheet'] [role=tree]")).not.toBeNull();
  });

  it("provisional: the notice is a tint block", () => {
    const { container } = render(
      <SyllabusLive subjectId={SUBJECT} subjectName="Mạng" initial={outline([sec("1", { source: "chunk10" })], { temporary: true })} />,
    );
    expect(container.querySelector("[data-tier='tint'][data-notice='chunk10']")).not.toBeNull();
  });

  it.each([
    ["no_textbook", { document: null, reason: "no_textbook" as const }],
    ["not_extractable", { reason: "not_extractable" as never }],
  ])("%s: a sheet with the mascot empty state, no plum field", (_n, over) => {
    const { container } = render(<SyllabusLive subjectId={SUBJECT} subjectName="Mạng" initial={outline([], over)} />);
    expect(container.querySelector("[data-tier='sheet'] [data-slot='empty-state']")).not.toBeNull();
    expect(container.querySelector("[data-tier='field']")).toBeNull();
  });
});
