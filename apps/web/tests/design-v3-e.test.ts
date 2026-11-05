// DESIGN-E: the Thống kê and auth screens follow DESIGN-V3 (plum field, one totals sheet, today in cam-fill).
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const read = (f: string) => readFileSync(join(__dirname, "..", f), "utf8");

describe("DESIGN-E", () => {
  it("auth layout has a plum field with the tagline and a 400px sheet", () => {
    const src = read("components/auth/auth-layout.tsx");
    expect(src).toContain("bg-plum");
    expect(src).toContain("Tối nay ôn gì, đã có app lo");
    expect(src).toContain("max-w-[400px]");
    expect(src).toContain("min-[1024px]:col-span-5");
  });
  it("stats: totals sit on one plum block, today is cam-fill with an ink ring", () => {
    const src = read("components/stats/stats-screen.tsx");
    expect(src.match(/tier="field"/g)).toHaveLength(1);
    const css = read("components/stats/stats.module.css");
    expect(css).toMatch(/data-today="true"\]\s*\{[^}]*cam-fill[^}]*var\(--ink\)/);
  });
  it("no hard-coded hex colours in stats and auth except the Google brand mark and token fallbacks", () => {
    for (const f of ["components/stats/activity-grid.tsx", "components/stats/stat-tile.tsx", "components/auth/login-form.tsx", "components/auth/register-form.tsx"]) {
      expect(read(f)).not.toMatch(/#[0-9a-fA-F]{6}\b/);
    }
  });
});
