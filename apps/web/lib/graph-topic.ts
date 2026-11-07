import { nodeRadius } from "@/components/landing/graph-data";
import type { GraphSection } from "@/lib/graph";
import { mergeGraphs, SUBJECT_COLORS, type MultiCard, type SubjectGraph } from "@/lib/graph-multi";

// GRAPH-LANDING-STYLE: the in-app knowledge graph drawn like the landing one (components/landing/graph-data.ts):
// a hub node per topic, ring nodes tinted by topic, size by level. Pure, so colour, size and grouping are tested.
// Topic = a subject on /graph; = a top-level chapter when one subject is focused (/graph?subject=…).

export type Topic = { id: string; name: string; color: string; cards: number };
export type TopicNode = {
  id: string;
  label: string;
  full: string;
  topicId: string;
  hub: boolean;
  degree: number;
  /** Diameter in px at zoom 1. */
  size: number;
  card?: MultiCard;
};
export type TopicEdge = { id: string; from: string; to: string; own: boolean };
export type TopicGraph = { mode: "subject" | "chapter"; topics: Topic[]; nodes: TopicNode[]; edges: TopicEdge[] };

/** Landing radius to cytoscape diameter: the landing stage is drawn smaller than the app canvas. */
const SCALE = 1.8;
const MIN_CARD = 16;
export const NO_CHAPTER = "Chưa vào chương nào";

/** Diameter of a node: the landing radius (hub biggest, card by its number of links, capped) scaled to the canvas. */
export function nodeSize(degree: number, hub: boolean): number {
  const d = 2 * nodeRadius(degree, hub) * SCALE;
  return hub ? d : Math.max(MIN_CARD, d);
}

/** `amount` of `colour` over `background` (both #rrggbb): the pale ring-node fill of the landing graph. */
export function tint(colour: string, background: string, amount: number): string {
  // the sheet token can be a short #fff
  const full = (hex: string) => (hex.length === 4 ? "#" + [...hex.slice(1)].map((c) => c + c).join("") : hex);
  [colour, background] = [full(colour), full(background)];
  const ch = (hex: string, o: number) => parseInt(hex.slice(o, o + 2), 16);
  const mix = (o: number) => Math.round(ch(background, o) + (ch(colour, o) - ch(background, o)) * amount);
  return "#" + [1, 3, 5].map((o) => mix(o).toString(16).padStart(2, "0")).join("");
}

function chapterOf(sections: GraphSection[], sectionId: string): string | null {
  const byId = new Map(sections.map((s) => [s.id, s] as const));
  let cur = byId.get(sectionId);
  for (let guard = 0; cur && guard < 20; guard++) {
    if (cur.parentId === null) return cur.id;
    cur = byId.get(cur.parentId);
  }
  return null;
}

export function buildTopicGraph(graphs: SubjectGraph[], focusSubject: string | null): TopicGraph {
  const focus = focusSubject ? graphs.find((g) => g.id === focusSubject) : undefined;
  const merged = mergeGraphs(focus ? [focus] : graphs);
  let mode: TopicGraph["mode"] = "subject";
  let topics: Topic[] = merged.subjects.map((s) => ({ id: s.id, name: s.name, color: s.color, cards: s.cards }));
  let topicOf = (c: MultiCard) => c.subjectId;
  if (focus) {
    const chapters = focus.data.sections.filter((s) => s.parentId === null);
    if (chapters.length > 0) {
      mode = "chapter";
      const known = new Set(chapters.map((s) => s.id));
      const chapterIdOf = (c: MultiCard) => {
        const ch = chapterOf(focus.data.sections, c.sectionId);
        return ch && known.has(ch) ? ch : "";
      };
      const count = new Map<string, number>();
      for (const c of merged.cards) count.set(chapterIdOf(c), (count.get(chapterIdOf(c)) ?? 0) + 1);
      // a chapter with no card yet is not drawn: an empty hub would float alone
      topics = chapters.map((s) => ({ id: s.id, name: s.title, color: "", cards: count.get(s.id) ?? 0 })).filter((t) => t.cards > 0);
      if (count.get("")) topics.push({ id: "", name: NO_CHAPTER, color: "", cards: count.get("")! });
      topics = topics.map((t, i) => ({ ...t, color: SUBJECT_COLORS[i % SUBJECT_COLORS.length] }));
      topicOf = chapterIdOf;
    }
  }
  const degree = new Map<string, number>();
  const bump = (id: string) => degree.set(id, (degree.get(id) ?? 0) + 1);
  const edges: TopicEdge[] = [
    ...merged.cards.map((c) => ({ id: `own:${c.id}`, from: c.id, to: `hub:${topicOf(c)}`, own: true })),
    ...merged.edges.map((e) => ({ id: e.id, from: e.from, to: e.to, own: false })),
  ];
  for (const e of edges) {
    bump(e.from);
    bump(e.to);
  }
  const nodes: TopicNode[] = [
    ...topics.map((t): TopicNode => {
      const id = `hub:${t.id}`;
      const d = degree.get(id) ?? 0;
      return { id, label: t.name, full: t.name, topicId: t.id, hub: true, degree: d, size: nodeSize(d, true) };
    }),
    ...merged.cards.map((c): TopicNode => {
      const d = degree.get(c.id) ?? 0;
      return { id: c.id, label: c.title, full: c.title, topicId: topicOf(c), hub: false, degree: d, size: nodeSize(d, false), card: c };
    }),
  ];
  return { mode, topics, nodes, edges };
}
