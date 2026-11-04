import type { GraphCard, GraphData, GraphEdge } from "@/lib/graph";

// V16/V17: the graphs of several subjects in one picture. Each subject has its own colour; an edge
// only ever joins two cards of one subject (core-api builds the graph per subject).

/** Colours of the subjects in order; fixed so a subject keeps its colour on every visit. */
export const SUBJECT_COLORS = [
  "#d6336c",
  "#1c7ed6",
  "#2f9e44",
  "#f08c00",
  "#7048e8",
  "#0c8599",
  "#c2255c",
  "#5c940d",
] as const;

export type SubjectGraph = { id: string; name: string; data: GraphData };
export type MultiCard = GraphCard & { subjectId: string };
export type MultiGraph = {
  subjects: { id: string; name: string; color: string; cards: number }[];
  cards: MultiCard[];
  edges: GraphEdge[];
};

export function colorOf(index: number): string {
  return SUBJECT_COLORS[index % SUBJECT_COLORS.length];
}

export function mergeGraphs(list: SubjectGraph[]): MultiGraph {
  const cards: MultiCard[] = [];
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();
  for (const s of list) {
    for (const c of s.data.cards) {
      if (seen.has(c.id)) continue;
      seen.add(c.id);
      cards.push({ ...c, subjectId: s.id });
    }
    const own = new Set(s.data.cards.map((c) => c.id));
    for (const e of s.data.edges) if (own.has(e.from) && own.has(e.to) && e.from !== e.to) edges.push(e);
  }
  return {
    subjects: list.map((s, i) => ({ id: s.id, name: s.name, color: colorOf(i), cards: s.data.cards.length })),
    cards,
    edges,
  };
}
