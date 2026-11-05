// Design tokens v3 (docs/design/visual-system.md §1): every text and border pair the
// rules allow meets WCAG, and the three copies of the palette never drift apart. Values are read
// from app/globals.css, never copied from the spec (plan V6, V15).
import { describe, expect, it } from "vitest";

import { contrast, contrastOn, osDarkPalette, palette, stops, type Mode } from "./css-tokens";

type Pair = [fg: string, bg: string, base?: string];

// DESIGN-V4 (design-system.md A1): text pairs allowed to carry words (>= 4.5:1).
const BG_LIGHT = ["--bg", "--sheet", "--sunken", "--rose-50", "--rose-100", "--rose-200"];
const BG_DARK = ["--bg", "--sheet", "--raised", "--sunken", "--rose-100", "--rose-200", "--cover"];
const TEXT: Record<Mode, Pair[]> = {
  light: [
    ...[...BG_LIGHT, "--cover", "--hl-stroke", "--hl", "--block", "--accent-tint"].map((bg): Pair => ["--ink", bg]),
    ...[...BG_LIGHT, "--hl-stroke", "--block"].map((bg): Pair => ["--ink-soft", bg]),
    // Pink TEXT is --hong-text, never --hong (3.83 on --bg).
    ...[...BG_LIGHT, "--hong-tint"].map((bg): Pair => ["--hong-text", bg]),
    ...["--bg", "--sunken", "--rose-100"].map((bg): Pair => ["--pencil", bg]),
    ...["--bg", "--sunken", "--correct-bg"].map((bg): Pair => ["--correct", bg]),
    ["--correct", "--correct-bg"],
    ...["--bg", "--sunken", "--partial-bg"].map((bg): Pair => ["--partial", bg]),
    ["--on-hong", "--hong"],
    ["--bg", "--ink"],
    ["--ink", "--hong-tint"],
    ["--ink-soft", "--hong-tint"],
    // Teal is the assistant's voice: text and fills.
    ["--accent", "--bg"],
    ["--accent", "--sheet"],
    ["--accent", "--hong-tint"],
    ["--accent", "--accent-tint"],
    ["--on-accent", "--accent"],
    ["--ink", "--accent-tint"],
    ["--cam", "--bg"],
    ["--on-cam-fill", "--cam-fill"],
    ["--now", "--sheet"],
    // The field (tier 1), its button, and the pressed pink.
    ["--on-plum", "--plum"],
    ["--on-plum-soft", "--plum"],
    ["--on-plum-action-fg", "--on-plum-action-bg"],
    ["--on-hong", "--hong-press"],
    ["--now-on-field", "--field"],
    // The button on a solid pink surface (primary-inverse).
    ["--inverse-fg", "--inverse-bg"],
  ],
  dark: [
    ...[...BG_DARK, "--hl-stroke", "--hl", "--block", "--accent-tint"].map((bg): Pair => ["--ink", bg]),
    ...[...BG_DARK, "--hl-stroke", "--block", "--hl"].map((bg): Pair => ["--ink-soft", bg]),
    ...[...BG_DARK, "--hl-stroke", "--hong-tint"].map((bg): Pair => ["--hong-text", bg]),
    ...[...BG_DARK, "--hl-stroke"].map((bg): Pair => ["--hong", bg]),
    ...["--bg", "--sheet", "--raised", "--sunken"].map((bg): Pair => ["--pencil", bg]),
    ...["--sheet", "--raised", "--sunken", "--correct-bg"].map((bg): Pair => ["--correct", bg]),
    ...["--bg", "--sheet", "--raised", "--sunken", "--partial-bg"].map((bg): Pair => ["--partial", bg]),
    ["--on-hong", "--hong"],
    ["--bg", "--ink"],
    ["--ink", "--hong-tint"],
    ["--ink-soft", "--hong-tint"],
    ["--accent", "--bg"],
    ["--accent", "--sheet"],
    ["--accent", "--accent-tint"],
    ["--on-accent", "--accent"],
    ["--cam", "--bg"],
    ["--on-cam-fill", "--cam-fill"],
    ["--now", "--sheet"],
    ["--on-plum", "--plum"],
    ["--on-plum-soft", "--plum"],
    ["--on-plum-action-fg", "--on-plum-action-bg"],
    ["--on-hong", "--hong-press"],
    ["--now-on-field", "--field"],
    ["--inverse-fg", "--inverse-bg"],
  ],
};

