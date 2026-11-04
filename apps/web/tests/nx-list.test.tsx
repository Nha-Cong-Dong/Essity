// V22: the landing's "nx" list as components (NxList, NxRow, NxChip, NxKind) and the screen kit
// pieces built on it (ScreenHeader, Stat, Row). Rendered to static markup; geometry is e2e's job.
import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Row, ScreenHeader, Stat } from "@/components/screen-kit";
import { NxChip, NxKind, NxList, NxRow } from "@/components/ui/nx-list";

const html = (node: Parameters<typeof renderToStaticMarkup>[0]) => renderToStaticMarkup(node);

describe("NxList", () => {
  it("is a --hong-tint tile with no border and no shadow, with the hint beside the title", () => {
    const out = html(h(NxList, { title: "Mạng máy tính", hint: "Gợi ý, bạn chọn" }, h(NxRow, { lead: "3.1", state: "Đã học" }, "Mục")));
    expect(out).toMatch(/bg-hong-tint/);
    expect(out).toMatch(/rounded-tile/);
    expect(out).not.toMatch(/border|shadow/);
    expect(out).toContain("Gợi ý, bạn chọn");
  });

  it("rows sit on the page colour, three columns, 36px lead", () => {
    const out = html(h(NxRow, { lead: "3.1", state: "Đã học" }, "Mục"));
    expect(out).toMatch(/grid-cols-\[36px_minmax\(0,1fr\)_auto\]/);
    expect(out).toMatch(/bg-bg/);
    expect(out).toMatch(/rounded-row/);
  });

  it("the next row is cam, with an arrow and words: never colour alone", () => {
    const out = html(h(NxRow, { lead: "3.3", state: "Tiếp theo", next: true, why: "Vì liên quan tới mục 3.2" }, "Định tuyến"));
    expect(out).toMatch(/inset-ring-cam/);
    expect(out).toContain("→ ");
    expect(out).toContain("Tiếp theo");
    expect(out).toContain("Vì liên quan tới mục 3.2");
  });

  it("a plain row has no cam", () => {
    expect(html(h(NxRow, { lead: "3.1", state: "Đã học" }, "Mục"))).not.toMatch(/cam/);
  });

  it("a linked row is one anchor with a sunken hover", () => {
    const out = html(h(NxRow, { lead: "A", href: "/subjects/1", state: "còn 41 ngày" }, "Mạng máy tính"));
    expect(out).toMatch(/<a href="\/subjects\/1"[^>]*hover:bg-sunken/);
  });

  it("NxKind stacks the chip over the question; the pick carries its reason", () => {
    const out = html(h(NxKind, { chip: "Tính toán", pick: true, why: "Nên luyện trước" }, "Tính thông lượng"));
    expect(out).toMatch(/flex-col/);
    expect(out).toContain("Tính toán");
    expect(out).toContain("Nên luyện trước");
    expect(out).toMatch(/inset-ring-cam/);
  });

  it("NxChip is a 28px pill", () => {
    expect(html(h(NxChip, null, "Tự luận"))).toMatch(/h-7[^"]*rounded-full/);
  });
});

describe("ScreenHeader", () => {
  it("draws one h1, with the highlighter under the phrase only", () => {
    const out = html(h(ScreenHeader, { title: "Hôm nay bạn học gì", highlight: "học gì" }));
    expect(out.match(/<h1/g)).toHaveLength(1);
    expect(out.match(/hl-word/g)).toHaveLength(1);
    expect(out).toMatch(/<span[^>]*class="hl-word"[^>]*>học gì<\/span>/);
  });

  it("without a highlight there is no motif; the h1 breaks between words only", () => {
    const out = html(h(ScreenHeader, { title: "Đề cương" }));
    expect(out).not.toMatch(/hl-word/);
    expect(out).toMatch(/\[overflow-wrap:normal\]/);
    expect(out).toMatch(/text-balance/);
  });
});

describe("Stat and Row", () => {
  it("a missing figure is a dash at body size, never a big word", () => {
    const out = html(h(Stat, { label: "Thẻ đã ôn", value: null }));
    expect(out).toContain("—");
    expect(out).not.toMatch(/text-display|text-verdict/);
  });

  it("the display figure is the one big number", () => {
    expect(html(h(Stat, { label: "Thẻ", value: 3, size: "display" }))).toMatch(/text-display/);
  });

  it("a Row has a fixed 36px lead cell and a 56px minimum", () => {
    const out = html(h(Row, { lead: "A", title: "Tên" }));
    expect(out).toMatch(/size-9/);
    expect(out).toMatch(/min-h-14/);
  });
});
