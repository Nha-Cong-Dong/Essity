import { notFound, redirect } from "next/navigation";

import { SubjectList } from "@/components/subjects/subject-list";
import { SubjectsFrame } from "@/components/subjects/subjects-frame";
import { Button } from "@/components/ui/button";
import { CoreStatusError, findSubject, listSubjects, type Subject } from "@/lib/subjects";
import { errorName, logError } from "@/lib/log";

/** A session that ended between the page's check and core-api's answer is a sign-in, not a failure. */
function redirectIfSignedOut(error: unknown): void {
  if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
}

/**
 * The subject of /subjects/[id]/upload (plan K5): someone else's, a missing one or an id that is
 * not one is a 404; a session that ended goes to /login (review 796071c #1).
 */
export async function subjectForUpload(id: string): Promise<Subject> {
  let subject: Subject | null;
  try {
    subject = await findSubject(id);
  } catch (error) {
    redirectIfSignedOut(error);
    throw error;
  }
  if (subject === null) notFound();
  return subject;
}

/**
 * /subjects below its shell (T1.20, DESIGN.md §6.8), for a page that has checked the session: the
 * frame with its title, then the list or the error. One primary button: "Tạo môn" beside the title,
 * or in the empty state (SubjectList, T2.3b plan F9, T2.3c plan G15).
 */
export async function Subjects({ example }: { example: string }) {
  let subjects: Subject[];
  try {
    subjects = await listSubjects();
  } catch (error) {
    redirectIfSignedOut(error);
    // The status and the error's type only: nothing the user wrote (ADR-0013).
    logError("core-api call failed", {
      route: "subjects",
      status: error instanceof CoreStatusError ? error.status : undefined,
      error: errorName(error),
    });
    return (
      <SubjectsFrame>
        <div role="alert" className="flex flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
          <p className="m-0 font-semibold">Không tải được danh sách môn.</p>
          <p className="m-0 text-ink-soft">Kiểm tra kết nối rồi thử lại.</p>
          <Button render={<a href="/subjects" />} nativeButton={false} variant="secondary" className="mt-3">
            Thử lại
          </Button>
        </div>
      </SubjectsFrame>
    );
  }
  const listed = subjects.map(({ id, name, exam_date, days_until_exam, has_history }) => ({
    id,
    name,
    exam_date,
    days_until_exam,
    has_history,
  }));
  // "Tạo môn" lives in SubjectList: it moves to the empty state when the last subject is deleted.
  return <SubjectList subjects={listed} example={example} />;
}
