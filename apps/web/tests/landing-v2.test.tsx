// T0.16: the landing now describes v2. Section order, five questions, the word budget and the
// forbidden-word scan (docs/DESIGN.md) on the prose.
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ has: () => false }) }));
vi.mock("@/components/landing-redirect", () => ({ LandingRedirect: () => "redirecting" }));

const { LandingEntry } = await import("@/components/landing/landing-entry");
const html = renderToStaticMarkup(await LandingEntry());

const FORBIDDEN = /(?<!\p{L})(streak|chuỗi|xếp hạng|ranking|trễ|kém|lười|bỏ lỡ|thất bại|phải|cần|kịp)(?!\p{L})/iu;

const strip = (s: string) =>
  s
    .replace(/<svg[\s\S]*?<\/svg>/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/&[a-z#0-9]+;/g, " ")
    .replace(/\s+/g, " ")
    .trim();

// Prose = headings, paragraphs and Q&A of the sections after the hero, minus the demo, aria-hidden figures and the .sr sentences.
function prose(): string[] {
  const body = html.slice(html.indexOf('id="cach-hoat-dong"'), html.indexOf("<footer"));
  const noFigures = body
    .replace(/<div[^>]*aria-hidden="true"[\s\S]*?<\/div>/g, " ")
    .replace(/<p class="[^"]*sr[^"]*">[\s\S]*?<\/p>/g, " "); // screen-reader sentences are not counted
  return [...noFigures.matchAll(/<(h2|h3|p|dt|dd)\b[^>]*>([\s\S]*?)<\/\1>/g)].map((m) => strip(m[2] ?? ""));
}

describe("landing v2 (T0.16)", () => {
  it("sections come in the approved order", () => {
    const ids = ["thu-cham", "cach-hoat-dong", "hoc-gi-tiep", "luyen-dang-de", "hoi-dap"];
    const at = ids.map((id) => html.indexOf(`id="${id}"`));
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
    expect(html.indexOf("<footer")).toBeGreaterThan(at[4]!);
  });

  it("the FAQ has exactly six items", () => {
    const faq = html.slice(html.indexOf('id="hoi-dap"'), html.indexOf("<footer"));
    expect(faq.match(/<dt\b/g)).toHaveLength(6);
    expect(faq.match(/<dd\b/g)).toHaveLength(6);
    expect(faq).toContain("Sửa nhanh thế nào?");
  });

  it("block A and B carry text labels and a screen-reader sentence", () => {
    expect(html).toContain("✓ Đã học");
    expect(html).toMatch(/→ <\/span>Tiếp theo/);
    expect(html).toContain("→ Gợi ý: liên quan tới Định tuyến");
    expect(html).toContain("câu tính toán đứng đầu, được gợi ý luyện trước vì liên quan tới mục Định tuyến");
  });

  it("prose stays within 360 words", () => {
    const words = prose().join(" ").split(" ").filter(Boolean).length;
    expect(words).toBeGreaterThan(100);
    expect(words).toBeLessThanOrEqual(360);
  });

  it("no forbidden word in the prose (the round-10 FAQ title is the one exception)", () => {
    const hits = prose().filter((t) => t !== "Cần chuẩn bị gì?" && FORBIDDEN.test(t));
    expect(hits).toEqual([]);
  });
});
