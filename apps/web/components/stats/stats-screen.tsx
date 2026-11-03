"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/sheet";
import type { GridCell } from "@/lib/stats";
import { NO_TOTALS, type StatsView } from "@/lib/stats-view";

import { ActivityGrid } from "./activity-grid";

// T9.5a (US-10 AC1-AC7, AC10; DESIGN §6.13, .work/T9.5a/design-decisions.md): the Thống kê screen
// from typed fixtures, no API. A read-only screen: the normal state has no primary button. A
// primary appears only where there is nothing to read (error, nothing yet, or a scope with no day
// recorded): at most one per state. No verdict, no ranking, no comparison anywhere.

function Skeleton() {
  return (
    <div aria-busy="true" aria-label="Đang tải thống kê" className="mt-6 flex flex-col gap-4">
      {[0, 1].map((i) => (
        <div key={i} className="h-40 rounded-sheet bg-sunken motion-safe:animate-pulse" aria-hidden="true" />
      ))}
      <div className="h-64 rounded-sheet bg-sunken motion-safe:animate-pulse" aria-hidden="true" />
    </div>
  );
}

function Kpi({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Sheet className="min-w-0" data-kpi>
      <p className="m-0 text-meta text-ink-soft">{label}</p>
      <p className="m-0 mt-1 text-title tabular-nums">{value}</p>
      {note && <p className="m-0 mt-1 text-meta text-ink-soft">{note}</p>}
    </Sheet>
  );
}

/** Work per week (cards saved + questions answered) for the last 12 weeks, oldest first. */
export function weeklyTrend(cells: GridCell[], weeks = 12): number[] {
  const last = cells.length === 0 ? 0 : cells[cells.length - 1].column;
  const out = Array.from({ length: weeks }, () => 0);
  for (const c of cells) {
    const slot = c.column - (last - weeks + 1);
    if (slot >= 0 && slot < weeks) out[slot] += c.cardsSaved + c.questionsAnswered;
  }
  return out;
}

function Trend({ cells }: { cells: GridCell[] }) {
  const weeks = weeklyTrend(cells);
  const top = Math.max(...weeks, 1);
  return (
    <Sheet className="min-w-0" aria-labelledby="trend-h" role="region">
      <h2 id="trend-h" className="m-0 mb-1 text-read font-semibold">
        12 tuần gần đây
      </h2>
      <p className="m-0 mb-3 text-meta text-ink-soft">Thẻ đã lưu và câu đã làm theo từng tuần.</p>
      <div className="flex h-28 items-end gap-1.5" data-trend>
        {weeks.map((n, i) => (
          <div key={i} className="flex h-full min-w-0 flex-1 flex-col justify-end" title={`${n}`}>
            <div
              className="w-full rounded-t-sm bg-spine"
              style={{ height: `${n === 0 ? 2 : Math.max((n / top) * 100, 6)}%`, opacity: n === 0 ? 0.3 : 1 }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex justify-between text-meta text-ink-soft">
        <span>12 tuần trước</span>
        <span>Tuần này</span>
      </div>
    </Sheet>
  );
}

function ErrorState({ onRetry }: { onRetry: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <div ref={ref} role="alert" tabIndex={-1} className="mt-8 flex flex-col items-start gap-4 outline-none">
      <p className="m-0 text-read">
        Không tải được thống kê.
      </p>
      <Button type="button" onClick={onRetry}>
        Thử lại
      </Button>
    </div>
  );
}

/** The loading state without hooks, so a Suspense fallback can prerender it. */
export function StatsLoading() {
  return (
    <>
      <h1 className="m-0 text-title">Thống kê</h1>
      <Skeleton />
    </>
  );
}

export type StatsMode = "ready" | "loading" | "error";

/** Overall statistics only (I1): totals, a 12-week trend and the year heatmap (I2). */
export function StatsScreen({
  view,
  mode = "ready",
}: {
  view: StatsView;
  subject?: string;
  mode?: StatsMode;
}) {
  const router = useRouter();
  const subjects = view.subjects;
  const cells = view.cells;
  const t = view.totals ?? NO_TOTALS;
  const examBy: Record<string, string[]> = {};
  for (const s of subjects) if (s.examOn) (examBy[s.examOn] ??= []).push(s.name);

  if (mode === "loading") return <StatsLoading />;
  if (mode === "error") {
    return (
      <>
        <h1 className="m-0 text-title">Thống kê</h1>
        <ErrorState onRetry={() => router.refresh()} />
      </>
    );
  }
  if (subjects.length === 0) {
    return (
      <>
        <h1 className="m-0 text-title">Thống kê</h1>
        <div className="mt-8 flex flex-col items-start gap-4">
          <p className="m-0 max-w-xl text-read">
            Thống kê hiện sau tuần học đầu tiên. Tạo một môn rồi nộp bài ở buổi học đầu tiên để bắt đầu.
          </p>
          <Button render={<a href="/subjects/new" />} nativeButton={false}>
            Tạo môn
          </Button>
        </div>
      </>
    );
  }

  const hasDays = cells.some((c) => c.cardsSaved + c.questionsAnswered > 0);
  return (
    <>
      <div className="flex flex-col gap-4 min-[768px]:flex-row min-[768px]:items-end min-[768px]:justify-between">
        <div>
          <h1 className="m-0 text-title">Thống kê</h1>
          <p className="m-0 mt-1 text-meta text-ink-soft">Tổng quan việc học của bạn, mọi môn cộng lại.</p>
        </div>
        <Button
          render={<a href="/api/export" download />}
          nativeButton={false}
          variant="secondary"
          className="max-sm:w-full"
        >
          Tải dữ liệu (CSV)
        </Button>
      </div>

      <div
        className="mt-8 grid gap-(--bento-gap) [grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr))]"
        data-totals
      >
        <Kpi
          label="Nội dung đã học"
          value={`${t.unitsLearned}`}
          note={`/ ${t.unitsTotal} mục · ${t.sessions} buổi học`}
        />
        <Kpi label="Thẻ đã ôn" value={`${t.cardsReviewed}`} note={`${t.cardsSaved} thẻ đã lưu`} />
        <Kpi label="Câu luyện tập đã làm" value={`${t.practiceDone}`} />
      </div>

      <div className="mt-(--bento-gap)">
        <Trend cells={cells} />
      </div>

      <Sheet id="activity" className="mt-(--bento-gap) min-w-0" aria-labelledby="activity-h" role="region">
        <h2 id="activity-h" className="m-0 mb-4 text-read font-semibold">
          Hoạt động cả năm
        </h2>
        {hasDays ? null : (
          <div className="mb-4 flex flex-col items-start gap-3">
            <p className="m-0">Chưa có ngày nào học. Ô sẽ đậm lên khi bạn lưu thẻ hoặc làm câu hỏi.</p>
            <Button render={<a href="/today" />} nativeButton={false}>
              Vào buổi học
            </Button>
          </div>
        )}
        <ActivityGrid
          cells={cells}
          today={view.today}
          subjects={subjects.map((s) => ({ id: s.id, name: s.name }))}
          examBy={examBy}
        />
      </Sheet>
    </>
  );
}
