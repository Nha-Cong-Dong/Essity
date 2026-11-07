"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { Doodle } from "@/components/icons/doodle";
import { Button } from "@/components/ui/button";
import { Mascot } from "@/components/mascot";
import { NxList } from "@/components/ui/nx-list";
import { Sheet } from "@/components/ui/sheet";
import { formatExamDate } from "@/lib/exam-date";
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

/** V4: the three totals sit on the field block (tier 1, one per screen); the lead one is the screen's answer. */
function Kpi({ label, value, note, lead = false }: { label: string; value: string; note?: string; lead?: boolean }) {
  return (
    <div data-kpi className="min-w-0 px-6 py-5 max-[900px]:px-4 max-[900px]:py-4 min-[901px]:[&:not(:first-of-type)]:border-l min-[901px]:[&:not(:first-of-type)]:border-on-plum-soft/20 max-[900px]:[&:not(:first-of-type)]:border-t max-[900px]:[&:not(:first-of-type)]:border-on-plum-soft/20">
      <p className="m-0 text-meta text-on-plum-soft">{label}</p>
      <p className={`m-0 my-1.5 font-display tabular-nums text-on-plum ${lead ? "text-display" : "text-title"}`}>{value}</p>
      {note && <p className="m-0 text-meta text-on-plum-soft">{note}</p>}
    </div>
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
    <Sheet className="flex min-w-0 flex-col" aria-labelledby="trend-h" role="region">
      <h2 id="trend-h" className="m-0 mb-1 text-read font-semibold">
        12 tuần gần đây
      </h2>
      <p className="m-0 mb-3 text-meta text-ink-soft">Thẻ đã lưu và câu đã làm theo từng tuần.</p>
      <div className="flex min-h-28 flex-1 items-end gap-2 min-[901px]:gap-3.5" data-trend>
        {weeks.map((n, i) => (
          <div key={i} className="flex h-full min-w-0 flex-1 flex-col justify-end" title={`${n}`}>
            <div
              className={`w-full rounded-control ${i === weeks.length - 1 ? "bg-now inset-ring-[1.5px] inset-ring-ink" : "bg-hong"}`}
              style={{ height: `${n === 0 ? 2 : Math.max((n / top) * 100, 6)}%`, opacity: n === 0 ? 0.3 : i === weeks.length - 1 ? 1 : 0.78 }}
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
      <div>
        <h1 className="m-0 text-title">Thống kê</h1>
        <div className="mt-8 flex flex-col items-start gap-4">
          <Mascot pose="cho" size="lg" className="size-18" />
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
      <div className="grid gap-x-4 gap-y-3 min-[901px]:grid-cols-12 min-[901px]:items-end">
        <div className="min-[901px]:col-span-8">
          <h1 className="m-0 text-title text-balance">Thống kê</h1>
          <p className="m-0 mt-2 text-body text-ink-soft">Tổng quan việc học của bạn, mọi môn cộng lại.</p>
        </div>
        <div className="min-[901px]:col-span-4 min-[901px]:justify-self-end">
          <a
            href="/api/export"
            download
            className="inline-flex min-h-11 items-center text-meta hover:text-ink rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line-strong hover:bg-sunken"
          >
            Tải dữ liệu (CSV)
          </a>
        </div>
      </div>

      <section
        aria-label="Tổng quan"
        className="relative mt-7 grid rounded-tile bg-field text-on-plum min-[901px]:grid-cols-3"
        data-totals
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 100 100"
          className="pointer-events-none absolute -top-4 right-5 z-10 w-14 rotate-12 fill-hl stroke-bg [stroke-width:5] max-[900px]:hidden"
        >
          <path d="M50 3 L59 29 L86 19 L71 43 L97 58 L68 63 L72 95 L50 74 L28 95 L32 63 L3 58 L29 43 L14 19 L41 29 Z" />
        </svg>
        <Kpi
          lead
          label="Nội dung đã học"
          value={`${t.unitsLearned}`}
          note={`/ ${t.unitsTotal} phần · ${t.sessions} buổi học`}
        />
        <Kpi label="Thẻ đã ôn" value={`${t.cardsReviewed}`} note={`${t.cardsSaved} thẻ đã lưu`} />
        <Kpi label="Câu luyện tập đã làm" value={`${t.practiceDone}`} />
      </section>

      <div className="mt-5 grid gap-x-5 gap-y-8 min-[901px]:grid-cols-12">
        <div className="min-w-0 min-[901px]:col-span-7 [&>*]:h-full">
          <Trend cells={cells} />
        </div>
        <NxList title="Môn đang học" className="min-[901px]:col-span-5">
          {subjects.map((s) => (
            <li key={s.id} className="min-h-12 rounded-row bg-bg px-3.5 py-2.5">
              <span className="block font-semibold [overflow-wrap:anywhere]">{s.name}</span>
              <span className="block text-meta text-ink-soft">
                {s.examOn ? `Thi ${formatExamDate(s.examOn)}` : "Chưa có ngày thi"}
              </span>
            </li>
          ))}
        </NxList>
      </div>

      <Sheet id="activity" className="mt-5 min-w-0" aria-labelledby="activity-h" role="region">
        <h2 id="activity-h" className="m-0 mb-4 text-read font-semibold">
          Hoạt động cả năm
        </h2>
        {hasDays ? null : (
          <div className="mb-4 flex flex-col items-start gap-3" data-empty-doodle>
            <Doodle name="dong-ho-cat" size={48} className="text-hong-text" />
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
