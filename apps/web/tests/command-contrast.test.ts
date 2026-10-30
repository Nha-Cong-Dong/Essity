// T9.3a (US-18; WCAG 1.4.3, 1.4.11): the tray sits on --sunken. Red when: a palette change drops
// the text under 4.5:1 or the quiet-button line / decorative mark under 3:1 on it.
import { describe, expect, it } from "vitest";

import { contrast, osDarkPalette, palette, type Mode, type Tokens } from "./css-tokens";

const PALETTES: [string, () => Tokens][] = [
  ["light", () => palette("light" as Mode)],
  ["dark", () => palette("dark" as Mode)],
  ["os-dark", () => ({ ...palette("light" as Mode), ...osDarkPalette() })],
];

describe.each(PALETTES)("tray on --sunken, %s", (_name, tokens) => {
  const t = tokens();
  it("ink and ink-soft text reach 4.5:1", () => {
    expect(contrast(t, "--ink", "--sunken")).toBeGreaterThanOrEqual(4.5);
    expect(contrast(t, "--ink-soft", "--sunken")).toBeGreaterThanOrEqual(4.5);
  });
  it("the --partial mark and the strong line reach 3:1", () => {
    expect(contrast(t, "--partial", "--sunken")).toBeGreaterThanOrEqual(3);
    expect(contrast(t, "--line-strong", "--sunken")).toBeGreaterThanOrEqual(3);
  });
});
