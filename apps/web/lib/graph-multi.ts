import type { StylesheetJson } from "cytoscape";
import type { GraphCard, GraphData, GraphEdge } from "@/lib/graph";

// V16/V17: the graphs of several subjects in one picture. Each subject has its own colour; an edge
// only ever joins two cards of one subject (core-api builds the graph per subject).

/** Colours of the subjects in order; fixed so a subject keeps its colour on every visit. */
// V4: the brand family. Pink is the first subject; teal stays the assistant's voice and never a
// subject; no yellow. The graph sits on `--sheet`, white in the light palette and #22151a in the
// dark one, and one palette must hold for both: every tone clears 3:1 on each (WCAG 1.4.11, the
// bar for a shape that carries meaning — a node's name has its own plate, so it is not the tone's
// job to carry 4.5:1), and no two tones sit closer than 25 in CIELAB, because the earlier tones
// that differed only in lightness merged into one another on the dark canvas. A tone that is dark
// on white is light on #22151a and the other way round, so no tone may go past either end.
// Held by tests/graph-multi-contrast.test.ts.
export const SUBJECT_COLORS = ["#d1347a", "#7b57c4", "#a05a3c", "#7c6d72", "#2f6fb5", "#3d8a55"] as const;

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

/** V4: a lit link is the brand pink; the card being read ("picked") is `now`, never the teal (that is the
 * assistant's voice). Rules appended after the base stylesheet. */
export function v4Highlights(ink: string, hong: string, now: string): StylesheetJson {
  return [
    { selector: "edge.hot", style: { "line-color": hong, width: 2 } },
    { selector: "node.picked", style: { "background-color": now, "border-color": ink, "border-width": 3, "text-opacity": 1 } },
  ];
}
