import { redirect } from "next/navigation";
import { connection } from "next/server";

import { LogSession } from "@/components/log-session";
import { PageColumn } from "@/components/shells";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { Sheet } from "@/components/ui/sheet";
import { requireVerifiedSession } from "@/lib/session";
import { newSessionTarget } from "@/lib/session-study/entry";
import { isSubjectId } from "@/lib/subject-id";

// T7.17: without ?session= this opens the v2 study session (/sessions/study). The v1 page below
// stays for old ?session= addresses until T7.6.
// T4.13a (US-02 AC1, DESIGN.md §6.10): one page, a sentence and what the app understood. Someone
// else's subject, or an id that is not one, shows the not-found page (same check as the upload
// step); a session that ended goes to /login.
export async function NewSessionEntry({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ session?: string | string[]; v1?: string | string[]; section?: string | string[] }>;
}) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  const { session, v1, section } = await searchParams;
  const target = newSessionTarget(subject.id, session, v1, section);
  if (target) redirect(target);
  const saved = typeof session === "string" && isSubjectId(session) ? session : undefined;
  return (
    <PageColumn width="full">
      <a href={`/subjects/${subject.id}/documents`} className="inline-flex min-h-11 w-fit items-center rounded-full bg-sheet px-4 text-meta font-medium text-ink no-underline inset-ring-1 inset-ring-line hover:bg-sunken">
        ← {subject.name}
      </a>
      <Sheet className="relative mt-3" aria-labelledby="log-title">
        <LogSession subjectId={subject.id} subjectName={subject.name} savedSessionId={saved} />
      </Sheet>
    </PageColumn>
  );
}
