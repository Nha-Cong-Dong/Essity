// Edge cases of design tokens v3 that tests/design-tokens.test.ts and design-rules.test.ts leave
// open (independent test pass on the branch). Each test names the change in src that turns it red.
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { block, declarations, SELECTORS } from "./css-tokens";

const WEB = path.resolve(import.meta.dirname, "..");
const CSS = readFileSync(path.join(WEB, "app/globals.css"), "utf-8");
const read = (file: string) => readFileSync(path.join(WEB, file), "utf-8");

function files(dir: string, pattern: RegExp): string[] {
  return readdirSync(path.join(WEB, dir), { recursive: true, withFileTypes: true })
    .filter((entry) => entry.isFile() && pattern.test(entry.name))
    .map((entry) => path.relative(WEB, path.join(entry.parentPath, entry.name)));
}
const UI = [...files("app", /\.tsx$/), ...files("components", /\.tsx$/)];

const theme = () => declarations(block("@theme inline"));

describe("color-scheme follows the palette (it is not a custom property, so the copy test skips it)", () => {
  // Red when: one of the three blocks says `color-scheme: light` (or dark) wrongly: native form
  // controls, scrollbars and the default canvas would then ignore the chosen mode.
  const scheme = (body: string) => /color-scheme:\s*(\w+);/.exec(body)?.[1];

  it("light block is light, chosen dark block is dark, OS-dark block is dark", () => {
    expect(scheme(block(SELECTORS.light))).toBe("light");
    expect(scheme(block(SELECTORS.dark))).toBe("dark");
    const media = CSS.slice(CSS.indexOf("@media (prefers-color-scheme: dark) {\n  :root:not"));
    expect(scheme(block(SELECTORS.osDark, media))).toBe("dark");
  });
});

describe("base rules", () => {
  // Red when: the global focus ring is removed or recoloured (every control without its own
  // focus utility, links included, would lose its focus indicator).
  it("a focus ring is always visible: 2px, 2px away, in the focus colour", () => {
    const base = block(":focus-visible", CSS.slice(CSS.indexOf("@layer base")));
    expect(base).toMatch(/outline:\s*2px solid var\(--focus\)/);
    expect(base).toMatch(/outline-offset:\s*2px/);
  });

  // Red when: the reduced-motion block loses a property (animation or transition would run).
  it("reduced motion stops animation, transition and smooth scroll", () => {
    const body = block("@media (prefers-reduced-motion: reduce)", CSS.slice(CSS.indexOf("@layer base")));
    expect(body).toMatch(/animation-duration:\s*0\.01ms !important/);
    expect(body).toMatch(/animation-iteration-count:\s*1 !important/);
    expect(body).toMatch(/transition-duration:\s*0\.01ms !important/);
    expect(body).toMatch(/scroll-behavior:\s*auto !important/);
  });
});

describe("the pink surface passes its own tokens down", () => {
  const surface = () => block('[data-surface="hong"]');

  // Red when: the surface stops reading --on-surface-hong (text would be --ink on a pink fill
  // in light mode) or stops swapping --focus for --focus-on-hong (hong ring on a hong tile).
  it("text and focus come from the palette tokens the contrast test checks", () => {
    expect(surface()).toMatch(/color:\s*var\(--on-surface-hong\)/);
    expect(surface()).toMatch(/--focus:\s*var\(--focus-on-hong\)/);
    expect(surface()).toMatch(/background:\s*var\(--hong-glow\)/);
  });

  // Red when: the grain overlay can take clicks, or a later change drops `isolation` and the
  // negative z-index overlay slides behind the tile's own background.
  it("its grain never takes the pointer and stays inside the tile", () => {
    const grain = block('[data-surface="hong"]::after');
    expect(grain).toMatch(/pointer-events:\s*none/);
    expect(surface()).toMatch(/isolation:\s*isolate/);
  });
});

