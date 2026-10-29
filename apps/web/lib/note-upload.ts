import { type PutFile, post, putFile, sha256Hex } from "@/lib/upload-client";

// T4.13b (US-02 AC13): one note file (notebook photo, PDF, text) from the browser to storage, for
// the draft session of "Ghi buổi học". Ask web for a signed URL, send the file straight to storage
// with the headers core-api signed, and hand back what confirm needs: its hash, type and size. The
// URL is a secret for a few minutes: held in a variable, never logged or shown.

/** core-api's per-file limit (note_max_bytes, 20 MiB); it checks again. */
export const NOTE_MAX_BYTES = 20 * 1024 * 1024;

export type NoteMime = "image/jpeg" | "image/png" | "application/pdf" | "text/plain" | "text/markdown";
export type NoteRef = { sha256: string; mime: NoteMime; size_bytes: number };

/** The types core-api takes, and the file extensions a browser may leave without a type. */
const BY_EXTENSION: Record<string, NoteMime> = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  pdf: "application/pdf",
  txt: "text/plain",
  md: "text/markdown",
};
const KNOWN = new Set<string>(Object.values(BY_EXTENSION));

/** The type to declare for a chosen file, or null when it is not one core-api takes. */
export function noteMime(file: { name: string; type: string }): NoteMime | null {
  if (KNOWN.has(file.type)) return file.type as NoteMime;
  const extension = /\.([a-z0-9]+)$/i.exec(file.name)?.[1]?.toLowerCase();
  return (extension && BY_EXTENSION[extension]) || null;
}

export type NoteProblem = "unsupported" | "empty" | "too_big";

/** Why a chosen file is not sent, before anything leaves the browser. */
export function checkNote(file: { name: string; type: string; size: number }): NoteProblem | null {
  if (noteMime(file) === null) return "unsupported";
  if (file.size === 0) return "empty";
  if (file.size > NOTE_MAX_BYTES) return "too_big";
  return null;
}

export type NoteState =
  | { kind: "queued" } // waits for the session to exist
  | { kind: "hashing" }
  | { kind: "uploading"; percent: number }
  | { kind: "ready"; note: NoteRef }
  | { kind: "failed"; code: string };

type Signed = { url: string; headers: Record<string, string> };

/**
 * Sends `file` to the session, reporting each step through `onState`; the last call is "ready"
 * (with the note to confirm) or "failed" with a code (core-api's, or offline, upload_expired,
 * upload_failed, signed_out).
 */
export async function uploadNote(
  sessionId: string,
  file: File,
  onState: (state: NoteState) => void,
  put: PutFile = putFile,
): Promise<void> {
  const fail = (code: string) => onState({ kind: "failed", code });
  const mime = noteMime(file);
  if (mime === null) return fail("unsupported");
  onState({ kind: "hashing" });
  const note: NoteRef = { sha256: await sha256Hex(file), mime, size_bytes: file.size };

  const asked = await post<Signed>(`/api/sessions/${sessionId}/notes/upload-url`, note);
  if (!asked.ok) return fail(asked.code);

  onState({ kind: "uploading", percent: 0 });
  let status: number;
  try {
    status = await put(asked.data, file, (percent) => onState({ kind: "uploading", percent }));
  } catch {
    return fail("offline");
  }
  // 412: the file is already there (If-None-Match), so it can be confirmed. 403: the URL expired.
  if (status === 403) return fail("upload_expired");
  if (!(status >= 200 && status < 300) && status !== 412) return fail("upload_failed");
  onState({ kind: "ready", note });
}
