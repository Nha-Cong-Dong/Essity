import "server-only";

import { cookies } from "next/headers";

import { type components, coreClient } from "@/lib/core-client";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";
import { parseToc, type TocEntry } from "@/lib/toc";

// T4.9 (US-01, US-02 AC2): the documents of a subject and one document's table of contents, read on
// the server for the pages under /subjects/[id].

export type Document = components["schemas"]["DocumentOut"];

export type TocResult =
  | { kind: "ok"; entries: TocEntry[] }
  // core-api answered, but the JSON is not toc.v1 (or core-api itself says toc_invalid).
  | { kind: "unreadable" }
  | { kind: "not_indexed" };

async function token(): Promise<string | undefined> {
  return (await cookies()).get(SESSION_COOKIE)?.value;
}

/** The subject's documents, oldest first. Throws CoreStatusError (404 = not the user's subject). */
export async function listDocuments(subjectId: string): Promise<Document[]> {
  if (!isSubjectId(subjectId)) throw new CoreStatusError("/v1/subjects/{id}/documents", 404);
  const { data, response } = await coreClient({ token: await token() }).GET(
    "/v1/subjects/{subject_id}/documents",
    { params: { path: { subject_id: subjectId } } },
  );
  if (!data) throw new CoreStatusError("/v1/subjects/{id}/documents", response.status);
  return data;
}

/** One document of the user's. Throws CoreStatusError (404 = not theirs, or not a UUID). */
export async function readDocument(id: string): Promise<Document> {
  if (!isSubjectId(id)) throw new CoreStatusError("/v1/documents/{id}", 404);
  const { data, response } = await coreClient({ token: await token() }).GET("/v1/documents/{document_id}", {
    params: { path: { document_id: id } },
  });
  if (!data) throw new CoreStatusError("/v1/documents/{id}", response.status);
  return data;
}

/** The toc of an indexed document. Throws CoreStatusError for anything but 409/502 refusals. */
export async function readToc(id: string): Promise<TocResult> {
  if (!isSubjectId(id)) throw new CoreStatusError("/v1/documents/{id}/toc", 404);
  const { data, response } = await coreClient({ token: await token() }).GET("/v1/documents/{document_id}/toc", {
    params: { path: { document_id: id } },
  });
  if (data) {
    const entries = parseToc(data.toc);
    return entries === null ? { kind: "unreadable" } : { kind: "ok", entries };
  }
  if (response.status === 409) return { kind: "not_indexed" };
  if (response.status === 502) return { kind: "unreadable" };
  throw new CoreStatusError("/v1/documents/{id}/toc", response.status);
}
