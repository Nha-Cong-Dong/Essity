// V16/V17: several subjects in one graph, one colour each.
import { describe, expect, it } from "vitest";

import { colorOf, mergeGraphs, SUBJECT_COLORS } from "@/lib/graph-multi";
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
