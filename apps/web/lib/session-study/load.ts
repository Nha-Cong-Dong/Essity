import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { listDocuments } from "@/lib/documents";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";

import { readStatus } from "./api";
import type { DocRef } from "./mention";
import type { SessionInitial } from "@/components/session-study/session-screen";
import { roundFromResult } from "./round";

// T7.12 (US-02 AC11, US-02b AC6): what the study session screen starts from, read on the server
// so leaving the page and coming back shows where the session truly is (reading still running, the
// result of a finished one, or a form to fill in). CARDS-V3: the cards are already in the Kho.

const ROLE = { textbook: "Giáo trình chính", question_bank: "Ngân hàng câu hỏi", auxiliary: "Tài liệu phụ" } as const;
const UNUSABLE = new Set(["pending", "rejected", "failed"]);

export async function loadSession(subjectId: string, sessionId: string): Promise<{ docs: DocRef[]; initial: SessionInitial }> {
  if (!isSubjectId(sessionId)) throw new CoreStatusError("/v1/vault/sessions/{id}/result", 404);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const [documents, found] = await Promise.all([
    listDocuments(subjectId),
    coreClient({ token }).GET("/v1/vault/sessions/{session_id}/result", { params: { path: { session_id: sessionId } } }),
  ]);
  if (!found.data) throw new CoreStatusError("/v1/vault/sessions/{id}/result", found.response.status);
  const docs: DocRef[] = documents
    .filter((d) => !UNUSABLE.has(d.status))
    .map((d) => ({ id: d.id, name: d.short_name, role: ROLE[d.role] }));
  const { cards, title, notice } = found.data;
  const round = roundFromResult(readStatus(found.data.submission_status), { cards, title, notice });
  return { docs, initial: { round, text: "", mentions: [], files: [], tooManyPages: null } };
}
