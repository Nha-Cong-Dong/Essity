import { type PutFile, post, putFile, sha256Hex } from "@/lib/upload-client";

// T7.12c (US-02 AC1, AC13): one file of a study session's submission (a notebook photo, a PDF, a
// Word or PowerPoint file, a text note) from the browser to storage. Ask web for a signed URL,
// send the file straight to storage with the headers core-api signed, hand back what the
// submission names: hash, type, size. The URL is a secret for a few minutes: held in a variable,
// never logged or shown (ADR-0013).

/** core-api's per-file limit (note_max_bytes, 20 MiB); it checks again. */
export const FILE_MAX_BYTES = 20 * 1024 * 1024;

const DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation";

export type SubmissionMime = "image/jpeg" | "image/png" | "application/pdf" | "text/plain" | "text/markdown" | typeof DOCX | typeof PPTX;
export type FileRef = { sha256: string; mime: SubmissionMime; size_bytes: number };

const BY_EXTENSION: Record<string, SubmissionMime> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  pdf: "application/pdf",
  txt: "text/plain",
  md: "text/markdown",
  docx: DOCX,
  pptx: PPTX,
};
const KNOWN = new Set<string>(Object.values(BY_EXTENSION));

/** The type to declare for a chosen file, or null when core-api does not take it. */
export function submissionMime(file: { name: string; type: string }): SubmissionMime | null {
  if (KNOWN.has(file.type)) return file.type as SubmissionMime;
  const extension = /\.([a-z0-9]+)$/i.exec(file.name)?.[1]?.toLowerCase();
  return (extension && BY_EXTENSION[extension]) || null;
}

export type FileProblem = "unsupported" | "empty" | "too_big";

/** Why a chosen file is not sent, before anything leaves the browser. */
export function checkSubmissionFile(file: { name: string; type: string; size: number }): FileProblem | null {
  if (submissionMime(file) === null) return "unsupported";
  if (file.size === 0) return "empty";
  if (file.size > FILE_MAX_BYTES) return "too_big";
  return null;
}

export type FileState =
  | { kind: "uploading"; percent: number }
  | { kind: "ready"; ref: FileRef }
  | { kind: "failed"; code: string };

type Signed = { url: string; headers: Record<string, string> };

/** The last call of `onState` is "ready" or "failed" with a code (core-api's, or offline, upload_expired, upload_failed, signed_out). */
export async function uploadSubmissionFile(
  sessionId: string,
  file: File,
  onState: (state: FileState) => void,
  put: PutFile = putFile,
): Promise<void> {
  const fail = (code: string) => onState({ kind: "failed", code });
  const problem = checkSubmissionFile(file);
  if (problem !== null) return fail(problem);
  const mime = submissionMime(file) as SubmissionMime;
  onState({ kind: "uploading", percent: 0 });
  const ref: FileRef = { sha256: await sha256Hex(file), mime, size_bytes: file.size };

  const asked = await post<Signed>(`/api/sessions/${sessionId}/notes/upload-url`, ref);
  if (!asked.ok) return fail(asked.code);

  let status: number;
  try {
    status = await put(asked.data, file, (percent) => onState({ kind: "uploading", percent }));
  } catch {
    return fail("offline");
  }
  // 412: the file is already there (If-None-Match). 403: the URL expired.
  if (status === 403) return fail("upload_expired");
  if (!(status >= 200 && status < 300) && status !== 412) return fail("upload_failed");
  onState({ kind: "ready", ref });
}

/** The row state a failure shows: a wrong type or a big file is told as such, anything else is a retry. */
export function rowStateOf(code: string): "bad-type" | "too-big" | "net-error" {
  if (code === "unsupported" || code === "empty" || code === "bad_note") return "bad-type";
  if (code === "too_big" || code === "file_too_large") return "too-big";
  return "net-error";
}
