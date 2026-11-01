import "server-only";

import { readFields } from "@/lib/http";
import { isSubjectId } from "@/lib/subject-id";

// T7.12 (US-02, US-02b): what web's routes for the study session's drafts take from the browser.
// Each body is rebuilt field by field (review plan R1): what goes on to core-api is never the
// browser's JSON. The learner's words are never logged (ADR-0013).

const isObject = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null && !Array.isArray(value);

const exactly = (value: Record<string, unknown>, keys: readonly string[]) =>
  Object.keys(value).every((key) => keys.includes(key));

export type SubmitBody = {
  session_id: string;
  description: string;
  mentions: { document_id: string; start: number; end: number }[];
};

/** The description is the learner's sentence (2000 characters, T7.6) and its `@` mentions. */
export function readSubmit(body: unknown): SubmitBody | null {
  if (!isObject(body) || !exactly(body, ["session_id", "description", "mentions"])) return null;
  const { session_id, description, mentions } = body;
  if (!isSubjectId(session_id) || typeof description !== "string" || description.length > 2000) return null;
  if (mentions !== undefined && (!Array.isArray(mentions) || mentions.length > 20)) return null;
  const found: SubmitBody["mentions"] = [];
  for (const item of mentions ?? []) {
    if (!isObject(item) || !exactly(item, ["document_id", "start", "end"])) return null;
    const { document_id, start, end } = item;
    if (!isSubjectId(document_id) || !Number.isSafeInteger(start) || !Number.isSafeInteger(end)) return null;
    found.push({ document_id, start: start as number, end: end as number });
  }
  return { session_id, description, mentions: found };
}

export type Edit = { version: number; title?: string; content?: string };

/** An edit: the version the browser saw (it becomes `If-Match`) and the fields it changed. */
export async function readEdit(request: Request): Promise<Edit | null> {
  const body = await readFields(
    request,
    { version: { kind: "integer" }, title: { kind: "string", optional: true }, content: { kind: "string", optional: true } },
    { maxBytes: 32 * 1024 },
  );
  if (body === null || body.version < 1) return null;
  return body;
}

export async function readAdd(request: Request): Promise<{ title: string; content: string; kind: "concept" } | null> {
  const body = await readFields(request, { title: { kind: "string" }, content: { kind: "string" } }, { maxBytes: 32 * 1024 });
  return body === null ? null : { ...body, kind: "concept" };
}

export type SplitBody = { version: number; parts: { title: string; content: string; anchor_ids: string[] }[] };

export function readSplit(body: unknown): SplitBody | null {
  if (!isObject(body) || !exactly(body, ["version", "parts"])) return null;
  const { version, parts } = body;
  if (!Number.isSafeInteger(version) || (version as number) < 1) return null;
  if (!Array.isArray(parts) || parts.length < 2 || parts.length > 10) return null;
  const found: SplitBody["parts"] = [];
  for (const part of parts) {
    if (!isObject(part) || !exactly(part, ["title", "content", "anchor_ids"])) return null;
    const { title, content, anchor_ids } = part;
    if (typeof title !== "string" || typeof content !== "string") return null;
    if (!Array.isArray(anchor_ids) || anchor_ids.length > 50 || !anchor_ids.every(isSubjectId)) return null;
    found.push({ title, content, anchor_ids });
  }
  return { version: version as number, parts: found };
}

export function readMerge(body: unknown): { unit_ids: string[] } | null {
  if (!isObject(body) || !exactly(body, ["unit_ids"])) return null;
  const { unit_ids } = body;
  if (!Array.isArray(unit_ids) || unit_ids.length < 2 || unit_ids.length > 50 || !unit_ids.every(isSubjectId)) return null;
  return { unit_ids };
}

export function readSave(body: unknown): { units: { unit_id: string; version: number }[] } | null {
  if (!isObject(body) || !exactly(body, ["units"])) return null;
  const { units } = body;
  if (!Array.isArray(units) || units.length < 1 || units.length > 200) return null;
  const found: { unit_id: string; version: number }[] = [];
  for (const item of units) {
    if (!isObject(item) || !exactly(item, ["unit_id", "version"])) return null;
    const { unit_id, version } = item;
    if (!isSubjectId(unit_id) || !Number.isSafeInteger(version) || (version as number) < 1) return null;
    found.push({ unit_id, version: version as number });
  }
  return { units: found };
}
