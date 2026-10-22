import { redirect } from "next/navigation";

import { SubjectList } from "@/components/subjects/subject-list";
import { Button } from "@/components/ui/button";
import { CoreStatusError, listSubjects, type Subject } from "@/lib/subjects";

/**
 * The list part of /subjects (T1.20, DESIGN.md §6.8), for a page that has checked the session. One
 * primary button: "Tạo môn" above the list, or in the empty state.
 */
export async function Subjects() {
  let subjects: Subject[];
  try {
    subjects = await listSubjects();
  } catch (error) {
    // A session that ended between the two calls is a sign-in, not a network error.
    if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
    // The status and the error's type only: nothing the user wrote (ADR-0013).
    console.error("core-api call failed", {
      route: "subjects",
      status: error instanceof CoreStatusError ? error.status : undefined,
      error: error instanceof Error ? error.name : undefined,
    });
    return (
      <div role="alert" className="flex flex-col items-start gap-2 rounded-sheet bg-sunken p-6">
        <p className="m-0 font-semibold" data-copy="tam">
          Không tải được danh sách môn.
        </p>
        <p className="m-0 text-ink-soft">Kiểm tra kết nối rồi thử lại.</p>
        <Button render={<a href="/subjects" />} nativeButton={false} variant="secondary" className="mt-3">
          Thử lại
        </Button>
      </div>
    );
  }
  const listed = subjects.map(({ id, name, exam_date, days_until_exam }) => ({ id, name, exam_date, days_until_exam }));
  return (
    <>
      {listed.length > 0 && (
        <div className="-mt-16 mb-6 flex justify-end">
          <Button render={<a href="/subjects/new" />} nativeButton={false}>
            Tạo môn
          </Button>
        </div>
      )}
      <SubjectList subjects={listed} />
    </>
  );
}
