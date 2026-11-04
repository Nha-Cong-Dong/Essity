// UI-A (ux-critic 05/11): the small text of the "suggested" (cam) row and of the tile hint reaches 4.5:1.
// Measured: light cam on its row 4.93, ink on the row 13.6, ink-soft on --hong-tint 6.84; dark 6.48 / 12.3 / 7.9.
import { describe, expect, it } from "vitest";

import { contrast, osDarkPalette, palette, type Mode, type Tokens } from "./css-tokens";

const PALETTES: [string, () => Tokens][] = [
  ["light", () => palette("light" as Mode)],
  ["dark", () => palette("dark" as Mode)],
  ["os-dark", () => ({ ...palette("light" as Mode), ...osDarkPalette() })],
];

describe.each(PALETTES)("suggested row and tile hint, %s", (_name, tokens) => {
  const t = { ...tokens(), "--cam-row": "color-mix(in srgb, var(--cam) 15%, transparent)" };
  it("cam text on the cam row is at least 4.5:1", () => {
    expect(contrast(t, "--cam", "--cam-row", "--bg")).toBeGreaterThanOrEqual(4.5);
  });
  it("ink on the cam row and ink-soft on the pink tile are at least 4.5:1", () => {
    expect(contrast(t, "--ink", "--cam-row", "--bg")).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t, "--ink-soft", "--hong-tint")).toBeGreaterThanOrEqual(4.5);
  });
});
