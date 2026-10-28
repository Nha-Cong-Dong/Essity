// T4.9 (US-02 AC2): the table of contents as ai-service writes it (toc.json, contracts/files/
// toc.v1.schema.json) and core-api relays it untyped (`toc: unknown`). Plain, no server-only.
export type TocEntry = { title: string; level: number; page: number | null };
export type TocNode = { title: string; from: number | null; to: number | null; children: TocNode[] };

const isInt = (v: unknown): v is number => typeof v === "number" && Number.isInteger(v);
const hasOnly = (o: object, keys: string[]) => Object.keys(o).every((k) => keys.includes(k));

function isEntry(v: unknown): v is TocEntry {
  if (typeof v !== "object" || v === null || Array.isArray(v)) return false;
  const o = v as Record<string, unknown>;
  return (
    hasOnly(o, ["title", "level", "page"]) &&
    typeof o.title === "string" &&
    isInt(o.level) &&
    o.level >= 0 &&
    (o.page === null || (isInt(o.page) && o.page >= 1))
  );
}

/** The entries of a valid toc.v1, or null when `value` does not match the schema. */
export function parseToc(value: unknown): TocEntry[] | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return null;
  const o = value as Record<string, unknown>;
  if (!hasOnly(o, ["entries"]) || !Array.isArray(o.entries)) return null;
  return o.entries.every(isEntry) ? (o.entries as TocEntry[]) : null;
}

/**
 * Nests the entries by level. An entry covers its page up to the page before the next entry of
 * the same or a shallower level (the last one to `pageCount`); one with no page has no range.
 */
export function toTree(entries: TocEntry[], pageCount: number | null): TocNode[] {
  const roots: TocNode[] = [];
  const stack: { level: number; node: TocNode }[] = [];
  const close = (node: TocNode, end: number | null) => {
    if (node.from !== null) node.to = Math.max(node.from, end ?? node.from);
  };
  for (const entry of entries) {
    while (stack.length > 0 && stack[stack.length - 1].level >= entry.level) {
      close(stack.pop()!.node, entry.page === null ? null : entry.page - 1);
    }
    const node: TocNode = { title: entry.title, from: entry.page, to: null, children: [] };
    (stack.length > 0 ? stack[stack.length - 1].node.children : roots).push(node);
    stack.push({ level: entry.level, node });
  }
  for (const { node } of stack) close(node, pageCount);
  return roots;
}
