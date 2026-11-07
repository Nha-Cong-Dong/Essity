// @vitest-environment jsdom
// C4C (RUN-0711, mockups/graph.html): a card is a solid dot with a ground-coloured rim, the picked
// one is the dark fill with an ink ring, and labels carry a ground halo. Red when: a dot goes
// back to an empty ring, the picked card loses its fill, or a label can sink into the lines.
import { describe, expect, it } from "vitest";

import { createFitLock } from "@/lib/graph-fit-lock";
import { dotImage, graphStylesheet, type Palette } from "@/lib/graph-style";

const p: Palette = { ink: "#2e1720", line: "#8f6676", sheet: "#ffffff", focus: "#ae2363", soft: "#6d4e59", hong: "#d1347a", now: "#891b4c", bg: "#fde6ed" };
const svg = (selected: boolean) => decodeURIComponent(dotImage(p, selected).split(",").slice(1).join(","));

describe("graph node style", () => {
  // Red when: a card loses its label at some zoom, or a long label is cut with an ellipsis again.
  it("every card shows its full label at any zoom, wrapped and never cut with an ellipsis", () => {
    for (const zoom of [0.4, 0.8, 1, 2]) {
      const rule = (graphStylesheet(p, zoom).find((r) => r.selector === "node.card") as unknown as { style: Record<string, unknown> }).style;
      expect(rule.label).toBe("data(label)");
      expect(rule["text-wrap"]).toBe("wrap");
      expect(rule["text-max-width"]).toBeTruthy();
    }
    expect(JSON.stringify(graphStylesheet(p, 1))).not.toContain("ellipsis");
  });
  it("a card dot is filled with --hong and rimmed with the ground", () => {
    const s = svg(false);
    expect(s).toContain(`fill='${p.hong}'`);
    expect(s).toContain(`stroke='${p.bg}'`);
    expect(s).not.toContain(`fill='${p.sheet}'`);
  });
  it("the picked card is filled with --now, ringed in ink and in the focus colour", () => {
    const s = svg(true);
    expect(s).toContain(`fill='${p.now}'`);
    expect(s).toContain(`stroke='${p.ink}'`);
    expect(s).toContain(`stroke='${p.focus}'`);
  });
  it("labels have a ground halo that keeps its pixel width at any zoom", () => {
    for (const zoom of [0.5, 1, 2]) {
      const card = (graphStylesheet(p, zoom).find((r) => r.selector === "node.card") as unknown as { style: Record<string, unknown> }).style;
      expect(card["text-outline-color"]).toBe(p.bg);
      expect((card["text-outline-width"] as number) * zoom).toBeCloseTo(3, 6);
    }
  });
});

describe("fit lock (review #280)", () => {
  const touch = (n: number) => Object.assign(new Event("touchstart"), { touches: Array.from({ length: n }) });
  it("starts free, and a wheel turn takes the view", () => {
    const el = document.createElement("div");
    const lock = createFitLock();
    lock.attach(el);
    expect(lock.touched).toBe(false);
    el.dispatchEvent(new Event("wheel"));
    expect(lock.touched).toBe(true);
  });
  it("a two-finger pinch locks, one finger (a tap or a drag) does not", () => {
    const el = document.createElement("div");
    const lock = createFitLock();
    lock.attach(el);
    el.dispatchEvent(touch(1));
    expect(lock.touched).toBe(false);
    el.dispatchEvent(touch(2));
    expect(lock.touched).toBe(true);
  });
  it("lock() (the zoom buttons, dragpan) locks and reset() frees it for 'Đặt lại'", () => {
    const lock = createFitLock();
    lock.lock();
    expect(lock.touched).toBe(true);
    lock.reset();
    expect(lock.touched).toBe(false);
  });
  it("after detach the frame no longer locks", () => {
    const el = document.createElement("div");
    const lock = createFitLock();
    lock.attach(el)();
    el.dispatchEvent(new Event("wheel"));
    expect(lock.touched).toBe(false);
  });
});
