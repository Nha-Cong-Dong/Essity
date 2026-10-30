// T7.12a (US-02 AC5-AC8, US-02b; ADR-0028; design decisions C10, C15, C18): the draft cards of one
// round. Pure: the screen keeps the list, T7.12 will mirror each action to core-api.

export type Anchor = { id: string; kind: "document" | "notes"; label: string; quote: string };

export type Draft = {
  id: string;
  title: string;
  summary: string;
  /** Outline section the card is filed under ("3.2"); null = "Chưa gắn mục". */
  section: string | null;
  anchors: Anchor[];
  origin: "ai" | "user";
  /** `retired` = discarded; it comes back with undo (AC8). */
  status: "draft" | "retired";
  /** For If-Match: a stale edit is answered 409 (ADR-0028). */
  version: number;
  /** Set after a 409: the text the user was typing, kept for comparing. */
  conflict: { mine: string } | null;
  /** AC5: seen only in the notebook or only in the textbook. */
  source: "both" | "notes" | "document";
};

export type DraftAction =
  | { type: "edit"; id: string; patch: Partial<Pick<Draft, "title" | "summary" | "section">> }
  | { type: "discard"; id: string }
  | { type: "undo"; id: string }
  | { type: "add"; id: string }
  | { type: "merge"; sourceId: string; targetId: string }
  | { type: "split"; id: string; parts: [SplitPart, SplitPart] }
  | { type: "append-ai"; drafts: Draft[] }
  | { type: "clear" }
  | { type: "conflict"; id: string; mine: string }
  | { type: "reload"; draft: Draft };

export type SplitPart = { id: string; title: string; summary: string };

const same = (id: string) => (draft: Draft) => draft.id === id;

export function draftsReducer(drafts: Draft[], action: DraftAction): Draft[] {
  switch (action.type) {
    case "edit":
      return drafts.map((d) => (d.id === action.id ? { ...d, ...action.patch, origin: "user" } : d));
    case "discard":
      return drafts.map((d) => (d.id === action.id ? { ...d, status: "retired" } : d));
    case "undo":
      return drafts.map((d) => (d.id === action.id ? { ...d, status: "draft" } : d));
    case "add":
      return [
        ...drafts,
        {
          id: action.id,
          title: "",
          summary: "",
          section: null,
          anchors: [],
          origin: "user",
          status: "draft",
          version: 1,
          conflict: null,
          source: "both",
        },
      ];
    case "merge": {
      const source = drafts.find(same(action.sourceId));
      if (!source || action.sourceId === action.targetId) return drafts;
      return drafts
        .filter((d) => d.id !== action.sourceId)
        .map((d) =>
          d.id === action.targetId
            ? {
                ...d,
                summary: [d.summary, source.summary].filter(Boolean).join("\n"),
                anchors: [...d.anchors, ...source.anchors.filter((a) => !d.anchors.some((x) => x.id === a.id))],
                origin: "user",
              }
            : d,
        );
    }
    case "split": {
      const index = drafts.findIndex(same(action.id));
      if (index < 0) return drafts;
      const base = drafts[index];
      const parts = action.parts.map((part): Draft => ({ ...base, ...part, origin: "user", conflict: null }));
      return [...drafts.slice(0, index), ...parts, ...drafts.slice(index + 1)];
    }
    case "append-ai":
      return [...drafts, ...action.drafts];
    case "clear":
      return [];
    case "conflict":
      return drafts.map((d) => (d.id === action.id ? { ...d, conflict: { mine: action.mine } } : d));
    case "reload":
      return drafts.map((d) => (d.id === action.draft.id ? { ...action.draft, conflict: null } : d));
  }
}

/** Cards that "Đúng rồi, lưu" will save: not retired, and with something written. */
export function savableCount(drafts: readonly Draft[]): number {
  return drafts.filter((d) => d.status === "draft" && (d.title.trim() !== "" || d.summary.trim() !== "")).length;
}
