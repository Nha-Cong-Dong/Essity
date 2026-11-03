// G4: the "Nguồn" view.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SourceButton } from "@/components/card-source/source-button";
import { SourceView } from "@/components/card-source/source-view";
import { sourceHref, sourceLabel, splitMarked } from "@/lib/card-source";

const base = { anchor_id: "a", document_id: "d", subject_id: "s", quote: "ba bước" };

describe("card source", () => {
  it("G4: the passage is cut out of the page text", () => {
    expect(splitMarked("xx ba bước yy", 3, 10)).toEqual([
      { text: "xx ", marked: false },
      { text: "ba bước", marked: true },
      { text: " yy", marked: false },
    ]);
    expect(splitMarked("abc", null, null)).toEqual([{ text: "abc", marked: false }]);
  });
  it("G4: label and link", () => {
    expect(sourceLabel({ document_name: "Giáo trình", page_no: 12 })).toBe("Giáo trình, trang 12");
    expect(sourceLabel({ document_name: null, page_no: null })).toBe("Ghi chú");
    expect(renderToStaticMarkup(<SourceButton cardId="c1" />)).toContain(sourceHref("c1"));
  });
  it("G4: the view wraps the passage in <mark>", () => {
    const html = renderToStaticMarkup(
      <SourceView source={{ ...base, document_name: "GT", page_no: 2, page_text: "xx ba bước yy", mark_start: 3, mark_end: 10 }} />,
    );
    expect(html).toContain("<mark>ba bước</mark>");
    expect(html).toContain("GT, trang 2");
  });
  it("G4: no page text still shows the quote", () => {
    const html = renderToStaticMarkup(
      <SourceView source={{ ...base, document_name: "GT", page_no: 2, page_text: null, mark_start: null, mark_end: null }} />,
    );
    expect(html).toContain("<mark>ba bước</mark>");
  });
});
