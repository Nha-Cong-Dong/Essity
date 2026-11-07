// V16/V17: several subjects in one graph, one colour each.
import { describe, expect, it } from "vitest";

import { colorOf, hiddenExcept, mergeGraphs, SUBJECT_COLORS } from "@/lib/graph-multi";
import type { GraphCard, GraphData } from "@/lib/graph";

const card = (id: string): GraphCard => ({ id, title: id, body: "b", sectionId: "", anchors: [], neededBy: [] });
const data = (ids: string[], edges: [string, string][]): GraphData => ({
  sections: [],
  cards: ids.map(card),
  edges: edges.map(([from, to], i) => ({ id: `e${from}${to}${i}`, kind: "prerequisite", from, to, evidence: "q" })),
});

describe("mergeGraphs", () => {
  it("V16: each subject has its own colour and keeps its cards and edges", () => {
    const m = mergeGraphs([
      { id: "s1", name: "A", data: data(["a", "b"], [["a", "b"]]) },
      { id: "s2", name: "B", data: data(["c"], []) },
    ]);
    expect(m.subjects.map((s) => s.color)).toEqual([colorOf(0), colorOf(1)]);
    expect(m.cards.map((c) => [c.id, c.subjectId])).toEqual([["a", "s1"], ["b", "s1"], ["c", "s2"]]);
    expect(m.edges).toHaveLength(1);
  });
  it("V16: an edge to a card outside its subject is dropped; colours wrap around", () => {
    const m = mergeGraphs([{ id: "s1", name: "A", data: data(["a"], [["a", "zzz"]]) }]);
    expect(m.edges).toHaveLength(0);
    expect(colorOf(SUBJECT_COLORS.length)).toBe(colorOf(0));
  });
});

describe("hiddenExcept", () => {
  const subs = [{ id: "a" }, { id: "b" }, { id: "c" }];
  it("hides every subject but the focused one", () => {
    expect([...hiddenExcept(subs, "b")].sort()).toEqual(["a", "c"]);
  });
  it("shows everything for a missing or unknown id", () => {
    expect(hiddenExcept(subs, null).size).toBe(0);
    expect(hiddenExcept(subs, "zzz").size).toBe(0);
  });
});

describe("UI-NITS-0811: graph labels and first zoom", () => {
  it("UI-NITS-0811: a node label has no plate behind it, only a text halo in the canvas colour", async () => {
    const { multiStylesheet } = await import("@/lib/graph-multi-style");
    const node = (multiStylesheet("#111", "#ccc", "#f5f5f5").find((r) => (r as { selector?: string }).selector === "node") as unknown as { style: Record<string, unknown> }).style;
    expect(Object.keys(node).filter((k) => k.startsWith("text-background"))).toEqual([]);
    expect(node["text-outline-color"]).toBe("#f5f5f5");
    expect(Number(node["text-outline-width"])).toBeGreaterThan(0);
  });
  it("UI-NITS-0811: the first view is one zoom step (1.3x) smaller than the fitted one", async () => {
    const { readFileSync } = await import("node:fs");
    const path = await import("node:path");
    const src = readFileSync(path.join(__dirname, "../components/graph/knowledge-graph.tsx"), "utf8");
    expect((await import("@/lib/graph-multi-style")).INITIAL_ZOOM_STEP).toBe(1.3);
    expect(src).toMatch(/cy\.zoom\(\{ level: cy\.zoom\(\) \/ INITIAL_ZOOM_STEP/);
  });
});
