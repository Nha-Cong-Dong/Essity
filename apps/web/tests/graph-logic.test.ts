// T9.10a (US-19 AC1-AC4; DESIGN §6.15): the pure graph view.
import { describe, expect, it } from "vitest";

import { graphFixture, GRAPH_STATE_IDS } from "@/lib/fixtures/graph";
import {
  EDGE_KINDS,
  EDGE_STYLE,
  MAX_NODES,
  neighbourhood,
  sectionScope,
  shortLabel,
  suggestList,
  viewGraph,
  type EdgeKind,
} from "@/lib/graph";

const ALL = new Set<EdgeKind>(EDGE_KINDS);
const few = () => graphFixture("few").data!;

describe("edge kinds", () => {
  // Red when: a "related" catch-all kind appears, or two kinds share a stroke and a word.
  it("US-19 AC1: five kinds, no generic one, each told apart by stroke and word", () => {
    expect(EDGE_KINDS).toEqual(["prerequisite", "part_of", "example_of", "contrast", "applies_to"]);
    const looks = EDGE_KINDS.map((k) => JSON.stringify([EDGE_STYLE[k].dash, EDGE_STYLE[k].arrow, EDGE_STYLE[k].width]));
    expect(new Set(looks).size).toBe(5);
    expect(new Set(EDGE_KINDS.map((k) => EDGE_STYLE[k].label)).size).toBe(5);
  });
  it("US-19 AC3: strokes are at least 2 px, except part_of which has its diamond end", () => {
    for (const k of EDGE_KINDS) {
      if (k !== "part_of") expect(EDGE_STYLE[k].width).toBeGreaterThanOrEqual(2);
    }
    expect(EDGE_STYLE.part_of.arrow).toBe("diamond");
  });
});

describe("viewGraph", () => {
  // Red when: the list and the canvas could read different data.
  it("US-19 AC3: one view holds the cards and edges both forms show", () => {
    const v = viewGraph(few(), "ch1", ALL);
    expect(v.cards).toHaveLength(5);
    expect(v.edges).toHaveLength(6);
  });
  // Red when: a section filter leaves out a child section, or lets another chapter in.
  it("US-19 AC3: a section includes its descendants and no other chapter", () => {
    const data = { ...few(), cards: [...few().cards, { ...few().cards[0]!, id: "x", sectionId: "ch2-1" }] };
    expect(sectionScope(data.sections, "ch1")).toEqual(new Set(["ch1", "ch1-1", "ch1-2"]));
    expect(viewGraph(data, "ch1", ALL).cards.map((c) => c.id)).not.toContain("x");
    expect(viewGraph(data, null, ALL).cards.map((c) => c.id)).toContain("x");
  });
  // Red when: an edge with no evidence is drawn or listed (principle 7: no evidence, no edge).
  it("US-19 AC2: an edge without evidence is not shown", () => {
    const data = { ...few(), edges: [...few().edges, { id: "bad", kind: "part_of" as const, from: "c1", to: "c3", evidence: "  " }] };
    expect(viewGraph(data, "ch1", ALL).edges.map((e) => e.id)).not.toContain("bad");
  });
  // Red when: an edge to a card outside the view dangles, or a self loop is drawn.
  it("US-19 AC3: edges join cards that are both in the view", () => {
    const data = {
      ...few(),
      edges: [...few().edges, { id: "far", kind: "contrast" as const, from: "c1", to: "gone", evidence: "q" }, { id: "self", kind: "contrast" as const, from: "c1", to: "c1", evidence: "q" }],
    };
    const ids = viewGraph(data, "ch1", ALL).edges.map((e) => e.id);
    expect(ids).not.toContain("far");
    expect(ids).not.toContain("self");
  });
  // Red when: turning a kind off drops cards, or keeps its edges.
  it("US-19 AC3: filtering by kind keeps every card and only that kind's edges", () => {
    const v = viewGraph(few(), "ch1", new Set<EdgeKind>(["prerequisite"]));
    expect(v.cards).toHaveLength(5);
    expect(v.edges.map((e) => e.kind)).toEqual(["prerequisite", "prerequisite"]);
    expect(v.unlinked).toEqual(new Set(["c3", "c5"]));
  });
  // Red when: the cap is not 300, or the count of hidden cards is wrong.
  it("US-19 AC3: at most 300 cards; the rest is counted", () => {
    const v = viewGraph(graphFixture("many").data!, "ch2", ALL);
    expect(v.cards).toHaveLength(MAX_NODES);
    expect(v.hidden).toBe(20);
    expect(v.edges.every((e) => v.cards.some((c) => c.id === e.from) && v.cards.some((c) => c.id === e.to))).toBe(true);
  });
});

describe("neighbourhood", () => {
  // Red when: depth 1 reaches two steps away, or a link is followed one way only.
  it("US-19 AC4: 1 and 2 steps, either direction", () => {
    const edges = viewGraph(few(), "ch1", ALL).edges;
    const one = neighbourhood(edges, "c2", 1);
    expect(one.get("c1")).toBe(1); // c1 -> c2, followed backwards
    expect(one.get("c4")).toBe(1);
    expect(one.has("c3")).toBe(false);
    expect(neighbourhood(edges, "c2", 2).get("c3")).toBe(2);
  });
});

describe("helpers", () => {
  it("suggests the list sooner on a narrow frame, and never flips anything itself", () => {
    expect(suggestList(21, 320)).toBe(true);
    expect(suggestList(20, 320)).toBe(false);
    expect(suggestList(30, 800)).toBe(false);
    expect(suggestList(41, 800)).toBe(true);
  });
  it("cuts a canvas label at 24 characters, diacritics intact", () => {
    expect(shortLabel("Điều khiển luồng")).toBe("Điều khiển luồng");
    const cut = shortLabel("Số thứ tự và xác nhận trong giao thức");
    expect([...cut]).toHaveLength(24);
    expect(cut.endsWith("…")).toBe(true);
  });
  it("every state has a fixture", () => {
    for (const s of GRAPH_STATE_IDS) expect(graphFixture(s).status).toBeDefined();
  });
});
