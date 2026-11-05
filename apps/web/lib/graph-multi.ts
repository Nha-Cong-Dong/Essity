import type { GraphCard, GraphData, GraphEdge } from "@/lib/graph";

// V16/V17: the graphs of several subjects in one picture. Each subject has its own colour; an edge
// only ever joins two cards of one subject (core-api builds the graph per subject).

/** Colours of the subjects in order; fixed so a subject keeps its colour on every visit. */
// UI-A: four tones in the app's own family (brand pink, a steel blue, brass, warm grey): no lime or violet.
export const SUBJECT_COLORS = ["#a8255f", "#3b6f8f", "#8a6a2e", "#6b5b66"] as const;

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

/** Subjects to start switched off so only `focus` shows; an unknown or missing id shows everything. */
export function hiddenExcept(subjects: { id: string }[], focus: string | null | undefined): Set<string> {
  if (!focus || !subjects.some((s) => s.id === focus)) return new Set();
  return new Set(subjects.filter((s) => s.id !== focus).map((s) => s.id));
}
