import { BackLink } from "@/components/screen-kit";
import { PageColumn } from "@/components/shells";
import { SubjectOutlineAside } from "@/components/subjects/subject-chapters-aside";
import { SubjectEntryRow } from "@/components/subjects/subject-entry-row";
import { SubjectPracticeBlock } from "@/components/subjects/subject-practice-block";
import { ReviewStack, type StackCard } from "@/components/subjects/review-stack";
import { SubjectScreenBlock } from "@/components/subjects/subject-screen";
import { SubjectStatsBlock } from "@/components/subjects/subject-stats-block";
import type { SuggestionState } from "@/components/subjects/subject-suggestion";
import type { ViewSubject } from "@/lib/stats-view";
import type { SubjectEntry } from "@/lib/subject-entries";
import type { SyllabusNode } from "@/lib/syllabus/tree";
import { dayLabel } from "@/lib/today-copy";

// V22: the one-subject screen as a value, so the page and the design preview draw the same thing.
export function SubjectView({
  subject,
  state,
  nothingDue,
  dueCards,
  questions,
  stats,
  rowEntries,
  nodes,
}: {
  subject: { id: string; name: string; exam_date: string; days_until_exam: number };
  state: SuggestionState;
  nothingDue: boolean;
  dueCards: StackCard[];
  questions: { total: number; ready: number; due_today?: number | null } | null;
  stats: ViewSubject | null;
  rowEntries: SubjectEntry[];
  nodes: SyllabusNode[] | null;
}) {
  const examLine = (
    <>
      Thi {dayLabel(subject.exam_date)}
      {subject.days_until_exam > 0 ? ` · còn ${subject.days_until_exam} ngày` : subject.days_until_exam === 0 ? " · hôm nay" : " (đã qua)"}
    </>
  );
  // SESSION-END / DESIGN-V4: no outline, no study. The field block says so and offers the textbook; the review,
  // practice, entries and numbers do not exist yet, so none of them is drawn.
  const locked = state.kind === "no_textbook";
  const nextId = state.kind === "suggested" ? (state.next.sectionId ?? null) : null;
  return (
    <PageColumn width="full" className="flex flex-col gap-6">
      <header className="flex flex-col gap-1">
        <BackLink href="/subjects">Quay lại</BackLink>
        <h1 className="m-0 max-w-full font-display text-title break-words text-balance">{subject.name}</h1>
        <p className="m-0 text-body text-ink-soft">{examLine}</p>
      </header>
      {locked ? (
        <div className="flex min-w-0 flex-col gap-5">
          <SubjectScreenBlock subjectId={subject.id} subjectName={subject.name} state={state} nothingDue={nothingDue} />
          <section aria-label="Đề cương" className="rounded-tile bg-sheet p-6 shadow-sheet">
            <h2 className="m-0 font-display text-tile">Đề cương</h2>
            <p className="m-0 mt-2 text-body text-ink-soft">Chưa có phần nào.</p>
          </section>
        </div>
      ) : (
        <div className="grid min-w-0 items-start gap-5 min-[901px]:grid-cols-12">
          <div className="flex min-w-0 flex-col gap-5 min-[901px]:col-span-8">
            <SubjectScreenBlock subjectId={subject.id} subjectName={subject.name} state={state} nothingDue={nothingDue} />
            {/* UI-C: review and practice side by side (7/5), the entry row below. */}
            <div className="grid min-w-0 items-start gap-5 min-[1100px]:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
              <ReviewStack subjectId={subject.id} cards={dueCards} />
              {questions !== null && (
                <SubjectPracticeBlock
                  subjectId={subject.id}
                  total={questions.total}
                  ready={questions.ready}
                  dueToday={questions.due_today ?? null}
                />
              )}
            </div>
            <SubjectEntryRow entries={rowEntries} />
          </div>
          <div className="flex min-w-0 flex-col gap-5 min-[901px]:col-span-4">
            {stats !== null && <SubjectStatsBlock stats={stats} />}
            {nodes !== null && <SubjectOutlineAside nodes={nodes} subjectId={subject.id} nextId={nextId} />}
          </div>
        </div>
      )}
    </PageColumn>
  );
}
