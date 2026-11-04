import { CoverageBar } from "@/components/stats/stat-tile";
import type { ViewSubject } from "@/lib/stats-view";

// Hackathon D7, V22: this subject's own numbers. Only the NUMBER is big (serif); the unit is a
// 14px word beside it; with no data the cell shows "—" and one line that says what to do.
function Stat({ label, value, unit, hint }: { label: string; value: string | null; unit?: string; hint: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-meta text-ink-soft">{label}</dt>
      <dd className="m-0 mt-1">
        {value === null ? (
          <>
            <span className="text-body text-ink-soft">—</span>
            <span className="block text-meta text-ink-soft">{hint}</span>
          </>
        ) : (
          <span className="flex items-baseline gap-1.5">
            <span className="font-serif text-verdict font-medium tabular-nums">{value}</span>
            {unit ? <span className="text-meta text-ink-soft">{unit}</span> : null}
          </span>
        )}
      </dd>
    </div>
  );
}

export function SubjectStatsBlock({ stats }: { stats: ViewSubject }) {
  const { syllabus, bank, retention } = stats;
  const percent = syllabus.leaves > 0 ? Math.round((syllabus.studied / syllabus.leaves) * 100) : 0;
  const ready = bank?.reduce((n, t) => n + t.ready, 0) ?? 0;
  const practiced = bank?.reduce((n, t) => n + t.practiced, 0) ?? 0;
  const mastered = bank?.reduce((n, t) => n + t.mastered, 0) ?? 0;
  return (
    <section aria-label="Thống kê môn" data-subject-stats className="flex min-w-0 flex-col gap-4">
      <h2 className="m-0 text-body font-semibold">Thống kê môn này</h2>
      <dl className="m-0 grid grid-cols-2 gap-x-4 gap-y-5">
        <Stat label="Đã học" value={`${syllabus.studied}/${syllabus.leaves}`} unit="phần" hint="" />
        <Stat
          label="Câu sẵn sàng"
          value={bank === null ? null : String(ready)}
          unit="câu"
          hint="Tải bộ câu hỏi để có câu luyện"
        />
        <Stat
          label="Đã luyện / thành thạo"
          value={bank === null ? null : `${practiced}/${mastered}`}
          hint="Luyện một câu để bắt đầu"
        />
        <Stat
          label="Nhớ tốt hôm nay"
          value={retention === null ? null : `${Math.round(retention * 100)}%`}
          hint="Học một buổi để có thẻ"
        />
      </dl>
      <CoverageBar percent={percent} />
    </section>
  );
}
