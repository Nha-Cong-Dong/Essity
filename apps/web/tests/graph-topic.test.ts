// GRAPH-LANDING-STYLE: the in-app knowledge graph drawn like the landing one: a hub per topic,
// colour by topic, size by level (hub > card, card grows with its links, capped).
import { describe, expect, it } from "vitest";

import { nodeRadius } from "@/components/landing/graph-data";
import type { GraphCard, GraphData } from "@/lib/graph";
import { SUBJECT_COLORS } from "@/lib/graph-multi";
import { buildTopicGraph, nodeSize, tint } from "@/lib/graph-topic";

const card = (id: string, sectionId = ""): GraphCard => ({ id, title: id, body: "b", sectionId, anchors: [], neededBy: [] });
const edge = (from: string, to: string) => ({ id: `${from}-${to}`, kind: "prerequisite" as const, from, to, evidence: "q" });
const data = (cards: GraphCard[], edges: [string, string][] = [], sections: GraphData["sections"] = []): GraphData => ({
  sections,
  cards,
  edges: edges.map(([a, b]) => edge(a, b)),
});

describe("nodeSize", () => {
  it("a hub is bigger than any card, even the best connected", () => {
    expect(nodeSize(3, true)).toBeGreaterThan(nodeSize(40, false));
  });
  it("a card grows with its links and stops at a cap", () => {
    expect(nodeSize(4, false)).toBeGreaterThan(nodeSize(1, false));
    expect(nodeSize(60, false)).toBe(nodeSize(200, false));
  });
  it("follows the landing radius so the two graphs look alike", () => {
    expect(nodeSize(6, false)).toBeCloseTo(2 * nodeRadius(6, false) * 1.8, 5);
  });
  it("a card is never too small to see", () => {
    expect(nodeSize(0, false)).toBeGreaterThanOrEqual(16);
  });
});

describe("tint", () => {
  it("amount 0 is the background, 1 is the colour, in between mixes", () => {
    expect(tint("#d1347a", "#ffffff", 0)).toBe("#ffffff");
    expect(tint("#d1347a", "#ffffff", 1)).toBe("#d1347a");
    expect(tint("#000000", "#ffffff", 0.5)).toBe("#808080");
  });
  it("a light tint of a topic stays lighter than its ring on a light sheet", () => {
    const [r] = [tint("#7b57c4", "#ffffff", 0.3)].map((h) => parseInt(h.slice(1, 3), 16));
    expect(r).toBeGreaterThan(0x7b);
  });
});

describe("buildTopicGraph: all subjects", () => {
  const graphs = [
    { id: "s1", name: "A", data: data([card("a"), card("b"), card("c")], [["a", "b"], ["a", "c"]]) },
    { id: "s2", name: "B", data: data([card("d")]) },
  ];
  const g = buildTopicGraph(graphs, null);
  it("one topic and one hub per subject, coloured from the subject palette", () => {
    expect(g.topics.map((t) => [t.id, t.name, t.cards, t.color])).toEqual([
      ["s1", "A", 3, SUBJECT_COLORS[0]],
      ["s2", "B", 1, SUBJECT_COLORS[1]],
    ]);
    expect(g.nodes.filter((n) => n.hub).map((n) => n.topicId)).toEqual(["s1", "s2"]);
  });
  it("every card links to its hub, then the relations between cards follow", () => {
    expect(g.edges.filter((e) => e.own)).toHaveLength(4);
    expect(g.edges.filter((e) => !e.own)).toHaveLength(2);
  });
  it("degree counts both kinds of link; sizes follow the degree", () => {
    const by = new Map(g.nodes.map((n) => [n.id, n]));
    expect(by.get("a")!.degree).toBe(3);
    expect(by.get("d")!.degree).toBe(1);
    expect(by.get("a")!.size).toBeGreaterThan(by.get("d")!.size);
    expect(by.get("hub:s1")!.size).toBeGreaterThan(by.get("a")!.size);
  });
  it("hubs come first so the starting spiral is stable", () => {
    expect(g.nodes.slice(0, 2).every((n) => n.hub)).toBe(true);
  });
});

describe("buildTopicGraph: one focused subject", () => {
  const sections = [
    { id: "ch1", title: "Chương 1", parentId: null },
    { id: "ch1a", title: "1.1", parentId: "ch1" },
    { id: "ch2", title: "Chương 2", parentId: null },
  ];
  const graphs = [
    { id: "s1", name: "A", data: data([card("a", "ch1a"), card("b", "ch1"), card("c", "ch2"), card("d", "")], [], sections) },
    { id: "s2", name: "B", data: data([card("z")]) },
  ];
  const g = buildTopicGraph(graphs, "s1");
  it("topics are the top-level chapters; a nested section counts for its chapter", () => {
    expect(g.topics.map((t) => [t.name, t.cards])).toEqual([["Chương 1", 2], ["Chương 2", 1], ["Chưa vào chương nào", 1]]);
    expect(g.nodes.find((n) => n.id === "a")!.topicId).toBe("ch1");
  });
  it("other subjects are left out; chapters get distinct colours in order", () => {
    expect(g.nodes.some((n) => n.id === "z")).toBe(false);
    expect(g.topics.map((t) => t.color)).toEqual([SUBJECT_COLORS[0], SUBJECT_COLORS[1], SUBJECT_COLORS[2]]);
    expect(g.mode).toBe("chapter");
  });
  it("an unknown focus id falls back to the subject view", () => {
    expect(buildTopicGraph(graphs, "nope").mode).toBe("subject");
  });
  it("a subject with no chapters is one topic named after the subject", () => {
    const one = buildTopicGraph([{ id: "s2", name: "B", data: data([card("z")]) }], "s2");
    expect(one.topics.map((t) => t.name)).toEqual(["B"]);
  });
});
