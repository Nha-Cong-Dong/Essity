// T7.12a (US-02 AC2-AC4; DESIGN.md §6.7 vùng 2; design decisions C2-C4): `@name` in the
// description. A mention is the document the user chose, kept by document id and character range,
// never guessed from the text. What follows it ("mục 3.2") is resolved by the backend on submit.

export type DocRef = { id: string; name: string; role: string };
export type Mention = { docId: string; name: string; start: number; end: number };

const MENU_MAX = 6;
/** A query this long no longer looks like a document name; the menu closes. */
const QUERY_MAX = 40;

const fold = (text: string) =>
  text
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .replace(/đ/g, "d")
    .replace(/Đ/g, "D")
    .toLowerCase();

/**
 * The `@` the caret is typing after: at the start of the text or after whitespace, on one line,
 * and not the start of a mention already chosen. Spaces stay in the query ("slide c3").
 */
export function activeMention(
  text: string,
  caret: number,
  mentions: readonly Mention[],
): { at: number; query: string } | null {
  for (let i = caret - 1; i >= 0 && caret - i <= QUERY_MAX; i--) {
    const ch = text[i];
    if (ch === "\n") return null;
    if (ch !== "@") continue;
    if (i > 0 && !/\s/.test(text[i - 1])) return null;
    if (mentions.some((m) => m.start === i)) return null;
    return { at: i, query: text.slice(i + 1, caret) };
  }
  return null;
}

/** Documents whose name contains the query, ignoring case and accents; at most six rows. */
export function filterDocs(docs: readonly DocRef[], query: string): DocRef[] {
  const wanted = fold(query.trim());
  return docs.filter((doc) => fold(doc.name).includes(wanted)).slice(0, MENU_MAX);
}

/** Chooses `doc` for the `@query` between `at` and `caret`: the text becomes `@name ` and the range is recorded. */
export function applyMention(
  text: string,
  at: number,
  caret: number,
  doc: DocRef,
  mentions: readonly Mention[],
): { text: string; caret: number; mentions: Mention[] } {
  const inserted = `@${doc.name} `;
  const next = text.slice(0, at) + inserted + text.slice(caret);
  const delta = inserted.length - (caret - at);
  const kept = mentions.map((m) => (m.start >= caret ? { ...m, start: m.start + delta, end: m.end + delta } : m));
  const mention: Mention = { docId: doc.id, name: doc.name, start: at, end: at + 1 + doc.name.length };
  return { text: next, caret: at + inserted.length, mentions: [...kept, mention].sort((a, b) => a.start - b.start) };
}

/**
 * After an edit: a mention whose characters were touched is removed (no orphan chip), the ones
 * after the edit shift. The edit is found as the span between the common prefix and suffix.
 */
export function reconcileMentions(
  before: string,
  after: string,
  mentions: readonly Mention[],
): { mentions: Mention[]; removed: Mention[] } {
  let prefix = 0;
  const shortest = Math.min(before.length, after.length);
  while (prefix < shortest && before[prefix] === after[prefix]) prefix++;
  let suffix = 0;
  while (suffix < shortest - prefix && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]) suffix++;
  const oldEnd = before.length - suffix;
  const delta = after.length - before.length;
  const kept: Mention[] = [];
  const removed: Mention[] = [];
  for (const m of mentions) {
    if (m.end <= prefix) kept.push(m);
    else if (m.start >= oldEnd) kept.push({ ...m, start: m.start + delta, end: m.end + delta });
    else removed.push(m);
  }
  return { mentions: kept, removed };
}
