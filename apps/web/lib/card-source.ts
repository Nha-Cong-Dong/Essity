// G4: where a card came from. Pure helpers (client-safe); the read is in card-source-load.ts.
// The wire shape is written by hand until api-client is regenerated for GET /v1/units/{id}/sources.

export type CardSource = {
  anchor_id: string;
  document_id: string | null;
  document_name: string | null;
  subject_id: string;
  page_no: number | null;
  quote: string;
  page_text: string | null;
  mark_start: number | null;
  mark_end: number | null;
};

export type CardSources = { unit_id: string; title: string; sources: CardSource[] };

export type TextPart = { text: string; marked: boolean };

/** The page text cut around the cited passage: before, passage (marked), after. */
export function splitMarked(text: string, start: number | null, end: number | null): TextPart[] {
  if (start === null || end === null || start < 0 || end > text.length || end <= start) {
    return [{ text, marked: false }];
  }
  return [
    { text: text.slice(0, start), marked: false },
    { text: text.slice(start, end), marked: true },
    { text: text.slice(end), marked: false },
  ].filter((p) => p.text.length > 0);
}

export function sourceLabel(s: Pick<CardSource, "document_name" | "page_no">): string {
  if (s.document_name === null) return "Ghi chú";
  return s.page_no === null ? s.document_name : `${s.document_name}, trang ${s.page_no}`;
}

export function sourceHref(cardId: string): string {
  return `/kho-kien-thuc/the/${cardId}/nguon`;
}
