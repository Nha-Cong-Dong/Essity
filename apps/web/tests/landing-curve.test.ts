import { describe, expect, it } from "vitest";

import { fsrsCurve } from "@/components/landing/fsrs-curve";

describe("landing FSRS curve geometry", () => {
  const c = fsrsCurve();

  it("starts at full memory and stays inside the 900 x 300 box", () => {
    expect(c.d.startsWith("M0.0 30.0")).toBe(true);
    const ys = [...c.d.matchAll(/[ML][\d.]+ ([\d.]+)/g)].map((m) => Number(m[1]));
    expect(Math.max(...ys)).toBeLessThanOrEqual(300);
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(30);
  });

  it("marks three reviews, each later than the last and each after a longer gap", () => {
    expect(c.dots).toHaveLength(3);
    const gaps = [c.dots[0], c.dots[1] - c.dots[0], c.dots[2] - c.dots[1]];
    expect(gaps[1]).toBeGreaterThan(gaps[0]);
    expect(gaps[2]).toBeGreaterThan(gaps[1]);
    expect(c.dots[2]).toBeLessThan(c.width);
  });

  it("the trough (circled in the demo) is the lowest point of a gap, right where the third review lands", () => {
    expect(c.trough.x).toBe(c.dots[2]);
    expect(c.trough.y).toBeGreaterThan(150); // low on the curve, not at the top where the old ring sat
    expect(c.trough.y).toBeLessThan(300);
    const before = [...c.d.matchAll(/[ML]([\d.]+) ([\d.]+)/g)].map((m) => [Number(m[1]), Number(m[2])]).filter(([x]) => x < c.trough.x - 0.9);
    expect(Math.abs(before[before.length - 1][1] - c.trough.y)).toBeLessThan(1);
  });
});
