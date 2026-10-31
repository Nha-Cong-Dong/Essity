// T7.5a (US-13 AC4-AC6; DESIGN §6.6, design-decisions.md R2.3-R2.4): the pure rules of the syllabus
// tree. One counting rule everywhere: a "mục" is a leaf that is not excluded, itself or through an
// ancestor. The shape is a guess until T7.4 defines the API; the rules do not depend on it.

export type Unit = "page" | "slide" | "est_page";
export type Source = "bookmark" | "heading" | "llm_toc" | "chunk10" | "user";

export type SyllabusNode = {
  id: string;
  title: string;
  from: number;
  to: number;
  /** Size in `unit`s; a section with no text counts 1 (US-13 AC1). */
  weight: number;
  excluded: boolean;
  /** Leaf only: the whole leaf is studied. */
  done: boolean;
  /** Leaf only: the part the learner declared when logging a session, or null. */
  part: [number, number] | null;
  /** Leaf only: marked studied with the button, not through a declared range. */
  byHand: boolean;
  /** The learner changed this range (source "user"). */
  edited: boolean;
  children: SyllabusNode[];
};

export type Status = "none" | "partial" | "done" | "empty";
export type Row = {
  node: SyllabusNode;
  level: number;
  setSize: number;
  posInSet: number;
  parentId: string | null;
};

const isLeaf = (n: SyllabusNode) => n.children.length === 0;

/** Leaves under `node` (or `node` itself) that count: nothing on the way down is excluded. */
function countable(node: SyllabusNode, parentExcluded = false): SyllabusNode[] {
  const out = parentExcluded || node.excluded;
  if (isLeaf(node)) return out ? [] : [node];
  return node.children.flatMap((c) => countable(c, out));
}

function allLeaves(node: SyllabusNode): SyllabusNode[] {
  return isLeaf(node) ? [node] : node.children.flatMap(allLeaves);
}

export const countCountable = (node: SyllabusNode): number => countable(node).length;

const covered = (leaf: SyllabusNode): number =>
  leaf.done ? leaf.weight : leaf.part ? Math.min(leaf.weight, leaf.part[1] - leaf.part[0] + 1) : 0;

export function progress(nodes: SyllabusNode[]) {
  const leaves = nodes.flatMap((n) => countable(n));
  return {
    done: leaves.filter((l) => l.done).length,
    total: leaves.length,
    pagesDone: leaves.reduce((sum, l) => sum + covered(l), 0),
    pagesTotal: leaves.reduce((sum, l) => sum + l.weight, 0),
    excluded: nodes.flatMap(allLeaves).length - leaves.length,
  };
}

export const anyEdited = (nodes: SyllabusNode[]): boolean => nodes.some((n) => n.edited || anyEdited(n.children));

export function leafStatus(leaf: SyllabusNode): Exclude<Status, "empty"> {
  return leaf.done ? "done" : leaf.part ? "partial" : "none";
}

export function nodeStatus(node: SyllabusNode): Status {
  if (isLeaf(node)) return leafStatus(node);
  const leaves = countable(node);
  if (leaves.length === 0) return "empty";
  if (leaves.every((l) => l.done)) return "done";
  return leaves.some((l) => l.done || l.part) ? "partial" : "none";
}

export function findNode(nodes: SyllabusNode[], id: string): SyllabusNode | undefined {
  for (const n of nodes) {
    if (n.id === id) return n;
    const inside = findNode(n.children, id);
    if (inside) return inside;
  }
  return undefined;
}

function mapNode(nodes: SyllabusNode[], id: string, fn: (n: SyllabusNode) => SyllabusNode): SyllabusNode[] {
  return nodes.map((n) => (n.id === id ? fn(n) : { ...n, children: mapNode(n.children, id, fn) }));
}

function mapLeaves(node: SyllabusNode, fn: (leaf: SyllabusNode) => SyllabusNode, parentExcluded = false): SyllabusNode {
  const out = parentExcluded || node.excluded;
  if (isLeaf(node)) return out ? node : fn(node);
  return { ...node, children: node.children.map((c) => mapLeaves(c, fn, out)) };
}

/** What the two mark buttons of a node would change (the numbers in their labels). */
export function markCounts(node: SyllabusNode) {
  const leaves = countable(node);
  return {
    toStudied: leaves.filter((l) => !l.done && !l.part).length,
    toUnstudied: leaves.filter((l) => l.done && l.byHand).length,
  };
}

/**
 * A leaf is set whole. A branch only changes what the learner has not declared: studying marks the
 * leaves with nothing studied, un-studying undoes the leaves marked by hand, never a declared range.
 */
export function applyMark(nodes: SyllabusNode[], id: string, studied: boolean): SyllabusNode[] {
  return mapNode(nodes, id, (n) => {
    if (isLeaf(n)) {
      return studied ? { ...n, done: true, part: null, byHand: true } : { ...n, done: false, part: null, byHand: false };
    }
    return mapLeaves(n, (l) => {
      if (studied && !l.done && !l.part) return { ...l, done: true, byHand: true };
      if (!studied && l.done && l.byHand) return { ...l, done: false, byHand: false };
      return l;
    });
  });
}

