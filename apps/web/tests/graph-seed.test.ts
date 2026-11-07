import { describe, expect, it } from "vitest";

import { seededRandom, spiralStart } from "@/lib/graph-sim";

describe("graph seed", () => {
  it("same seed gives the same sequence, different seeds differ", () => {
    const a = seededRandom(7);
    const b = seededRandom(7);
    const xs = [a(), a(), a()];
    expect(xs).toEqual([b(), b(), b()]);
    expect(xs.every((v) => v >= 0 && v < 1)).toBe(true);
    expect(seededRandom(8)()).not.toBe(xs[0]);
  });
  it("spiral start is stable and spreads nodes apart", () => {
    expect(spiralStart(3)).toEqual(spiralStart(3));
    const pts = Array.from({ length: 30 }, (_, i) => spiralStart(i));
    const keys = new Set(pts.map((p) => `${Math.round(p.x)},${Math.round(p.y)}`));
    expect(keys.size).toBe(30);
  });
});
