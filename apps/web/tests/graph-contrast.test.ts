// T9.10a (US-19 AC3; WCAG 1.4.11, 1.4.3): the graph's ink on --sheet in every palette, and the
// stylesheet's promises. Red when: a faded stroke drops under 3:1, the filter chip text loses
// 4.5:1 on its ground, the 44 px hit box shrinks with zoom, or a stroke gets thinner than 2 px.
import { describe, expect, it } from "vitest";

import { EDGE_KINDS, EDGE_STYLE } from "@/lib/graph";
import { graphStylesheet, HIT, type Palette } from "@/lib/graph-style";

import { contrast, osDarkPalette, palette, type Mode, type Tokens } from "./css-tokens";

const PALETTES: [string, () => Tokens][] = [
  ["light", () => palette("light" as Mode)],
  ["dark", () => palette("dark" as Mode)],
  ["os-dark", () => ({ ...palette("light" as Mode), ...osDarkPalette() })],
];

describe.each(PALETTES)("graph tokens, %s", (_name, tokens) => {
  const t = tokens();
  it("AC3: ink strokes at the faded opacity (.5) still reach 3:1 on the sheet", () => {
    const faded = { ...t, "--faded": "color-mix(in srgb, var(--ink) 50%, transparent)" };
    expect(contrast(faded, "--faded", "--sheet")).toBeGreaterThanOrEqual(3);
  });
  it("AC3: chip text is ink on --rose-100 and on --sheet at 4.5:1", () => {
    expect(contrast(t, "--ink", "--rose-100")).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t, "--ink", "--sheet")).toBeGreaterThanOrEqual(4.5);
  });
  it("AC3: chip and switch borders (--line-strong) reach 3:1", () => {
    expect(contrast(t, "--line-strong", "--sheet")).toBeGreaterThanOrEqual(3);
    expect(contrast(t, "--line-strong", "--rose-100")).toBeGreaterThanOrEqual(3);
  });
});

describe("graphStylesheet", () => {
  const p: Palette = { ink: "#000", line: "#888", sheet: "#fff", focus: "#a00", soft: "#555" };
  const rule = (sheet: ReturnType<typeof graphStylesheet>, selector: string) =>
    (sheet.find((r) => r.selector === selector) as unknown as { style: Record<string, unknown> }).style;

  it("AC3: the card hit box is 44 px at any zoom", () => {
    for (const zoom of [0.2, 0.5, 1, 2, 3]) {
      expect(rule(graphStylesheet(p, zoom), "node.card").width).toBeCloseTo(HIT / zoom, 6);
    }
  });
  it("AC3: every stroke is at least 2 px on screen (1.5 px for part_of, which has its diamond end)", () => {
    for (const zoom of [0.2, 1, 3]) {
      for (const kind of EDGE_KINDS) {
        const onScreen = (rule(graphStylesheet(p, zoom), `edge.${kind}`).width as number) * zoom;
        expect(onScreen).toBeCloseTo(EDGE_STYLE[kind].width, 6);
      }
    }
  });
  it("AC3: the faded part is opacity .5 and nothing fades the labels", () => {
    const sheet = graphStylesheet(p, 1);
    expect(rule(sheet, "edge.far, node.card.far").opacity).toBe(0.5);
    expect(JSON.stringify(sheet)).not.toMatch(/text-opacity|label-opacity/);
  });
  it("AC3: five kinds, five different dash patterns or end shapes", () => {
    const looks = EDGE_KINDS.map((k) => {
      const s = rule(graphStylesheet(p, 1), `edge.${k}`);
      return JSON.stringify([s["line-dash-pattern"], s["target-arrow-shape"], s["source-arrow-shape"]]);
    });
    expect(new Set(looks).size).toBe(5);
  });
});
