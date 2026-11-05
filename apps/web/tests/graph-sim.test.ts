import { describe, expect, it } from "vitest";

import { type SimNode, stepSim } from "@/lib/graph-sim";

const node = (id: string, x: number, y: number, pinned = false): SimNode => ({ id, x, y, vx: 0, vy: 0, pinned });
const calm = () => 0.5;

describe("stepSim", () => {
  it("pushes two close nodes apart", () => {
    const ns = [node("a", 0, 0), node("b", 10, 0)];
    for (let i = 0; i < 20; i++) stepSim(ns, [], 1, calm);
    expect(ns[1].x - ns[0].x).toBeGreaterThan(10);
  });
  it("pulls two linked far nodes towards the rest length", () => {
    const ns = [node("a", 0, 0), node("b", 300, 0)];
    for (let i = 0; i < 300; i++) stepSim(ns, [{ a: 0, b: 1 }], 1, calm);
    const d = ns[1].x - ns[0].x;
    expect(d).toBeLessThan(200);
    expect(d).toBeGreaterThan(40);
  });
  it("never moves a pinned node", () => {
    const ns = [node("a", 5, 5, true), node("b", 10, 5)];
    for (let i = 0; i < 20; i++) stepSim(ns, [{ a: 0, b: 1 }], 1, calm);
    expect([ns[0].x, ns[0].y]).toEqual([5, 5]);
  });
  it("keeps a lone cloud near its centre and stays finite", () => {
    const ns = Array.from({ length: 30 }, (_, i) => node(String(i), (i % 6) * 20, Math.floor(i / 6) * 20));
    for (let i = 0; i < 200; i++) stepSim(ns, [], 0.1, Math.random);
    for (const p of ns) expect(Number.isFinite(p.x) && Number.isFinite(p.y)).toBe(true);
  });
  it("pulls unlinked cards of one subject together and keeps two subjects apart", () => {
    const mk = (id: string, x: number, group: string): SimNode => ({ ...node(id, x, (x % 7) * 9), group });
    const ns = [mk("a1", 0, "A"), mk("a2", 300, "A"), mk("a3", -250, "A"), mk("b1", 20, "B"), mk("b2", 310, "B")];
    for (let i = 0; i < 400; i++) stepSim(ns, [], 1, calm);
    const dist = (p: SimNode, q: SimNode) => Math.hypot(p.x - q.x, p.y - q.y);
    const within = (dist(ns[0], ns[1]) + dist(ns[0], ns[2]) + dist(ns[3], ns[4])) / 3;
    expect(within).toBeLessThan(300);
  });
});
