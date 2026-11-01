// T7.12 (US-02 AC2-AC4, AC11, AC13; US-02b AC6-AC9): the browser's side of the study session. Each
// action is one call to web's own routes (app/api), which pass it on to core-api. core-api's
// cards become the screen's `Draft`; an answer is `{ok}` or the code of the refusal, never a throw
// (a dropped network is `status: 0`, `error: "network"`). The learner's words are not logged.
import type { Anchor, Draft } from "./drafts";
import type { DocRef, Mention } from "./mention";

type CoreAnchor = { id: string; source: string; document_id: string | null; page_no: number | null; quote_text: string };
export type CoreDraft = {
  id: string;
  title: string;
  content: string;
  status: string;
  version: number;
  anchors: CoreAnchor[];
  revisions: { origin: string }[];
};

/** Where the submission stands: `none` = nothing was handed in yet. */
export type Phase = "none" | "queued" | "processing" | "pending_ai" | "failed" | "done";

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; error: string; docId?: string };

export function readStatus(status: string | null): Phase {
  switch (status) {
    case null:
      return "none";
    case "queued":
    case "processing":
    case "pending_ai":
    case "failed":
    case "done":
      return status;
    default:
      return "processing";
  }
}

export function toDraft(card: CoreDraft, docs: readonly DocRef[]): Draft {
  const anchors: Anchor[] = card.anchors.map((a) => {
    const name = docs.find((d) => d.id === a.document_id)?.name;
    const label = a.source === "notes" ? "Vở ghi" : `${name ?? "Tài liệu"}${a.page_no === null ? "" : ` · tr. ${a.page_no}`}`;
    return { id: a.id, kind: a.source === "notes" ? "notes" : "document", label, quote: a.quote_text };
  });
  const notes = anchors.some((a) => a.kind === "notes");
  const documents = anchors.some((a) => a.kind === "document");
  return {
    id: card.id,
    title: card.title,
    summary: card.content,
    section: null,
    anchors,
    origin: card.revisions.some((r) => r.origin === "user") ? "user" : "ai",
    status: card.status === "retired" ? "retired" : "draft",
    version: card.version,
    conflict: null,
    source: notes && !documents ? "notes" : documents && !notes ? "document" : "both",
  };
}

export type SessionApi = {
  sessionId: string;
  submit(text: string, mentions: readonly Mention[]): Promise<ApiResult<{ status: Phase }>>;
  load(): Promise<ApiResult<{ phase: Phase; drafts: Draft[] }>>;
  get(id: string): Promise<ApiResult<Draft>>;
  edit(id: string, version: number, patch: { title?: string; content?: string }): Promise<ApiResult<Draft>>;
  discard(id: string): Promise<ApiResult<Draft>>;
  undo(id: string): Promise<ApiResult<Draft>>;
  add(title: string, content: string): Promise<ApiResult<Draft>>;
  merge(ids: string[]): Promise<ApiResult<Draft>>;
  split(id: string, version: number, parts: { title: string; content: string }[]): Promise<ApiResult<Draft[]>>;
  save(cards: { id: string; version: number }[]): Promise<ApiResult<string[]>>;
};

export function createSessionApi(sessionId: string, docs: readonly DocRef[], fetchFn: typeof fetch = fetch): SessionApi {
  async function call(path: string, method: string, body?: unknown): Promise<{ status: number; json: Record<string, unknown> }> {
    try {
      const response = await fetchFn(path, {
        method,
        credentials: "same-origin",
        headers: body === undefined ? undefined : { "content-type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
      const json = (await response.json().catch(() => ({}))) as Record<string, unknown>;
      return { status: response.status, json };
    } catch {
      return { status: 0, json: { error: "network" } };
    }
  }

  async function run<T>(path: string, method: string, body: unknown, read: (json: Record<string, unknown>) => T): Promise<ApiResult<T>> {
    const { status, json } = await call(path, method, body);
    if (status >= 200 && status < 300) return { ok: true, data: read(json) };
    return { ok: false, status, error: typeof json.error === "string" ? json.error : "unavailable" };
  }

  const card = (json: Record<string, unknown>) => toDraft(json as unknown as CoreDraft, docs);
  const list = (json: Record<string, unknown>) => (json.drafts as CoreDraft[]).map((d) => toDraft(d, docs));

  return {
    sessionId,
    async submit(text, mentions) {
      const body = { session_id: sessionId, description: text, mentions: mentions.map((m) => ({ document_id: m.docId, start: m.start, end: m.end })) };
      const { status, json } = await call("/api/submissions", "POST", body);
      if (status >= 200 && status < 300) return { ok: true, data: { status: readStatus(String(json.status)) } };
      const error = typeof json.error === "string" ? json.error : "unavailable";
      const at = typeof json.mention === "number" ? mentions[json.mention] : undefined;
      return at ? { ok: false, status, error, docId: at.docId } : { ok: false, status, error };
    },
    load: () =>
      run(`/api/sessions/${sessionId}/drafts`, "GET", undefined, (json) => ({
        phase: readStatus((json.submission_status as string | null) ?? null),
        drafts: (json.drafts as CoreDraft[]).filter((d) => d.status === "draft" || d.status === "retired").map((d) => toDraft(d, docs)),
      })),
    get: (id) => run(`/api/drafts/${id}`, "GET", undefined, card),
    edit: (id, version, patch) => run(`/api/drafts/${id}`, "PATCH", { version, ...patch }, card),
    discard: (id) => run(`/api/drafts/${id}`, "DELETE", undefined, card),
    undo: (id) => run(`/api/drafts/${id}/undo`, "POST", undefined, card),
    add: (title, content) => run(`/api/sessions/${sessionId}/drafts`, "POST", { title, content }, card),
    merge: (ids) => run(`/api/sessions/${sessionId}/drafts/merge`, "POST", { unit_ids: ids }, card),
    split: (id, version, parts) =>
      run(`/api/drafts/${id}/split`, "POST", { version, parts: parts.map((p) => ({ title: p.title, content: p.content, anchor_ids: [] })) }, list),
    save: (cards) =>
      run(`/api/sessions/${sessionId}/drafts/save`, "POST", { units: cards.map((c) => ({ unit_id: c.id, version: c.version })) }, (json) => json.saved as string[]),
  };
}
