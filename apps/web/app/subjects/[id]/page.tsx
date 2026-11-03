import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AccountSlot } from "@/components/account-slot";
import { AppShell, PageColumn } from "@/components/shells";
import { SubjectEntryRow } from "@/components/subjects/subject-entry-row";
import { SubjectScreenBlock } from "@/components/subjects/subject-screen";
import { subjectForUpload } from "@/components/subjects/subjects-loader";
import { dayLabel } from "@/lib/today-copy";
import { requireVerifiedSession } from "@/lib/session";
import { errorName, logError } from "@/lib/log";
import { CoreStatusError } from "@/lib/subjects";
import { loadGraph } from "@/lib/graph-load";
import { loadOutline } from "@/lib/outline";
import { loadQuestionList } from "@/lib/question-list";
import { ReviewStack, type StackCard } from "@/components/subjects/review-stack";
import { SubjectOutlineAside } from "@/components/subjects/subject-chapters-aside";
import { SubjectStatsBlock } from "@/components/subjects/subject-stats-block";
import { CoverageBar } from "@/components/stats/stat-tile";
import { getStats } from "@/lib/stats-api";
import { outlineView } from "@/lib/syllabus/api";
import { progress } from "@/lib/syllabus/tree";
import { entryRow } from "@/lib/subject-entries";
import { getSuggestions, getToday } from "@/lib/today";
import { suggestionState } from "@/lib/today-adapt";
import type { SuggestionState } from "@/components/subjects/subject-suggestion";

export const metadata: Metadata = { title: "Môn học · Essity" };

// T7.13 (US-15 AC6, AC7; DESIGN §6.5): one subject with "Hôm nay nên học: mục X" or the
// "Gợi ý cho hôm nay" button. A failed read of the suggestions leaves the button, so the learner
// can still ask; someone else's subject or a bad id is the 404 page.
async function Subject({ params }: { params: Promise<{ id: string }> }) {
  await connection();
  await requireVerifiedSession();
  const subject = await subjectForUpload((await params).id);
  let state: SuggestionState;
  try {
    state = suggestionState(await getSuggestions(), subject.id, subject.days_until_exam);
  } catch (error) {
    if (error instanceof CoreStatusError && error.status === 401) redirect("/login");
    logError("core-api call failed", { route: "today", error: errorName(error) });
    state = subject.days_until_exam < 0 ? { kind: "exam_over" } : { kind: "not_suggested" };
  }
  // Each source stands alone: one that fails drops its own entry, never the page (DESIGN §6.5 item 4).
  // T7.19 F3: "Ôn riêng môn này" is a dead end when today's review holds nothing of this subject.
  const dueCards = await getToday()
    .then((today) =>
      today.review.items
        .filter((item) => item.subject_id === subject.id)
        .map((item) => ({ id: item.question_id, why: item.why, kind: item.item_kind, front: item.front, back: item.back })),
    )
    .catch(() => [] as StackCard[]);
  const nothingDue = dueCards.length === 0;
  const [outline, questions, graph] = await Promise.all([
    loadOutline(subject.id).catch(() => null),
    loadQuestionList(subject.id).catch(() => null),
    loadGraph(subject.id, null).catch(() => null),
  ]);
  const stats = await getStats()
    .then((r) => r.view.subjects.find((x) => x.id === subject.id) ?? null)
    .catch(() => null);
  const view = outline === null ? null : outlineView(outline);
  const prog = view?.kind === "ready" ? progress(view.nodes) : null;
  const entries = entryRow(subject.id, {
    outline,
    questions: questions && { ready: questions.ready, total: questions.total },
    graphCards: graph && graph.cards.length,
  });
  const rowEntries = entries.filter((e) => e.key !== "syllabus" && e.key !== "stats");
  return (
    <PageColumn width="full" className="flex flex-col gap-6">
      <a href="/subjects" className="text-small">
        Môn học
      </a>
      <h1 className="m-0 font-display text-title wrap-anywhere">{subject.name}</h1>
      <p className="m-0 text-read text-ink-soft">
        Thi vào {dayLabel(subject.exam_date)}
        {subject.days_until_exam >= 0 ? ` (còn ${subject.days_until_exam} ngày)` : " (đã qua)"}
      </p>
      {prog !== null && prog.total > 0 && (
        <div className="flex flex-col gap-1" data-subject-progress>
          <p className="m-0 text-meta text-ink-soft">
            Tiến độ: đã học {prog.done}/{prog.total} mục
          </p>
          <CoverageBar percent={(prog.done / prog.total) * 100} />
        </div>
      )}
      <div className="grid min-w-0 gap-6 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="flex min-w-0 flex-col gap-6">
          <div className="grid min-w-0 gap-6 md:grid-cols-2">
            <SubjectScreenBlock subjectId={subject.id} subjectName={subject.name} state={state} nothingDue={nothingDue} />
            <ReviewStack subjectId={subject.id} cards={dueCards} />
          </div>
          {stats !== null && <SubjectStatsBlock stats={stats} />}
          <SubjectEntryRow entries={rowEntries} />
        </div>
        {view?.kind === "ready" && <SubjectOutlineAside nodes={view.nodes} subjectId={subject.id} />}
      </div>
    </PageColumn>
  );
}

export default function SubjectPage({ params }: { params: Promise<{ id: string }> }) {
  return (
    <AppShell current="/subjects" account={<AccountSlot />}>
      <Suspense fallback={<PageColumn width="full" aria-busy="true" className="h-64 rounded-sheet bg-sunken" />}>
        <Subject params={params} />
      </Suspense>
    </AppShell>
  );
}
