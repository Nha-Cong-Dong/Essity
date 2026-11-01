import "server-only";

import { cookies } from "next/headers";

import { coreClient } from "@/lib/core-client";
import { listDocuments } from "@/lib/documents";
import { SESSION_COOKIE } from "@/lib/session";
import { isSubjectId } from "@/lib/subject-id";
import { CoreStatusError } from "@/lib/subjects";

import { type CoreDraft, readStatus, toDraft } from "./api";
import type { DocRef } from "./mention";
import type { SessionInitial } from "@/components/session-study/session-screen";
import { initialRound, type Round } from "./round";

// T7.12 (US-02 AC11, US-02b AC6): what the study session screen starts from, read on the server
// so leaving the page and coming back shows where the session truly is (drafts kept, reading
// still running, or a form to fill in).

const ROLE = { textbook: "Giáo trình chính", question_bank: "Ngân hàng câu hỏi", auxiliary: "Tài liệu phụ" } as const;
const UNUSABLE = new Set(["pending", "rejected", "failed"]);

export async function loadSession(subjectId: string, sessionId: string): Promise<{ docs: DocRef[]; initial: SessionInitial }> {
  if (!isSubjectId(sessionId)) throw new CoreStatusError("/v1/sessions/{id}/drafts", 404);
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const [documents, found] = await Promise.all([
    listDocuments(subjectId),
    coreClient({ token }).GET("/v1/sessions/{session_id}/drafts", { params: { path: { session_id: sessionId } } }),
  ]);
  if (!found.data) throw new CoreStatusError("/v1/sessions/{id}/drafts", found.response.status);
  const docs: DocRef[] = documents
    .filter((d) => !UNUSABLE.has(d.status))
    .map((d) => ({ id: d.id, name: d.short_name, role: ROLE[d.role] }));
  const drafts = (found.data.drafts as unknown as CoreDraft[])
    .filter((d) => d.status === "draft" || d.status === "retired")
    .map((d) => toDraft(d, docs));
  const phase = readStatus(found.data.submission_status);
  const at = (patch: Partial<Round>): Round => ({ ...initialRound, ...patch });
  // Cards on the screen mean "keep reviewing"; otherwise the reading's state decides.
  const round =
    drafts.length > 0 || phase === "done"
      ? at({ phase: "review" })
      : phase === "queued" || phase === "processing" || phase === "pending_ai" || phase === "failed"
        ? at({ phase: "processing", submission: phase })
        : initialRound;
  return {
    docs,
    initial: { round, drafts, text: "", mentions: [], files: [], scope: [], saved: "free", resumed: drafts.length > 0 },
  };
}
