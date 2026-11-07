// LANDING-V62-FIX: the landing graph is a full, linked cluster (like a vault graph view): no loose node, no bad index,
// nodes sized by how connected they are, only a few accent nodes.
import { describe, expect, it } from "vitest";

import { GRAPH_CARDS, GRAPH_HUBS, GRAPH_RELATIONS, graphLayout, graphModel, nodeRadius } from "@/components/landing/graph-data";

describe("landing graph model", () => {
  const { nodes, links } = graphModel();

  it("is dense enough to read as a cluster: about 45 notes", () => {
    expect(nodes.length).toBe(GRAPH_HUBS.length + GRAPH_CARDS.length);
    expect(nodes.length).toBeGreaterThanOrEqual(40);
    expect(nodes.length).toBeLessThanOrEqual(60);
  });

  it("every relation points at real cards, never at itself, never twice", () => {
    const seen = new Set<string>();
    for (const [a, b] of GRAPH_RELATIONS) {
      expect(a).toBeGreaterThanOrEqual(0);
      expect(b).toBeGreaterThanOrEqual(0);
      expect(a).toBeLessThan(GRAPH_CARDS.length);
      expect(b).toBeLessThan(GRAPH_CARDS.length);
      expect(a).not.toBe(b);
      const k = a < b ? `${a}-${b}` : `${b}-${a}`;
      expect(seen.has(k)).toBe(false);
      seen.add(k);
    }
  });

  it("has no loose node: every note has at least two links and the whole graph is one piece", () => {
    nodes.forEach((n) => expect(n.degree).toBeGreaterThanOrEqual(n.hub ? 8 : 2));
    const adj = nodes.map(() => [] as number[]);
    links.forEach((l) => {
      adj[l.a].push(l.b);
      adj[l.b].push(l.a);
    });
    const seen = new Set([0]);
    const stack = [0];
    while (stack.length) for (const m of adj[stack.pop() as number]) if (!seen.has(m)) (seen.add(m), stack.push(m));
    expect(seen.size).toBe(nodes.length);
  });

  it("size follows centrality: hubs biggest, then more links means a bigger ring", () => {
    expect(nodeRadius(10, false)).toBeGreaterThan(nodeRadius(2, false));
    expect(nodeRadius(2, true)).toBeGreaterThan(nodeRadius(12, false));
    const hubMin = Math.min(...nodes.filter((n) => n.hub).map((n) => n.r));
    const cardMax = Math.max(...nodes.filter((n) => !n.hub).map((n) => n.r));
    expect(hubMin).toBeGreaterThan(cardMax);
  });

  it("accents are rare: three accent nodes, none of them a hub", () => {
    const acc = nodes.filter((n) => n.accent);
    expect(acc.map((n) => n.accent).sort()).toEqual(["gold", "rose", "teal"]);
    expect(acc.some((n) => n.hub)).toBe(false);
  });

  it("the layout is a round cluster inside the unit disc, hubs near the middle, deterministic, no two notes on the same spot", () => {
    const pos = graphLayout(nodes);
    expect(pos).toEqual(graphLayout(nodes));
    pos.forEach((p) => expect(Math.hypot(p.x, p.y)).toBeLessThanOrEqual(1));
    nodes.forEach((n, i) => n.hub && expect(Math.hypot(pos[i].x, pos[i].y)).toBeLessThan(0.5));
    for (let i = 0; i < pos.length; i++) for (let j = i + 1; j < pos.length; j++) expect(Math.hypot(pos[i].x - pos[j].x, pos[i].y - pos[j].y)).toBeGreaterThan(0.02);
  });
});
