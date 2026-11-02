import type { components } from "@/lib/core-client";
import type { GraphCard, GraphData, GraphEdge } from "@/lib/graph";

// T9.10 (US-19 AC3, AC4): core-api's graph (T9.10 endpoint) as the shape the T9.10a screen reads.
// Pure, no server-only import: the screen is a client component.

export type GraphOut = components["schemas"]["GraphOut"];
type AnchorOut = components["schemas"]["GraphAnchorOut"];

/** "Giáo trình, trang 12"; a note has no document. */
export function anchorLabel(a: Pick<AnchorOut, "document_name" | "page_no">): string {
  if (a.document_name === null) return "Ghi chú";
  return a.page_no === null ? a.document_name : `${a.document_name}, trang ${a.page_no}`;
}

export function toGraphData(out: GraphOut): GraphData {
  const cards: GraphCard[] = out.cards.map((c) => ({
    id: c.id,
    title: c.title,
    body: c.summary,
    // "" is a card in no section: it is in the whole-subject view only.
    sectionId: c.section_id ?? "",
    anchors: c.anchors.map((a) => ({ id: a.id, label: anchorLabel(a), quote: a.quote })),
    neededBy: c.needed_by,
  }));
  const edges: GraphEdge[] = out.edges.map((e) => ({
    id: e.id,
    kind: e.kind,
    from: e.from_id,
    to: e.to_id,
    // The screen shows one quote line per link; an edge the learner added has none and is not drawn.
    evidence: e.evidence.map((q) => q.quote).join(" … "),
  }));
  return {
    sections: out.sections.map((s) => ({ id: s.id, title: s.title, parentId: s.parent_id })),
    cards,
    edges,
    hidden: out.hidden,
  };
}
