import "server-only";

import { readUploadFile, type UploadFile } from "@/lib/session-routes";
import { isSubjectId } from "@/lib/subject-id";

// T7.12 (US-02): what web's routes for the study session's submission and pieces take from the browser.
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
  files: UploadFile[];
  /** T7.19 F1: the sentence again as the note, when there is no file (core-api needs a note or a file). */
  text?: string;
};

/** The description is the learner's sentence (2000 characters, T7.6) and its `@` mentions. */
export function readSubmit(body: unknown): SubmitBody | null {
  if (!isObject(body) || !exactly(body, ["session_id", "description", "mentions", "files"])) return null;
  const { session_id, description, mentions, files } = body;
  if (!isSubjectId(session_id) || typeof description !== "string" || description.length > 2000) return null;
  if (mentions !== undefined && (!Array.isArray(mentions) || mentions.length > 20)) return null;
  const found: SubmitBody["mentions"] = [];
  for (const item of mentions ?? []) {
    if (!isObject(item) || !exactly(item, ["document_id", "start", "end"])) return null;
    const { document_id, start, end } = item;
    if (!isSubjectId(document_id) || !Number.isSafeInteger(start) || !Number.isSafeInteger(end)) return null;
    found.push({ document_id, start: start as number, end: end as number });
  }
  if (files !== undefined && (!Array.isArray(files) || files.length > 20)) return null;
  const read: UploadFile[] = [];
  for (const item of files ?? []) {
    const file = readUploadFile(item);
    if (file === null) return null;
    read.push(file);
  }
  // Words alone are a note: core-api refuses a submission with neither text nor a file.
  const note = read.length === 0 && description.trim() !== "" ? { text: description } : {};
  return { session_id, description, mentions: found, files: read, ...note };
}

export type PieceBody = { text: string; mentions: SubmitBody["mentions"]; files: UploadFile[] };

/** F2: one piece of a study session ("Ghi lại"): the words, their `@` mentions and the files. */
export function readPiece(body: unknown): PieceBody | null {
  if (!isObject(body) || !exactly(body, ["text", "mentions", "files"])) return null;
  const read = readSubmit({ session_id: "00000000-0000-0000-0000-000000000000", description: body.text, mentions: body.mentions, files: body.files });
  if (read === null) return null;
  return { text: read.description, mentions: read.mentions, files: read.files };
}
