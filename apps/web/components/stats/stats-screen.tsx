"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { Button } from "@/components/ui/button";
import { Watermark } from "@/components/motifs";
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

/** Phase B: the first number of the page is the one solid pink block; the others are quiet. */
function Kpi({ label, value, note, lead = false }: { label: string; value: string; note?: string; lead?: boolean }) {
  if (lead) {
    return (
      <div data-surface="hong" data-kpi className="min-w-0 rounded-tile p-8">
        <p className="m-0 text-read">{label}</p>
        <p className="m-0 mt-1 font-display text-mega tabular-nums">{value}</p>
        {note && <p className="m-0 mt-1 text-meta">{note}</p>}
      </div>
    );
  }
  return (
    <Sheet variant="tile" tone="rose" className="min-w-0 self-start" data-kpi>
      <p className="m-0 text-meta text-ink-soft">{label}</p>
      <p className="m-0 mt-1 font-display text-display tabular-nums">{value}</p>
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
              className="w-full rounded-control bg-spine"
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
      <div className="relative">
        <Watermark />
        <h1 className="relative z-1 m-0 text-title">Thống kê</h1>
        <div className="relative z-1 mt-8 flex flex-col items-start gap-4">
          <p className="m-0 max-w-xl text-read">
            Thống kê hiện sau tuần học đầu tiên. Tạo một môn rồi nộp bài ở buổi học đầu tiên để bắt đầu.
          </p>
          <Button render={<a href="/subjects/new" />} nativeButton={false}>
            Tạo môn
          </Button>
        </div>
      </div>
    );
  }

  const hasDays = cells.some((c) => c.cardsSaved + c.questionsAnswered > 0);
  return (
    <>
      <div className="flex flex-col gap-4 min-[768px]:flex-row min-[768px]:items-end min-[768px]:justify-between">
        <div>
          <h1 className="m-0 font-display text-display">
            <span className="px-1" style={{ backgroundImage: "linear-gradient(to top, var(--hl-band) 35%, transparent 35%)" }}>Thống kê</span>
          </h1>
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

      <div className="mt-8 grid gap-(--bento-gap) min-[901px]:grid-cols-12" data-totals>
        <div className="min-[901px]:col-span-7 [&>*]:h-full">
          <Kpi
            lead
            label="Nội dung đã học"
            value={`${t.unitsLearned}`}
            note={`/ ${t.unitsTotal} phần · ${t.sessions} buổi học`}
          />
        </div>
        <div className="grid gap-(--bento-gap) min-[901px]:col-span-5 [grid-template-columns:repeat(auto-fit,minmax(min(100%,200px),1fr))] min-[901px]:grid-cols-1">
          <Kpi label="Thẻ đã ôn" value={`${t.cardsReviewed}`} note={`${t.cardsSaved} thẻ đã lưu`} />
          <Kpi label="Câu luyện tập đã làm" value={`${t.practiceDone}`} />
        </div>
      </div>

      <div className="mt-(--bento-gap) grid gap-(--bento-gap) min-[901px]:grid-cols-12">
        <div className="min-w-0 min-[901px]:col-span-5 [&>*]:h-full">
          <Trend cells={cells} />
        </div>
        <Sheet variant="tile" tone="rose" className="min-w-0 min-[901px]:col-span-7" aria-labelledby="subjects-h" role="region">
          <h2 id="subjects-h" className="m-0 mb-3 text-read font-semibold">
            Môn đang học
          </h2>
          <ul className="m-0 grid list-none gap-2 p-0 [grid-template-columns:repeat(auto-fill,minmax(min(100%,200px),1fr))]">
            {subjects.map((s) => (
              <li key={s.id} className="flex min-w-0 flex-col rounded-control bg-sheet px-3 py-2">
                <span className="font-semibold wrap-anywhere">{s.name}</span>
                <span className="text-meta text-ink-soft">{s.examOn ? `Thi ${s.examOn}` : "Chưa có ngày thi"}</span>
              </li>
            ))}
          </ul>
        </Sheet>
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
