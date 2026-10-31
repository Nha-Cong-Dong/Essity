// T7.5 (US-13 AC4-AC6, US-01 AC4-AC5): the outline API (T7.4) as the tree of T7.5a wants it, and
// the browser's calls to web's routes. Pure, no server-only import: the tree and the upload form
// are client components.
import type { components } from "@/lib/core-client";

import type { Source, SyllabusNode, Unit } from "./tree";

export type OutlineOut = components["schemas"]["OutlineOut"];
type SectionOut = components["schemas"]["SectionOut"];

export type OutlineView =
  | { kind: "none"; reason: "no_textbook" | "not_indexed" | "no_outline"; name: string | null }
  | {
      kind: "ready";
      name: string;
      nodes: SyllabusNode[];
      unit: Unit;
      total: number;
      source: Source;
      /** Every section is a 10-page block: labelled "tạm" (US-13 AC9). */
      temporary: boolean;
    };

function toNode(s: SectionOut): SyllabusNode {
  const leaf = s.children.length === 0;
  const first = s.first_page ?? 0;
  const last = s.last_page ?? first;
  // The API says how much of a leaf is covered (0..1), not which pages: a partly studied leaf
  // shows its first pages (decision in .work/T7.5/decisions.md).
  const covered = Math.round(s.progress * s.weight);
  return {
    id: s.id,
    title: s.title,
    from: first,
    to: last,
    weight: s.weight,
    excluded: s.excluded,
    done: leaf && s.studied,
    part: leaf && !s.studied && s.progress > 0 ? [first, Math.min(last, first + Math.max(1, covered) - 1)] : null,
    byHand: leaf && s.studied,
    edited: s.source === "user",
    children: s.children.map(toNode),
  };
}

const flatten = (list: SectionOut[]): SectionOut[] => list.flatMap((s) => [s, ...flatten(s.children)]);

export function outlineView(out: OutlineOut): OutlineView {
  if (out.document === null || out.reason !== null || out.sections.length === 0) {
    return { kind: "none", reason: out.reason ?? "no_outline", name: out.document?.short_name ?? null };
  }
  const all = flatten(out.sections);
  const total = out.document.page_count ?? Math.max(...all.map((s) => s.last_page ?? 0));
  const machine = all.find((s) => s.source !== "user")?.source ?? "heading";
  return {
    kind: "ready",
    name: out.document.short_name,
    nodes: out.sections.map(toNode),
    unit: all[0]!.unit,
    total,
    source: out.temporary ? "chunk10" : machine,
    temporary: out.temporary,
  };
}

export type SectionBody = { first_page?: number; last_page?: number; excluded?: boolean; studied?: boolean };
export type Change = { id: string; body: SectionBody };

/**
 * What the learner's action changed, as one PATCH per node: a range, an exclusion, or a leaf
 * studied/not studied. A branch mark arrives as its leaves (the tree computed them).
 */
export function diffChanges(prev: SyllabusNode[], next: SyllabusNode[]): Change[] {
  const before = new Map<string, SyllabusNode>();
  const index = (list: SyllabusNode[]) =>
    list.forEach((n) => {
      before.set(n.id, n);
      index(n.children);
    });
  index(prev);
  const out: Change[] = [];
  const walk = (list: SyllabusNode[]) => {
    for (const n of list) {
      const old = before.get(n.id);
      if (old) {
        if (old.from !== n.from || old.to !== n.to) out.push({ id: n.id, body: { first_page: n.from, last_page: n.to } });
        if (old.excluded !== n.excluded) out.push({ id: n.id, body: { excluded: n.excluded } });
        if (n.children.length === 0 && old.done !== n.done) out.push({ id: n.id, body: { studied: n.done } });
      }
      walk(n.children);
    }
  };
  walk(next);
  return out;
}

export type ApiRole = "textbook" | "question_bank" | "auxiliary";
export type Sent<T> = { ok: true; data: T } | { ok: false; code: string; cards?: number };

async function send<T>(method: string, path: string, body?: object): Promise<Sent<T>> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch {
    return { ok: false, code: "offline" };
  }
  const json: unknown = await response.json().catch(() => null);
  if (response.ok && json !== null) return { ok: true, data: json as T };
  const error = json as { error?: unknown; cards?: unknown } | null;
  return {
    ok: false,
    code: typeof error?.error === "string" ? error.error : response.status === 401 ? "signed_out" : "unavailable",
    ...(typeof error?.cards === "number" ? { cards: error.cards } : {}),
  };
}

export const readOutline = (subjectId: string) => send<OutlineOut>("GET", `/api/subjects/${subjectId}/outline`);
export const patchSection = (id: string, body: SectionBody) => send<OutlineOut>("PATCH", `/api/sections/${id}`, body);
export const putTextbook = (subjectId: string, documentId: string, confirm: boolean) =>
  send<OutlineOut>("PUT", `/api/subjects/${subjectId}/textbook`, { document_id: documentId, confirm });
export const patchDocument = (id: string, body: { role?: ApiRole; short_name?: string }) =>
  send<unknown>("PATCH", `/api/documents/${id}`, body);
