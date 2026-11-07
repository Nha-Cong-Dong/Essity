// LANDING-V61-PORT: structure of landing v6.1: block order, the words that carry the argument, the pause control,
// the Mây mascot from the shared component, and that motion only runs from the client layer (reduced-motion safe).
import { readFileSync } from "node:fs";
import path from "node:path";

import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ has: () => false }) }));
vi.mock("@/components/landing-redirect", () => ({ LandingRedirect: () => "redirecting" }));

const { LandingEntry } = await import("@/components/landing/landing-entry");
const html = renderToStaticMarkup(await LandingEntry());
const read = (f: string) => readFileSync(path.join(process.cwd(), "components/landing", f), "utf8");

describe("landing v6.1", () => {
  it("blocks come in the approved order, the footer last", () => {
    const ids = ["dau-trang", "do-thi", "de-cuong", "the-nguon", "lich-on", "luyen-de", "chinh-sua", "thu-cham", "hoi-dap", "cuoi"];
    const at = ids.map((id) => html.indexOf(`id="${id}"`));
    expect(at.every((i) => i >= 0)).toBe(true);
    expect([...at].sort((a, b) => a - b)).toEqual(at);
  });

  it("each block names what it shows, in the finished (no-script) state", () => {
    expect(html).toContain("Hiệu ứng Mpemba");
    expect(html).toContain("Nguồn · tr. 3");
    expect(html).toContain("mục hiệu ứng Mpemba tôi học rồi");
    expect(html).toContain('data-pause=""');
  });

  it("the Mây mascot is the shared Mascot component (cloud)", () => {
    expect(read("landing.tsx")).toMatch(/<Mascot\s+kind="cloud"/);
    expect(html).toContain('data-mascot="chao"');
  });

  it("the FSRS curve is drawn by the server: a path and three dots", () => {
    expect(html).toMatch(/class="[^"]*c-line[^"]*"[^>]*d="M0\.0 /);
    expect((html.match(/<circle cx="[\d.]+" cy="[\d.]+" r="7"/g) ?? []).length).toBe(3);
  });

  it("motion honours prefers-reduced-motion and the pause button, and cleans up after itself", () => {
    const m = read("motion.ts");
    expect(m).toContain("prefers-reduced-motion: reduce");
    expect(m).toContain("data-pause");
    expect(m).toContain("alive = false");
    expect(read("landing.module.css")).toContain("prefers-reduced-motion");
    expect(read("landing.module.css")).toContain(":focus-visible");
  });

  it("LANDING-V62-FIX copy: hero chip, card section and edit section carry the user's words", () => {
    const text = html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
    expect(text).toContain("Mây Mây – trợ lí học tập của bạn");
    expect(text).toContain("Chia thẻ kiến thức thông minh");
    expect(text).toContain("AI tự động chia kiến thức thành các thẻ ghi nhớ, sẵn sàng cho việc recall. Người dùng có thể chỉnh sửa thẻ bằng markdown.");
    expect(text).toContain("Chỉnh sửa đơn giản");
    expect(text).toContain("Tất cả thao tác chỉnh sửa chỉ cần viết ra yêu cầu và trợ lí AI sẽ hỗ trợ hoàn thành.");
    expect(text).not.toContain("Chỉnh bằng một câu");
    expect(text).not.toContain("Học gì tiếp");
  });
});
