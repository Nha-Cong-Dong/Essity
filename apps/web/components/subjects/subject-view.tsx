import { Marker } from "@/components/notebook";
import { PageColumn } from "@/components/shells";
import { CoverageBar } from "@/components/stats/stat-tile";
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
  prog,
  state,
  nothingDue,
  dueCards,
  questions,
  stats,
  rowEntries,
  nodes,
}: {
  subject: { id: string; name: string; exam_date: string; days_until_exam: number };
  prog: { done: number; total: number } | null;
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
      Thi vào {dayLabel(subject.exam_date)}
      {subject.days_until_exam >= 0 ? "" : " (đã qua)"}
    </>
  );
  return (
    <PageColumn width="full" className="flex flex-col gap-10">
      {/* V22 row 0: the name (cols 1-8, two lines at most) and the one big number (cols 9-12). */}
      <header className="grid items-end gap-x-6 gap-y-3 min-[901px]:grid-cols-12">
        <div className="flex min-w-0 flex-col gap-3 min-[901px]:col-span-8">
          <a href="/subjects" className="inline-flex min-h-11 w-fit items-center rounded-full bg-sheet px-4 text-meta font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken">
            Môn học ›
          </a>
          <h1 className="m-0 max-w-full font-display text-title break-words text-balance">
            {subject.name}
          </h1>
          <p className="m-0 text-body text-ink-soft">{examLine}</p>
        </div>
        {subject.days_until_exam > 0 && (
          <p className="m-0 flex items-baseline gap-2 min-[901px]:col-span-4 min-[901px]:justify-end" data-days-left>
            <span className="font-display text-display font-medium tabular-nums">{subject.days_until_exam}</span>
            <span className="text-body text-ink-soft">ngày nữa thi</span>
          </p>
        )}
        {prog !== null && prog.total > 0 && (
          <div className="flex flex-col gap-2 min-[901px]:col-span-8" data-subject-progress>
            <CoverageBar percent={(prog.done / prog.total) * 100} />
            <p className="m-0 text-meta text-ink-soft">
              Đã học {prog.done}/{prog.total} phần
            </p>
          </div>
        )}
      </header>
      <div className="grid min-w-0 gap-x-4 gap-y-10 min-[901px]:grid-cols-12">
        <div className="flex min-w-0 flex-col gap-10 min-[901px]:col-span-8">
          <SubjectScreenBlock subjectId={subject.id} subjectName={subject.name} state={state} nothingDue={nothingDue} />
          {/* UI-C: review and practice side by side (7/5), the entry row below. */}
          <div className="grid min-w-0 items-start gap-x-4 gap-y-6 min-[1100px]:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
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
        <div className="flex min-w-0 flex-col gap-10 min-[901px]:col-span-4">
          {stats !== null && <SubjectStatsBlock stats={stats} />}
          {nodes !== null && <SubjectOutlineAside nodes={nodes} subjectId={subject.id} />}
        </div>
      </div>
    </PageColumn>
  );
}
