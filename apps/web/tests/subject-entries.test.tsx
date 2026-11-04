// T7.13b (DESIGN §6.5 items 4-5; US-13): the subject screen's entry row and the textbook link.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DocumentList } from "@/components/documents/document-list";
import { SubjectEntryRow } from "@/components/subjects/subject-entry-row";
import { entryRow } from "@/lib/subject-entries";
import type { OutlineOut } from "@/lib/syllabus/api";

const ID = "0b8f1d2e-0000-4000-8000-000000000001";
type Section = OutlineOut["sections"][number];
const leaf = (id: string, studied: boolean): Section => ({
  id, parent_id: null, title: id, first_page: 1, last_page: 10, weight: 10, unit: "page", source: "bookmark",
  excluded: false, excluded_effective: false, progress: studied ? 1 : 0, studied, learned: studied, children: [],
});
const outline = (sections: Section[], over: Partial<OutlineOut> = {}): OutlineOut => ({
  subject_id: ID, document: { id: "d", page_count: 30, short_name: "Giáo trình" }, progress: 0, reason: null,
  temporary: false, remaining_chapters: 0, sections, ...over,
});
const keys = (e: ReturnType<typeof entryRow>) => e.map((x) => x.key);

describe("entryRow", () => {
  // Red when: the entry is missing, or counts something other than studied/total sections.
  it("US-13: Đề cương shows 'đã học x/y phần' with a link to the outline", () => {
    const e = entryRow(ID, { outline: outline([leaf("1", true), leaf("2", false), leaf("3", false)]), questions: null, graphCards: null });
    expect(e[0]).toEqual({ key: "syllabus", label: "Đề cương", href: `/subjects/${ID}/syllabus`, note: "đã học 1/3 phần" });
  });

  // Red when: an entry whose screen has nothing to show (no textbook, no questions, no cards) is drawn.
  it("DESIGN §6.5: entries without data are left out; Thống kê stays, without a number", () => {
    const none = outline([], { document: null, reason: "no_textbook" });
    const e = entryRow(ID, { outline: none, questions: { ready: 0, total: 0 }, graphCards: 0 });
    expect(keys(e)).toEqual(["stats", "graph"]);
    expect(e[0]).toMatchObject({ href: `/stats?subject=${ID}`, note: null });
    expect(e[1]).toMatchObject({ key: "graph", note: "chưa có thẻ" });
  });

  // Red when: a failed read (null) breaks the row or shows a made-up number.
  it("a source that failed to load drops only its entry", () => {
    expect(keys(entryRow(ID, { outline: null, questions: null, graphCards: null }))).toEqual(["stats", "graph"]);
  });

  // Red when: the count or the links of Luyện tập / Đồ thị are wrong.
  it("Luyện tập shows the ready count; Đồ thị links to the graph", () => {
    const e = entryRow(ID, { outline: null, questions: { ready: 5, total: 9 }, graphCards: 12 });
    expect(keys(e)).toEqual(["practice", "stats", "graph"]);
    expect(e[0]).toMatchObject({ href: `/subjects/${ID}/practice`, note: "5 câu sẵn sàng" });
    expect(e[2]).toMatchObject({ href: `/subjects/${ID}/graph` });
  });
});

describe("SubjectEntryRow", () => {
  it("renders one link per entry with its number", () => {
    const html = renderToStaticMarkup(
      <SubjectEntryRow entries={entryRow(ID, { outline: outline([leaf("1", true)]), questions: { ready: 2, total: 2 }, graphCards: 1 })} />,
    );
    expect(html).toContain("đã học 1/1 phần");
    expect(html).toContain("2 câu sẵn sàng");
    expect((html.match(/<a /g) ?? []).length).toBe(4);
  });
  it("renders nothing for an empty row", () => {
    expect(renderToStaticMarkup(<SubjectEntryRow entries={[]} />)).toBe("");
  });
});

describe("DocumentList textbook link (DESIGN §6.5 item 5)", () => {
  const doc = (id: string, role: string, status = "indexed") => ({
    id, short_name: id, status, page_count: 10, unreadable_pages: [], failure_reason: null, role,
  });
  // Red when: the main textbook opens its toc page instead of Đề cương, or another file opens Đề cương.
  it("the textbook's name opens Đề cương; other files keep their toc page", () => {
    const html = renderToStaticMarkup(<DocumentList subjectId={ID} docs={[doc("GT", "textbook"), doc("Slide", "auxiliary")]} />);
    expect(html).toContain(`href="/subjects/${ID}/syllabus"`);
    expect(html).toContain(`href="/subjects/${ID}/documents/Slide"`);
    expect(html).not.toContain(`/documents/GT"`);
  });
  it("a textbook not indexed yet is not a link", () => {
    const html = renderToStaticMarkup(<DocumentList subjectId={ID} docs={[doc("GT", "textbook", "pending")]} />);
    expect(html).not.toContain("/syllabus");
  });
});
