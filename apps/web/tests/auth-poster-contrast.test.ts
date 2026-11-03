// T1.24 (WCAG 1.4.3): the words on the auth poster stay readable in every palette, on the flat
// colour and on both glows painted over it. Red when: a palette change drops a pair under 4.5:1,
// or --poster / --on-poster / --glow-* goes missing from one of the three palette copies.
import { describe, expect, it } from "vitest";

import { contrast, osDarkPalette, palette, type Mode, type Tokens } from "./css-tokens";

const PALETTES: [string, () => Tokens][] = [
  ["light", () => palette("light" as Mode)],
  ["dark", () => palette("dark" as Mode)],
  ["os-dark", () => ({ ...palette("light" as Mode), ...osDarkPalette() })],
];

describe.each(PALETTES)("auth poster, %s", (_name, tokens) => {
  const t = tokens();
  it.each(["--poster", "--glow-a", "--glow-b"])("--on-poster on %s reaches 4.5:1", (bg) => {
    expect(contrast(t, "--on-poster", bg)).toBeGreaterThanOrEqual(4.5);
  });
});

describe("auth poster tokens", () => {
  it("dark values differ from light, and the dark copies agree", () => {
    const light = palette("light" as Mode);
    const dark = palette("dark" as Mode);
    const os = osDarkPalette();
    expect(dark["--poster"]).not.toBe(light["--poster"]);
    for (const name of ["--poster", "--on-poster", "--glow-a", "--glow-b"]) {
      expect(os[name]).toBe(dark[name]);
    }
  });
});
