// C4 (v4): the document list, the toc and the graph screen use the v4 blocks and no colour literals.
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DocumentList, DocumentsFrame } from "@/components/documents/document-list";
import { TocNotReady, TocTree } from "@/components/documents/toc-view";
import { toTree } from "@/lib/toc";

const SUBJECT = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const doc = { id: "d1", short_name: "Giáo trình", status: "indexed", page_count: 12, unreadable_pages: [], failure_reason: null };

describe("C4 documents v4", () => {
  it("list is one white sheet of whole-row links", () => {
    const out = renderToStaticMarkup(<DocumentList subjectId={SUBJECT} docs={[doc, { ...doc, id: "d2", status: "pending" }]} />);
    expect(out).toContain('data-tier="sheet"');
    expect(out).toContain(`<a href="/subjects/${SUBJECT}/documents/d1"`);
    expect(out).toContain("Giáo trình");
    expect(out).toContain("12 trang");
    expect(out).not.toContain("rounded-sheet");
  });

  it("empty list keeps its words and one action in a sheet", () => {
    const out = renderToStaticMarkup(<DocumentList subjectId={SUBJECT} docs={[]} />);
    expect(out).toContain('data-tier="sheet"');
    expect(out).toContain("Chưa có tài liệu.");
    expect(out.match(/Tải tài liệu lên/g)).toHaveLength(1);
  });

  it("frame has a back link and the h1", () => {
    const out = renderToStaticMarkup(<DocumentsFrame name="Toán">x</DocumentsFrame>);
    expect(out).toContain('href="/subjects"');
    expect(out).toMatch(/<h1[^>]*>Toán<\/h1>/);
  });

  it("toc and its states sit in sheets", () => {
    const tree = toTree([{ title: "Chương 1", level: 0, page: 1 }], 5);
    expect(renderToStaticMarkup(<TocTree nodes={tree} />)).toContain('data-tier="sheet"');
    expect(renderToStaticMarkup(<TocNotReady />)).toContain("border-line");
  });

  it("no colour literals in the C4 folders", () => {
    for (const f of [
      "components/documents/document-list.tsx",
      "components/documents/toc-view.tsx",
      "components/graph/graph-screen.tsx",
      "components/graph/legend.tsx",
      "app/graph/page.tsx",
    ]) {
      expect(readFileSync(f, "utf8"), f).not.toMatch(/#[0-9a-fA-F]{3,8}\b|rgb\(|hsl\(/);
    }
  });
});
