// LANDING-V63-FIX: hero chip/sticker copy + structure, FSRS label, palette merged into shared tokens.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/headers", () => ({ cookies: async () => ({ has: () => false }) }));
vi.mock("@/components/landing-redirect", () => ({ LandingRedirect: () => "redirecting" }));
const { LandingEntry } = await import("@/components/landing/landing-entry");

const css = readFileSync(join(__dirname, "../components/landing/landing.module.css"), "utf8");

describe("landing v6.3", () => {
  it("hero chip: title plus one line, no question, no Tiếp theo button, no arrow", async () => {
    const out = renderToStaticMarkup(await LandingEntry());
    const chip = out.match(/<div class="note-chip"[\s\S]*?<\/div>/)?.[0] ?? "";
    expect(chip).toContain("Mây Mây – trợ lí học tập của bạn");
    expect(chip).toContain("Học tập thật dễ và vui!");
    expect(chip).not.toContain("Vì sao bầu trời màu xanh?");
    expect(chip).not.toContain("Tiếp theo");
    expect(out).not.toContain("m-arrow");
  });

  it("FSRS axis says Quên, not Sắp quên", async () => {
    const out = renderToStaticMarkup(await LandingEntry());
    expect(out).toMatch(/<span>Quên<\/span>/);
    expect(out).not.toContain("<span>Sắp quên</span>");
  });

  it("no local copies of shared palette tokens in the landing css", () => {
    for (const v of ["--bg", "--ink", "--hong", "--rose-100", "--plum", "--line"]) {
      expect(css).not.toMatch(new RegExp(`\.lp\{[^}]*${v}:`));
    }
  });

  it("queue chips animate sideways only (shared baseline)", () => {
    const motion = readFileSync(join(__dirname, "../components/landing/motion.ts"), "utf8");
    expect(motion).not.toContain("translate(-40px,26px)");
  });
});
