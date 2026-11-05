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
    <section aria-label="Luyện tập" data-subject-practice className="flex min-w-0 flex-col items-start gap-3 rounded-tile bg-sheet p-5 shadow-sheet min-[901px]:p-6">
      <h2 className="m-0 font-display text-tile">Luyện tập</h2>
      {empty ? (
        <p className="m-0 text-body text-ink-soft">Chưa có bộ câu hỏi. Tải bộ câu hỏi để luyện đúng dạng đề thi.</p>
      ) : (
        <>
          <p className="m-0 flex items-baseline gap-2" data-due-today>
            <span className="font-display text-verdict leading-none font-semibold tracking-[-0.03em] tabular-nums">{dueToday === null ? ready : dueToday}</span>{" "}
            <span className="text-lead font-semibold">{dueToday === null ? "câu sẵn sàng" : "câu cần luyện hôm nay"}</span>
          </p>
          <p className="m-0 text-meta text-ink-soft">
            Đã mở khóa {ready}/{total} câu
          </p>
        </>
      )}
      <div>
        <Button variant="quiet" render={<a href={empty ? `/subjects/${subjectId}/upload` : `/subjects/${subjectId}/practice`} />} nativeButton={false}>
          {empty ? "Tải bộ câu hỏi" : "Luyện tập"}
        </Button>
      </div>
    </section>
  );
}