// Borders, icons and focus rings (>= 3:1).
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
    ["--focus-on-plum", "--plum"],
    ["--focus-on-hong", "--hong"],
    ["--hong-press", "--bg"],
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
    ["--focus-on-plum", "--plum"],
    ["--focus-on-hong", "--hong"],
    ["--hong-press", "--bg"],
  ],
};

// Pairs the rules forbid because they fall short: they must stay short, so the rule stays true.
const FORBIDDEN: Record<Mode, Pair[]> = {
  light: [
    ["--hong", "--bg"], // 3.83: --hong is a fill, pink text is --hong-text
    ["--hong", "--plum"], // pink never sits on the field; the button there is --on-plum-action
  ],
  dark: [],
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

// V22: the "pink" surface is the flat --hong-tint tile (the landing's nx lists): text and focus on
// it, and the highlighter (--hl, --hl-band) under ink, which is what the one motif is made of.
describe.each(["light", "dark"] as const)("%s tile", (mode) => {
  it.each([
    ["--on-surface-hong", 4.5],
    ["--hong-soft-text", 4.5],
  ] as const)("%s on --hong-tint", (fg, limit) => {
    expect(contrast(palette(mode), fg, "--hong-tint")).toBeGreaterThanOrEqual(limit);
  });
  it("--focus-on-hong reads on a --hong fill (direction §F1)", () => {
    expect(contrast(palette(mode), "--focus-on-hong", "--hong")).toBeGreaterThanOrEqual(3);
  });
  it("--ink reads on the highlighter band under an h1 phrase (≥ 4.5)", () => {
    expect(contrast(palette(mode), "--ink", "--hl", "--bg")).toBeGreaterThanOrEqual(4.5);
    expect(contrast(palette(mode), "--ink", "--hl-band", "--bg")).toBeGreaterThanOrEqual(4.5);
  });
  it("the cam row (--cam-tint) keeps its text and its --cam label readable", () => {
    const t = palette(mode);
    const row = t["--cam-tint"]; // the "suggested" row is the opaque --cam-tint tile, as in nx-list.tsx
    expect(contrastOn(t, "--ink", row)).toBeGreaterThanOrEqual(4.5);
    expect(contrastOn(t, "--cam", row)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("--elev-sheet keeps a hairline", () => {
  it.each(["light", "dark"] as const)("%s: a card shadow is never none", (mode) => {
    expect(palette(mode)["--elev-sheet"]).not.toBe("none");
    expect(palette(mode)["--elev-sheet"]).toMatch(/var\(--line\)/);
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
    expect([count(TEXT), count(EDGES), count(FORBIDDEN)]).toEqual([123, 35, 2]);
  });

  it("matches the v4 spec on a few exact values, to catch a mistyped hex", () => {
    const light = palette("light");
    const dark = palette("dark");
    expect(contrast(light, "--hong", "--bg")).toBeCloseTo(3.83, 1); // why pink text is --hong-text
    expect(contrast(light, "--hong-text", "--bg")).toBeCloseTo(5.33, 1);
    expect(contrast(light, "--on-hong", "--hong")).toBeCloseTo(4.68, 1);
    expect(contrast(light, "--on-accent", "--accent")).toBeCloseTo(6.55, 1);
    expect(contrast(light, "--ink", "--hl")).toBeGreaterThan(10.5);
    expect(contrast(dark, "--on-hong", "--hong")).toBeCloseTo(7.72, 1);
    expect(light["--field"]).toBe("#661738");
    expect(dark["--field"]).toBe("#4e152f");
    expect(light["--inverse-bg"]).toBe("#ffffff");
    expect(dark["--inverse-bg"]).toBe("#1a0e14");
    expect(dark["--inverse-fg"]).toBe("#ff77ad");
  });
});

describe("palette copies", () => {
  it("the OS-dark block declares exactly what the data-theme dark block does", () => {
    expect(osDarkPalette()).toEqual(palette("dark"));
  });

  it("light and dark declare the same tokens", () => {
    expect(Object.keys(palette("dark")).sort()).toEqual(Object.keys(palette("light")).sort());
  });

  it("no --right is left; --cam is the one second colour (V22 decisions #9)", () => {
    for (const mode of ["light", "dark"] as const) {
      expect(Object.keys(palette(mode))).toContain("--cam");
      expect(Object.keys(palette(mode))).not.toContain("--right");
    }
  });
});
