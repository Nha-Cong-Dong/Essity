import { go } from "@/lib/navigate";

// T4.6 (US-01 AC7): one PDF from the browser to storage. Ask web for a signed URL, send the file
// straight to storage with the headers core-api signed, then confirm. The URL is a secret for a few
// minutes: it is held in a variable, never logged, never put in a message or in the page.

/** core-api's per-file limit (document_max_bytes, 100 MiB, decided 26/10); it checks again. */
export const MAX_FILE_BYTES = 100 * 1024 * 1024;

export type FileProblem = "not_pdf" | "too_big" | "empty";

/** Why a chosen file is not sent, before anything leaves the browser. */
export function checkFile(file: { name: string; size: number }): FileProblem | null {
  if (!/\.pdf$/i.test(file.name)) return "not_pdf";
  if (file.size === 0) return "empty";
  if (file.size > MAX_FILE_BYTES) return "too_big";
  return null;
}

/** Lowercase hex SHA-256 of the file, as core-api asks for it. */
export async function sha256Hex(file: Blob): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export type UploadState =
  | { kind: "hashing" }
  | { kind: "uploading"; percent: number }
  | { kind: "checking" }
  | { kind: "done"; documentId?: string }
  | { kind: "failed"; code: string };

type Signed = { url: string; headers: Record<string, string> };
type Asked = { document: { id: string }; upload: Signed | null };

export type PutFile = (
  signed: Signed,
  file: Blob,
  onProgress: (percent: number) => void,
) => Promise<number>;

/** PUT with XMLHttpRequest, the only way a browser reports upload progress. Resolves the status. */
export const putFile: PutFile = (signed, file, onProgress) =>
  new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", signed.url);
    for (const [name, value] of Object.entries(signed.headers)) request.setRequestHeader(name, value);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress(Math.floor((event.loaded / event.total) * 100));
    };
    request.onload = () => resolve(request.status);
    request.onerror = () => reject(new Error("network"));
    request.onabort = () => reject(new Error("network"));
    request.send(file);
  });

export async function post<T>(path: string, body: object): Promise<{ ok: true; data: T } | { ok: false; code: string }> {
  let response: Response;
  try {
    response = await fetch(path, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { ok: false, code: "offline" };
  }
  if (response.status === 401) {
    go("/login");
    return { ok: false, code: "signed_out" };
  }
  const json: unknown = await response.json().catch(() => null);
  if (response.ok && json !== null) return { ok: true, data: json as T };
  const error = (json as { error?: unknown } | null)?.error;
  return { ok: false, code: typeof error === "string" ? error : "unavailable" };
}

/**
 * Sends `file` to the subject, reporting each step through `onState`; the last call is "done" or
 * "failed" with a code (core-api's, or offline, upload_expired, upload_failed, signed_out).
 */
export async function uploadPdf(
  subjectId: string,
  file: File,
  onState: (state: UploadState) => void,
  put: PutFile = putFile,
): Promise<void> {
  const fail = (code: string) => onState({ kind: "failed", code });
  onState({ kind: "hashing" });
  const sha256 = await sha256Hex(file);

  const asked = await post<Asked>(`/api/subjects/${subjectId}/documents`, {
    filename: file.name,
    size_bytes: file.size,
    sha256,
  });
  if (!asked.ok) return fail(asked.code);

  const { document, upload } = asked.data;
  if (upload !== null) {
    onState({ kind: "uploading", percent: 0 });
    let status: number;
    try {
      status = await put(upload, file, (percent) => onState({ kind: "uploading", percent }));
    } catch {
      return fail("offline");
    }
    // 412: the file is already there (If-None-Match): confirm it. 403: the URL has expired.
    if (status === 403) return fail("upload_expired");
    if (!(status >= 200 && status < 300) && status !== 412) return fail("upload_failed");
  }

  onState({ kind: "checking" });
  const confirmed = await post<unknown>(`/api/documents/${document.id}/confirm`, {});
  if (!confirmed.ok) return fail(confirmed.code);
  onState({ kind: "done", documentId: document.id });
}
