// Design tokens v3 (docs/design/visual-system.md §1): every text and border pair the
// rules allow meets WCAG, and the three copies of the palette never drift apart. Values are read
// from app/globals.css, never copied from the spec (plan V6, V15).
import { describe, expect, it } from "vitest";

import { contrast, contrastOn, osDarkPalette, palette, stops, type Mode } from "./css-tokens";

type Pair = [fg: string, bg: string, base?: string];

// Final §1.3: text pairs allowed to carry words (≥ 4.5:1).
const TEXT: Record<Mode, Pair[]> = {
  light: [
    ...["--bg", "--sheet", "--sunken", "--rose-50", "--rose-100", "--cover", "--rose-200", "--hl-stroke", "--hl"].map(
      (bg): Pair => ["--ink", bg],
    ),
    ...["--bg", "--sunken", "--rose-50", "--rose-100", "--rose-200", "--hl-stroke"].map((bg): Pair => ["--ink-soft", bg]),
    ...["--bg", "--sunken", "--rose-50", "--rose-100", "--rose-200"].map((bg): Pair => ["--hong", bg]),
    ...["--bg", "--sunken", "--rose-50", "--rose-100"].map((bg): Pair => ["--pencil", bg]),
    ...["--bg", "--sunken", "--rose-100"].map((bg): Pair => ["--correct", bg]),
    ...["--bg", "--sunken", "--rose-50", "--rose-100"].map((bg): Pair => ["--partial", bg]),
    ["--on-hong", "--hong"],
    ["--hong", "--on-hong"],
    ["--bg", "--ink"],
  ],
  dark: [
    ...["--bg", "--sheet", "--raised", "--sunken", "--rose-100", "--rose-200", "--cover", "--hl-stroke"].map(
      (bg): Pair => ["--ink", bg],
    ),
    ...["--bg", "--sheet", "--raised", "--rose-200", "--cover"].map((base): Pair => ["--ink", "--hl", base]),
    ...["--bg", "--sheet", "--raised", "--sunken", "--rose-100", "--rose-200", "--cover", "--hl-stroke"].map(
      (bg): Pair => ["--ink-soft", bg],
    ),
    ...["--bg", "--sheet", "--raised", "--sunken", "--rose-100", "--rose-200", "--cover", "--hl-stroke"].map(
      (bg): Pair => ["--hong", bg],
    ),
    ...["--bg", "--sheet", "--raised", "--sunken"].map((bg): Pair => ["--pencil", bg]),
    ...["--sheet", "--raised", "--sunken"].map((bg): Pair => ["--correct", bg]),
    ...["--bg", "--sheet", "--raised", "--sunken", "--rose-200", "--hl-stroke"].map((bg): Pair => ["--partial", bg]),
    ["--on-hong", "--hong"],
    ["--hong", "--on-hong"],
    ["--bg", "--ink"],
  ],
};

// Final §1.4: borders, icons and focus rings (≥ 3:1).
const EDGES: Record<Mode, Pair[]> = {
  light: [
    ...["--bg", "--sheet", "--raised", "--sunken", "--rose-100", "--rose-200"].map((bg): Pair => ["--line-strong", bg]),
    ["--stroke-line", "--hl-stroke"],
    ["--focus", "--bg"],
    ["--focus", "--sheet"],
    ["--focus", "--hl-stroke"],
    ["--hl-edge", "--bg"],
    ["--correct", "--sheet"],
    ["--partial", "--sheet"],
    ["--pencil", "--sheet"],
    ["--hong", "--rose-100"],
  ],
  dark: [
    ...["--bg", "--sheet", "--raised", "--sunken", "--rose-100", "--rose-200"].map((bg): Pair => ["--line-strong", bg]),
    ["--stroke-line", "--hl-stroke"],
    ["--focus", "--bg"],
    ["--focus", "--sheet"],
    ["--focus", "--hl-stroke"],
    ["--hl-edge", "--sheet"],
    ["--correct", "--sheet"],
    ["--partial", "--sheet"],
    ["--pencil", "--sheet"],
    ["--hong", "--rose-200"],
  ],
};

