import type { components } from "@/lib/core-client"; // types only: erased from the browser bundle

import { postJson } from "@/lib/auth-errors";
import type { NoteRef } from "@/lib/note-upload";

// T4.13a (US-02): what the "Ghi buổi học" page does with core-api's card. Pure helpers plus the two
// calls the browser makes to web's routes (/api/subjects/{id}/sessions, /api/sessions/{id}/confirm).

export type Card = components["schemas"]["SessionCard"];
export type CardRange = components["schemas"]["CardRange"];
export type DocumentChoice = components["schemas"]["DocumentChoice"];
export type Depth = CardRange["depth"];

/** core-api's DESCRIPTION_MAX: longer is cut by the box, never refused after the wait. */
export const DESCRIPTION_MAX = 2000;

/** One row of the page-range form: the pages are text until checked. */
export type RangeDraft = { documentId: string; from: string; to: string; depth: Depth };

export type RangeProblem = "document" | "pages" | "order" | "beyond";

/** The first thing wrong with a row, or null (page counts come from the card's documents). */
export function checkRange(draft: RangeDraft, documents: DocumentChoice[]): RangeProblem | null {
  const document = documents.find((choice) => choice.document_id === draft.documentId);
  if (!document) return "document";
  if (!/^\d{1,5}$/.test(draft.from.trim()) || !/^\d{1,5}$/.test(draft.to.trim())) return "pages";
  const from = Number(draft.from);
  const to = Number(draft.to);
  if (from < 1 || to < 1) return "pages";
  if (from > to) return "order";
  if (to > document.page_count) return "beyond";
  return null;
}

/** The rows the form starts with: the card's ranges, or one empty row on the first document. */
export function startingRows(card: Card, preferred?: string): RangeDraft[] {
  if (card.ranges.length > 0 && preferred === undefined) {
    return card.ranges.map((range) => ({
      documentId: range.document_id,
      from: String(range.start_page),
      to: String(range.end_page),
      depth: range.depth,
    }));
  }
  return [{ documentId: preferred ?? card.documents[0]?.document_id ?? "", from: "", to: "", depth: "deep" }];
}

/** "tr. 43–58" (or "tr. 43" for one page). */
export function pagesLine(start: number, end: number): string {
  return start === end ? `tr. ${start}` : `tr. ${start}–${end}`;
}

export type ConfirmRange = components["schemas"]["RangeIn"];

export function rowsToRanges(rows: RangeDraft[]): ConfirmRange[] {
  return rows.map((row) => ({
    document_id: row.documentId,
    start_page: Number(row.from),
    end_page: Number(row.to),
    depth: row.depth,
  }));
}

/** The ranges of a proposed card, as the learner confirms them (labels kept, nothing added). */
export function cardToRanges(card: Card): ConfirmRange[] {
  return card.ranges.map(({ document_id, start_page, end_page, depth, start_label, end_label }) => ({
    document_id,
    start_page,
    end_page,
    depth,
    ...(start_label ? { start_label } : {}),
    ...(end_label ? { end_label } : {}),
  }));
}

export type CallResult<Data> = { ok: true; data: Data } | { ok: false; code: string; retryAfter?: number };

async function call<Data>(path: string, body: unknown): Promise<CallResult<Data>> {
  const result = await postJson<Data>(path, body);
  if (result.data) return { ok: true, data: result.data };
  if (result.status === 401) return { ok: false, code: "signed_out" };
  return { ok: false, code: result.error ?? "unavailable", retryAfter: result.retryAfter };
}

/** US-02 AC3-AC5: the sentence in, the card to confirm out. */
export function describeSession(subjectId: string, description: string): Promise<CallResult<Card>> {
  return call<Card>(`/api/subjects/${subjectId}/sessions`, { description });
}

/** US-02 AC7: "Lưu". Confirming twice is safe (core-api answers the saved session). */
export function confirmSession(
  sessionId: string,
  ranges: ConfirmRange[],
  studiedOn?: string | null,
  notes: NoteRef[] = [],
): Promise<CallResult<{ session_id: string }>> {
  return call(`/api/sessions/${sessionId}/confirm`, {
    ranges,
    notes,
    ...(studiedOn ? { studied_on: studiedOn } : {}),
  });
}
