// T9.10a (US-19 AC1-AC4; DESIGN §6.15, .work/T9.10a/design-decisions.md): the pure part of the
// graph screen. One filtered view feeds both the canvas and the list, so the list always holds
// exactly what the canvas draws (AC3). Nothing here scores, ranks or flags a card as weak.

export const EDGE_KINDS = ["prerequisite", "part_of", "example_of", "contrast", "applies_to"] as const;
export type EdgeKind = (typeof EDGE_KINDS)[number];

/** Cards drawn at once (DESIGN §6.15). */
export const MAX_NODES = 300;

export type EdgeStyle = {
  label: string;
  /** Short reading of the link for a screen reader and the list: "A <phrase> B". */
  phrase: string;
  /** Stroke in px; every kind is at least 2 px except part_of, which has its diamond end. */
  width: number;
  /** Cytoscape dash pattern; null is solid. */
  dash: number[] | null;
  /** Arrow shape at the target end (null: none) and, for contrast, at the source end too. */
  arrow: "triangle" | "diamond" | "triangle-tee" | "vee" | null;
  both: boolean;
};

// Ink only: kinds differ by stroke and by word, never by a new colour (DESIGN §6.15).
export const EDGE_STYLE: Record<EdgeKind, EdgeStyle> = {
  prerequisite: { label: "Tiên quyết", phrase: "cần biết trước", width: 2, dash: null, arrow: "triangle", both: false },
  part_of: { label: "Là một phần của", phrase: "là một phần của", width: 1.5, dash: null, arrow: "diamond", both: false },
  example_of: { label: "Là ví dụ của", phrase: "là ví dụ của", width: 2, dash: [6, 4], arrow: "vee", both: false },
  contrast: { label: "Đối lập hoặc so sánh", phrase: "đối lập hoặc so sánh với", width: 2, dash: [2, 4], arrow: "vee", both: true },
  applies_to: { label: "Áp dụng vào", phrase: "được áp dụng vào", width: 2, dash: [8, 3, 2, 3], arrow: "triangle-tee", both: false },
};

export type Anchor = { id: string; label: string; quote: string };
export type GraphCard = {
  id: string;
  title: string;
  body: string;
  sectionId: string;
  anchors: Anchor[];
  /** Source questions that need this card to be answered (shown in the tray, not drawn). */
  neededBy: string[];
};
export type GraphEdge = {
  id: string;
  kind: EdgeKind;
  from: string;
  to: string;
  /** Quote from the anchors of both cards; an edge without one is never shown. */
  evidence: string;
};
export type GraphSection = { id: string; title: string; parentId: string | null };
export type GraphData = { sections: GraphSection[]; cards: GraphCard[]; edges: GraphEdge[] };

export type GraphView = {
  cards: GraphCard[];
  edges: GraphEdge[];
  /** Cards beyond MAX_NODES that the section holds. */
  hidden: number;
  /** Ids of cards with no visible edge (listed apart in the list). */
  unlinked: Set<string>;
};

/** `sectionId` and all its descendants; null is the whole subject. */
export function sectionScope(sections: GraphSection[], sectionId: string | null): Set<string> | null {
  if (sectionId === null) return null;
  const scope = new Set([sectionId]);
  let grew = true;
  while (grew) {
    grew = false;
    for (const s of sections) {
      if (s.parentId !== null && scope.has(s.parentId) && !scope.has(s.id)) {
        scope.add(s.id);
        grew = true;
      }
    }
  }
  return scope;
}

export function viewGraph(data: GraphData, sectionId: string | null, kinds: ReadonlySet<EdgeKind>): GraphView {
  const scope = sectionScope(data.sections, sectionId);
  const inScope = data.cards.filter((c) => scope === null || scope.has(c.sectionId));
  const cards = inScope.slice(0, MAX_NODES);
  const ids = new Set(cards.map((c) => c.id));
  const edges = data.edges.filter(
    (e) => e.evidence.trim() !== "" && kinds.has(e.kind) && ids.has(e.from) && ids.has(e.to) && e.from !== e.to,
  );
  const linked = new Set(edges.flatMap((e) => [e.from, e.to]));
  return {
    cards,
    edges,
    hidden: inScope.length - cards.length,
    unlinked: new Set(cards.filter((c) => !linked.has(c.id)).map((c) => c.id)),
  };
}

/** Steps from `id` over `edges` (either direction), up to `depth`; includes `id` at 0. */
export function neighbourhood(edges: GraphEdge[], id: string, depth: number): Map<string, number> {
  const dist = new Map([[id, 0]]);
  let frontier = [id];
  for (let step = 1; step <= depth; step++) {
    const next: string[] = [];
    for (const e of edges) {
      for (const [a, b] of [[e.from, e.to], [e.to, e.from]] as const) {
        if (frontier.includes(a) && !dist.has(b)) {
          dist.set(b, step);
          next.push(b);
        }
      }
    }
    frontier = next;
  }
  return dist;
}

/**
 * Whether to suggest the list: a 44 px hit area per node fills a small frame fast (design
 * decision 3): 20 nodes under 480 px, 40 above. Only a hint; the switch is never flipped for the
 * reader.
 */
export function suggestList(nodeCount: number, frameWidth: number): boolean {
  return nodeCount > (frameWidth < 480 ? 20 : 40);
}

/** Canvas label: cut at 24 characters; the full title stays in `aria-label`, tray and list. */
export function shortLabel(title: string): string {
  const chars = [...title];
  return chars.length <= 24 ? title : `${chars.slice(0, 23).join("")}…`;
}

export const COPY = {
  empty: "Chưa có liên kết nào. Liên kết hiện ra khi bạn lưu thêm thẻ.",
  truncated: "Hiển thị 300 thẻ đầu của mục này. Chọn mục nhỏ hơn để xem đủ.",
  error: "Không tải được đồ thị.",
  noKind: "Không có liên kết thuộc loại đã chọn.",
} as const;