/** Flips this node's own flag. A branch brought back does not bring back a child dropped on its own. */
export const excludeToggle = (nodes: SyllabusNode[], id: string): SyllabusNode[] =>
  mapNode(nodes, id, (n) => ({ ...n, excluded: !n.excluded }));

export type RangeContext = {
  total: number;
  parent: [number, number] | null;
  siblings: { label: string; from: number; to: number }[];
};

/** The context a node's range is checked against (its parent and the neighbours, T7.4 will own the real rule). */
export function rangeContext(nodes: SyllabusNode[], id: string, total: number): RangeContext {
  const find = (list: SyllabusNode[], parent: SyllabusNode | null): RangeContext | null => {
    for (const n of list) {
      if (n.id === id) {
        return {
          total,
          parent: parent ? [parent.from, parent.to] : null,
          siblings: list.filter((s) => s.id !== id).map((s) => ({ label: s.title.match(/^[\d.]+/)?.[0] ?? s.title, from: s.from, to: s.to })),
        };
      }
      const inside = find(n.children, n);
      if (inside) return inside;
    }
    return null;
  };
  return find(nodes, null) ?? { total, parent: null, siblings: [] };
}

const WORD: Record<Unit, string> = { page: "trang", slide: "slide", est_page: "trang" };

/** The sentence for a refused range (null = fine). Rule text is provisional until T7.4. */
export function validateRange(from: number, to: number, ctx: RangeContext, unit: Unit): string | null {
  const word = WORD[unit];
  if (![from, to].every((n) => Number.isInteger(n) && n >= 1)) return `Nhập số ${word}, ví dụ 52.`;
  if (from > to) return `${word === "slide" ? "Slide" : "Trang"} bắt đầu phải nhỏ hơn hoặc bằng ${word} kết thúc.`;
  if (to > ctx.total) {
    return unit === "slide" ? `Bài giảng chỉ có ${ctx.total} slide.` : `Giáo trình chỉ có ${ctx.total} trang.`;
  }
  if (ctx.parent && (from < ctx.parent[0] || to > ctx.parent[1])) {
    return `Khoảng này nằm ngoài mục cha (${rangeText(ctx.parent[0], ctx.parent[1], unit)}).`;
  }
  return null;
}

export const applyRange = (nodes: SyllabusNode[], id: string, from: number, to: number): SyllabusNode[] =>
  mapNode(nodes, id, (n) => ({ ...n, from, to, weight: to - from + 1, edited: true }));

const SOURCE_LABEL: Record<Source, string> = {
  bookmark: "từ bookmark",
  heading: "từ heading",
  llm_toc: "từ mục lục (AI đọc)",
  chunk10: "tạm: chia khối 10 trang",
  user: "bạn đã sửa",
};

export const sourceLabel = (source: Source, edited: boolean): string => SOURCE_LABEL[edited ? "user" : source];

export function rangeText(from: number, to: number, unit: Unit): string {
  const head = unit === "slide" ? "slide" : "tr.";
  return to > from ? `${head} ${from}–${to}` : `${head} ${from}`;
}

/** The status sentence of a node, for the screen reader description and the line under the title. */
export function describeNode(node: SyllabusNode, unit: Unit): string {
  if (node.excluded) return "không thi";
  if (!isLeaf(node)) {
    const n = countCountable(node);
    if (n === 0) return "không có mục tính";
    const done = countable(node).filter((l) => l.done).length;
    return `${n} mục, đã học ${done}/${n} mục`;
  }
  if (node.done) return "đã học";
  if (node.part) {
    return `đã học ${rangeText(node.part[0], node.part[1], unit)} trong ${rangeText(node.from, node.to, unit)}`;
  }
  return "chưa học";
}

/** Rows in screen order: a branch's children only while it is open. */
export function visibleRows(nodes: SyllabusNode[], open: ReadonlySet<string>): Row[] {
  const walk = (list: SyllabusNode[], level: number, parentId: string | null): Row[] =>
    list.flatMap((node, i) => [
      { node, level, setSize: list.length, posInSet: i + 1, parentId },
      ...(open.has(node.id) ? walk(node.children, level + 1, node.id) : []),
    ]);
  return walk(nodes, 1, null);
}

/** The branch ids open by default: the way down to the first leaf not yet studied (level 1 is always shown). */
export function defaultOpen(nodes: SyllabusNode[]): Set<string> {
  const open = new Set<string>();
  const path = (list: SyllabusNode[]): string[] | null => {
    for (const n of list) {
      if (isLeaf(n)) {
        if (!n.excluded && !n.done) return [];
        continue;
      }
      const inside = path(n.children);
      if (inside) return [n.id, ...inside];
    }
    return null;
  };
  path(nodes)?.forEach((id) => open.add(id));
  return open;
}
