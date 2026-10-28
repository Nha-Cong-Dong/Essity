// T4.9 (US-01, US-02 AC2): the document list and the toc view.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DocumentList, unreadableText } from "@/components/documents/document-list";
import { TocTree, UnreadableNotice } from "@/components/documents/toc-view";
import { toTree } from "@/lib/toc";

const SUBJECT = "b2c3d4e5-6f7a-4b8c-9d0e-1f2a3b4c5d6e";
const doc = (over: Partial<Parameters<typeof DocumentList>[0]["docs"][number]>) => ({
  id: "d1",
  short_name: "Giáo trình",
  status: "indexed",
  page_count: 120,
  unreadable_pages: [] as number[],
  failure_reason: null,
  ...over,
});
const html = (docs: ReturnType<typeof doc>[]) =>
  renderToStaticMarkup(<DocumentList subjectId={SUBJECT} docs={docs} />);

describe("DocumentList", () => {
  it("shows each state in words; only an indexed document links to its toc", () => {
    const out = html([
      doc({}),
      doc({ id: "d2", short_name: "Slide", status: "pending", page_count: null }),
      doc({ id: "d3", short_name: "Đề cương", unreadable_pages: [12, 13, 40] }),
      doc({ id: "d4", short_name: "Hỏng", status: "failed", failure_reason: "corrupt" }),
    ]);
    expect(out).toContain("Sẵn sàng");
    expect(out).toContain("Đang đọc tài liệu…");
    expect(out).toContain("Không đọc được 3 trang (tr. 12, 13, 40)");
    expect(out).toContain("File bị lỗi nên chưa đọc được.");
    expect(out).toContain(`href="/subjects/${SUBJECT}/documents/d1"`);
    expect(out).not.toContain("/documents/d2");
    expect(out).not.toContain("/documents/d4");
  });

  it("falls back for an unknown failure reason and says so when empty", () => {
    expect(html([doc({ status: "rejected", failure_reason: "x" })])).toContain("Chưa đọc được tài liệu này.");
    expect(html([])).toContain("Chưa có tài liệu.");
  });

  it("cuts a long list of unreadable pages", () => {
    expect(unreadableText([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])).toBe("Không đọc được 10 trang (tr. 1, 2, 3, 4, 5, 6, 7, 8, …)");
  });
});

describe("TocTree", () => {
  it("renders the tree with page ranges, nested", () => {
    const nodes = toTree(
      [
        { title: "Chương 1", level: 0, page: 1 },
        { title: "1.1 Thẳng", level: 1, page: 1 },
        { title: "Chương 2", level: 0, page: 9 },
      ],
      20,
    );
    const out = renderToStaticMarkup(<TocTree nodes={nodes} />);
    expect(out).toContain("Chương 1");
    expect(out).toContain("tr. 1–8");
    expect(out).toContain("tr. 9–20");
    expect(out.match(/<ul/g)).toHaveLength(2);
  });

  it("says so for an empty toc and lists unreadable pages", () => {
    expect(renderToStaticMarkup(<TocTree nodes={[]} />)).toContain("không có mục lục");
    expect(renderToStaticMarkup(<UnreadableNotice pages={[3]} />)).toContain("Không đọc được 1 trang (tr. 3)");
    expect(renderToStaticMarkup(<UnreadableNotice pages={[]} />)).toBe("");
  });
});
