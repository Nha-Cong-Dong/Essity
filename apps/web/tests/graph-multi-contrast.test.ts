// V4 graph: the colours of the subjects in one picture (lib/graph-multi.ts SUBJECT_COLORS).
// The graph is drawn on --sheet, which is white in the light palette and #22151a in the dark one,
// and the same four tones serve both. Red when: a tone drops under 3:1 on either sheet (WCAG
// 1.4.11 — a node's fill carries meaning, so it is not decoration), or two tones land close
// together in CIELAB and read as one colour, which is what the earlier lightness-only tones did.
import { describe, expect, it } from "vitest";

import { SUBJECT_COLORS } from "@/lib/graph-multi";
import { contrast, palette, type Mode, type Tokens } from "./css-tokens";

/** Contrast of a literal hex on another literal hex, through the token reader the other tests use. */
function ratio(foreground: string, background: string): number {
  const tokens: Tokens = { "--fg": foreground, "--bg": background };
  return contrast(tokens, "--fg", "--bg");
}

/** A colour as a point in CIELAB (D65): the space a person's eye is roughly linear in. */
function lab(hex: string): [number, number, number] {
  const channel = (offset: number) => {
    const c = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const [r, g, b] = [channel(1), channel(3), channel(5)];
  const f = (t: number) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const x = f((0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047);
  const y = f(0.2126 * r + 0.7152 * g + 0.0722 * b);
  const z = f((0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883);
  return [116 * y - 16, 500 * (x - y), 200 * (y - z)];
}

/** CIE76: the plain distance between two colours in CIELAB. ~2.3 is the just-noticeable step. */
function distance(a: string, b: string): number {
  const [one, two] = [lab(a), lab(b)];
  return Math.hypot(one[0] - two[0], one[1] - two[1], one[2] - two[2]);
}

describe.each(["light", "dark"] as Mode[])("subject colours, %s palette", (mode) => {
  const tokens = palette(mode);

  it("each tone clears 3:1 on the sheet it is drawn on", () => {
    for (const colour of SUBJECT_COLORS) {
      expect(ratio(colour, tokens["--sheet"])).toBeGreaterThanOrEqual(3);
    }
  });

  it("no two subjects are close enough in CIELAB to read as one colour", () => {
    for (let i = 0; i < SUBJECT_COLORS.length; i++) {
      for (let j = i + 1; j < SUBJECT_COLORS.length; j++) {
        expect(distance(SUBJECT_COLORS[i], SUBJECT_COLORS[j])).toBeGreaterThanOrEqual(25);
      }
    }
  });
});