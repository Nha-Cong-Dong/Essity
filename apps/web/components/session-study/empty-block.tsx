import { PageColumn } from "@/components/shells";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";

// SESSION-END: a subject with no outline cannot be studied (core-api answers 409 no_syllabus). Every
// way into a study session lands here, with one short line and the way on: the textbook upload.

export const NO_OUTLINE_COPY = {
  title: "Chưa có đề cương để học",
  text: "Môn này cần có đề cương trước khi học. Tải giáo trình lên để Essity đọc mục lục, rồi quay lại.",
  upload: "Tải giáo trình",
  back: "Về môn học",
} as const;

export function NoOutlineBlock({ subjectId, subjectName }: { subjectId: string; subjectName: string }) {
  return (
    <PageColumn width="full">
      <Sheet className="relative mt-3" aria-labelledby="empty-title">
        <div role="status" className="flex flex-col gap-3">
          <h1 id="empty-title" className="m-0 font-display text-title">
            {NO_OUTLINE_COPY.title}
          </h1>
          <p className="m-0 text-body">{NO_OUTLINE_COPY.text}</p>
          <div className="flex flex-wrap items-center gap-3">
            <Button render={<a href={`/subjects/${subjectId}/documents`} />} nativeButton={false}>
              {NO_OUTLINE_COPY.upload}
            </Button>
            <Button render={<a href={`/subjects/${subjectId}`} />} nativeButton={false} variant="quiet" aria-label={`${NO_OUTLINE_COPY.back} ${subjectName}`}>
              {NO_OUTLINE_COPY.back}
            </Button>
          </div>
        </div>
      </Sheet>
    </PageColumn>
  );
}
