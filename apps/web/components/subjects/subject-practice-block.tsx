import { Button } from "@/components/ui/button";

// V19: the practice block of the subject screen, a tile like "Thống kê môn này": how many
// questions are due today and the button into the practice screen.
export function SubjectPracticeBlock({
  subjectId,
  total,
  ready,
  dueToday,
}: {
  subjectId: string;
  total: number;
  ready: number;
  /** null: the API did not say (old data). */
  dueToday: number | null;
}) {
  const empty = total === 0;
  return (
    <section
      aria-label="Luyện tập"
      data-subject-practice
      className="flex flex-col gap-3 rounded-sheet border border-line border-t-4 border-t-hong p-6"
    >
      <h2 className="m-0 font-display text-lead">Luyện tập</h2>
      {empty ? (
        <p className="m-0 text-body text-ink-soft">Chưa có bộ câu hỏi. Tải bộ câu hỏi để luyện đúng dạng đề thi.</p>
      ) : (
        <>
          <p className="m-0 font-display text-title" data-due-today>
            {dueToday === null ? `${ready} câu sẵn sàng` : `${dueToday} câu cần luyện hôm nay`}
          </p>
          <p className="m-0 text-meta text-ink-soft">
            Đã mở khóa {ready}/{total} câu
          </p>
        </>
      )}
      <div>
        <Button render={<a href={empty ? `/subjects/${subjectId}/upload` : `/subjects/${subjectId}/practice`} />} nativeButton={false}>
          {empty ? "Tải bộ câu hỏi" : "Luyện tập"}
        </Button>
      </div>
    </section>
  );
}
