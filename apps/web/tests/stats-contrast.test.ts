// T9.5a (US-10 AC4, AC6; WCAG 1.4.11): the four tints of the activity grid, measured on --sheet in
// every palette. Red when: a tint drops under 3:1 (a day with little work becomes invisible), two
// neighbouring tints merge, or the empty-day hairline fades further.
import { describe, expect, it } from "vitest";

import { contrast, osDarkPalette, palette, type Mode, type Tokens } from "./css-tokens";

const PALETTES: [string, () => Tokens][] = [
  ["light", () => palette("light" as Mode)],
  ["dark", () => palette("dark" as Mode)],
  ["os-dark", () => ({ ...palette("light" as Mode), ...osDarkPalette() })],
];

describe.each(PALETTES)("grid tints, %s", (_name, tokens) => {
  const t = tokens();
  const LEVELS = ["--grid-1", "--grid-2", "--grid-3", "--grid-4"];

  it("AC4: every tint reaches 3:1 on the sheet", () => {
    for (const level of LEVELS) expect(contrast(t, level, "--sheet")).toBeGreaterThanOrEqual(3);
  });

  it("AC4: neighbouring tints differ by at least 1.2:1", () => {
    for (let i = 1; i < LEVELS.length; i++) {
      // Both tints sit on the same side of the sheet, so their ratio is the ratio of the two
      // contrasts against it.
      const [a, b] = [contrast(t, LEVELS[i], "--sheet"), contrast(t, LEVELS[i - 1], "--sheet")];
      expect(Math.max(a, b) / Math.min(a, b)).toBeGreaterThanOrEqual(1.2);
    }
  });

  it("AC6: the empty-day hairline keeps its floor and the ink ring is strong", () => {
    expect(contrast(t, "--line", "--sheet")).toBeGreaterThanOrEqual(1.2);
    expect(contrast(t, "--ink", "--sheet")).toBeGreaterThanOrEqual(7);
  });
});
