// T9.10 (US-19 AC3, AC4): core-api's graph as the shape the screen reads.
import { describe, expect, it } from "vitest";

import { viewGraph, EDGE_KINDS } from "@/lib/graph";
import { anchorLabel, toGraphData, type GraphOut } from "@/lib/graph-live";

const OUT: GraphOut = {
  sections: [
    { id: "s1", parent_id: null, title: "Chương 1" },
    { id: "s2", parent_id: "s1", title: "1.1" },
  ],
  cards: [
    {
      id: "a",
      title: "A",
      summary: "tóm tắt",
      section_id: "s2",
      anchors: [{ id: "x", document_name: "Giáo trình", page_no: 12, quote: "trích A" }],
      needed_by: ["Vì sao A?"],
    },
    { id: "b", title: "B", summary: "s", section_id: null, anchors: [], needed_by: [] },
  ],
  edges: [
    { id: "e1", kind: "prerequisite", from_id: "a", to_id: "b", evidence: [{ unit_id: "a", quote: "q1" }, { unit_id: "b", quote: "q2" }] },
    { id: "e2", kind: "part_of", from_id: "b", to_id: "a", evidence: [] },
  ],
  hidden: 4,
  truncated: true,
};

describe("AC3 AC4 graph from core-api", () => {
  // Red when: a card loses its section, anchors or the questions that need it.
  it("AC4 maps cards with their place, anchors and questions", () => {
    const data = toGraphData(OUT);
    expect(data.cards[0]).toMatchObject({ id: "a", body: "tóm tắt", sectionId: "s2", neededBy: ["Vì sao A?"] });
    expect(data.cards[0]!.anchors).toEqual([{ id: "x", label: "Giáo trình, trang 12", quote: "trích A" }]);
    expect(data.cards[1]!.sectionId).toBe("");
    expect(data.sections[1]).toEqual({ id: "s2", title: "1.1", parentId: "s1" });
  });

  // Red when: the evidence of a link is lost, or an edge with none (a learner's own) is drawn.
  it("AC4 joins the quotes of an edge; an edge with none is not in the view", () => {
    const data = toGraphData(OUT);
    expect(data.edges[0]!.evidence).toBe("q1 … q2");
    const view = viewGraph(data, null, new Set(EDGE_KINDS));
    expect(view.edges.map((e) => e.id)).toEqual(["e1"]);
  });

  // Red when: the cards core-api left out are not counted in the neutral message.
  it("AC3 carries the cards core-api left out into the view's hidden count", () => {
    expect(viewGraph(toGraphData(OUT), null, new Set(EDGE_KINDS)).hidden).toBe(4);
  });

  it("AC4 names a note and a document without a page", () => {
    expect(anchorLabel({ document_name: null, page_no: null })).toBe("Ghi chú");
    expect(anchorLabel({ document_name: "Slide", page_no: null })).toBe("Slide");
  });
});