// Pairs the rules forbid because they fall short: they must stay short, so the rule stays true.
const FORBIDDEN: Record<Mode, Pair[]> = {
  light: [
    ["--ink-soft", "--hl"],
    ["--hong", "--hl"],
    ["--pencil", "--hl"],
  ],
  dark: [
    ["--hong", "--hl", "--bg"],
    ["--line-strong", "--cover"],
  ],
};

const label = ([fg, bg, base]: Pair) => `${fg} on ${bg}${base ? ` over ${base}` : ""}`;

describe.each(["light", "dark"] as const)("%s palette", (mode) => {
  const tokens = () => palette(mode);

  it.each(TEXT[mode].map((pair) => [label(pair), pair] as const))("text %s ≥ 4.5", (_, [fg, bg, base]) => {
    expect(contrast(tokens(), fg, bg, base)).toBeGreaterThanOrEqual(4.5);
  });

  it.each(EDGES[mode].map((pair) => [label(pair), pair] as const))("edge %s ≥ 3", (_, [fg, bg, base]) => {
    expect(contrast(tokens(), fg, bg, base)).toBeGreaterThanOrEqual(3);
  });

  it.each(FORBIDDEN[mode].map((pair) => [label(pair), pair] as const))(
    "forbidden %s stays below its threshold",
    (_, [fg, bg, base]) => {
      const limit = fg === "--line-strong" ? 3 : 4.5;
      expect(contrast(tokens(), fg, bg, base)).toBeLessThan(limit);
    },
  );
});

// Final §1.3 "on buttons and the pink tile": text and focus on every stop of the tile's gradient.
describe.each(["light", "dark"] as const)("%s pink tile", (mode) => {
  it.each([
    ["--on-surface-hong", 4.5],
    ["--hong-soft-text", 4.5],
    ["--focus-on-hong", 3],
    ["--inverse-bg", 3], // the primary-inverse fill is the button's only edge (review of cf1c9a0)
  ] as const)("%s on every stop of --hong-glow", (fg, limit) => {
    const tokens = palette(mode);
    const found = stops(tokens, "--hong-glow");
    expect(found).toHaveLength(3);
    for (const stop of found) expect(contrastOn(tokens, fg, stop)).toBeGreaterThanOrEqual(limit);
  });
});

describe.each(["light", "dark"] as const)("%s primary-inverse", (mode) => {
  it("its label reads on its fill (≥ 4.5)", () => {
    expect(contrast(palette(mode), "--inverse-fg", "--inverse-bg")).toBeGreaterThanOrEqual(4.5);
  });
});

describe("token tables", () => {
  it("checks the number of pairs it means to (a dropped pair fails here)", () => {
    const count = (table: Record<Mode, Pair[]>) => table.light.length + table.dark.length;
    expect([count(TEXT), count(EDGES), count(FORBIDDEN)]).toEqual([79, 30, 5]);
  });

  it("matches the spec on a few exact values, to catch a mistyped hex", () => {
    const light = palette("light");
    const dark = palette("dark");
    expect(contrast(light, "--hong", "--bg")).toBeCloseTo(6.79, 1);
    expect(contrast(light, "--ink", "--hl")).toBeCloseTo(8.83, 1);
    expect(contrast(dark, "--hong", "--bg")).toBeCloseTo(8.17, 1);
    expect(contrast(dark, "--ink", "--hl", "--bg")).toBeCloseTo(8.24, 1);
  });
});

describe("palette copies", () => {
  it("the OS-dark block declares exactly what the data-theme dark block does", () => {
    expect(osDarkPalette()).toEqual(palette("dark"));
  });

  it("light and dark declare the same tokens", () => {
    expect(Object.keys(palette("dark")).sort()).toEqual(Object.keys(palette("light")).sort());
  });

  it("no orange and no --right are left", () => {
    for (const mode of ["light", "dark"] as const) {
      expect(Object.keys(palette(mode))).not.toContain("--cam");
      expect(Object.keys(palette(mode))).not.toContain("--right");
    }
  });
});