describe("scale (final §2, §5, §7)", () => {
  // Red when: a role radius is edited alone (`--radius-control: 8px`...). V1 fixed them.
  it("role radii: control 12, slip 14, sheet 24, tile 28; the shadcn aliases keep the old order", () => {
    const t = theme();
    expect(t).toMatchObject({
      "--radius-control": "12px",
      "--radius-slip": "14px",
      "--radius-sheet": "24px",
      "--radius-tile": "28px",
      "--radius-cover-spine": "10px",
      "--radius-cover-edge": "28px",
    });
    expect(Number.parseInt(t["--radius-sm"])).toBeLessThanOrEqual(Number.parseInt(t["--radius-md"]));
    expect(Number.parseInt(t["--radius-md"])).toBeLessThanOrEqual(Number.parseInt(t["--radius-lg"]));
  });

  // Red when: a text step gets a line height under 1.15 (Vietnamese diacritics clip) -- except
  // the two documented single-line steps -- or a unitless value is mistyped.
  it("every text step keeps line height ≥ 1.15 for diacritics (mega and logo are single numbers)", () => {
    const t = theme();
    const single = new Set(["--text-mega--line-height", "--text-logo--line-height"]);
    const low = Object.entries(t)
      .filter(([k, v]) => /^--text-[\w-]+--line-height$/.test(k) && /^[\d.]+$/.test(v) && !single.has(k))
      .filter(([, v]) => Number(v) < 1.15)
      .map(([k, v]) => `${k}: ${v}`);
    expect(low).toEqual([]);
    expect(Object.keys(t).filter((k) => /--line-height$/.test(k)).length).toBeGreaterThan(10);
  });

  // Red when: reading text drops under 16px or small text under 14px (final §2 floor).
  it("body is 16px, meta 14px, read and answer 18px: nothing readable under 14px", () => {
    const t = theme();
    expect(t["--text-body"]).toBe("16px");
    expect(t["--text-meta"]).toBe("14px");
    expect(t["--text-read"]).toBe("18px");
    expect(t["--text-answer"]).toBe("18px");
    const px = Object.entries(t)
      .filter(([k, v]) => /^--text-[a-z]+$/.test(k) && /^\d+px$/.test(v))
      .filter(([, v]) => Number.parseInt(v) < 14);
    expect(px).toEqual([]);
  });

  // Red when: the header height or the page gutter is changed in :root only; the shells,
  // scroll-padding and the §5 container read these two.
  it("frame: 64px header, 56px focus header, page max 1280", () => {
    const root = declarations(block(":root"));
    expect(root["--header-h"]).toBe("64px");
    expect(root["--header-focus-h"]).toBe("56px");
    expect(root["--page-max"]).toBe("1280px");
    expect(root["--page-gutter"]).toMatch(/^clamp\(16px,/);
  });
});

describe("Tailwind tokens", () => {
  // Red when: a theme token is renamed or removed while a component still uses its utility:
  // Tailwind then emits no CSS for `bg-book-cover` (the cover would be transparent) and nothing
  // fails at build time.
  it("every colour, shadow and radius utility used in a component exists in @theme", () => {
    const t = theme();
    const colourPrefix = /\b(?:hover:|focus-visible:|disabled:|aria-[\w-]+:|aria-\[[^\]]+\]:|min-\[\d+px\]:|sm:|lg:)*(bg|outline|inset-ring|decoration|border|text|ring|fill|stroke|from|via|to)-([a-z][a-z0-9-]*)(?:\/\d+)?(?=[\s"'`])/g;
    const NOT_COLOUR = new Set([
      "transparent", "current", "none", "solid", "dotted", "dashed", "double", "left", "right", "center",
      "b", "t", "l", "r", "x", "y", "s", "e", "wrap", "nowrap", "ellipsis", "clip", "balance", "pretty",
      "offset", "inherit", "start", "end", "justify", "top", "bottom", "line-through", "underline",
    ]);
    const missing: string[] = [];
    for (const file of UI) {
      for (const [, prefix, name] of read(file).matchAll(colourPrefix)) {
        if (NOT_COLOUR.has(name) || /^(offset|decoration|[btlrxy]-)/.test(name)) continue;
        if (name.startsWith("offset-")) continue;
        const known = `--color-${name}` in t || (prefix === "text" && `--text-${name}` in t);
        if (!known) missing.push(`${file}: ${prefix}-${name}`);
      }
      for (const [, name] of read(file).matchAll(/\bshadow-([a-z][a-z0-9-]*)/g)) {
        if (!(`--shadow-${name}` in t) && !["none"].includes(name)) missing.push(`${file}: shadow-${name}`);
      }
      for (const [, name] of read(file).matchAll(/\brounded-([a-z][a-z0-9-]*)/g)) {
        if (!(`--radius-${name}` in t) && !["full", "none"].includes(name)) missing.push(`${file}: rounded-${name}`);
      }
    }
    expect([...new Set(missing)]).toEqual([]);
  });

  // Red when: `--color-right` / `--color-cam` is declared in @theme again (text-right would then
  // mean a colour AND an alignment; orange is out of the palette).
  it("@theme declares no colour named right or cam", () => {
    expect(Object.keys(theme()).filter((k) => /^--color-(right|cam)$/.test(k))).toEqual([]);
  });
});
