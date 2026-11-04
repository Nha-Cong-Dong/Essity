import { CoverageBar } from "@/components/stats/stat-tile";
import { NxList } from "@/components/ui/nx-list";
import type { ViewSubject } from "@/lib/stats-view";

// Hackathon D7, V22: this subject's own numbers as a tile of the landing's "nx" list: label | value.
// Only the NUMBER is display-sized; the unit is a 14px word beside it; with no data the value is "—"
// and one meta line says what to do.
function StatRow({ label, value, unit, hint }: { label: string; value: string | null; unit?: string; hint: string }) {
  return (
    <li className="min-h-12 rounded-row bg-bg px-3.5 py-2">
      <dl className="m-0 grid grid-cols-[minmax(0,1fr)_auto] items-baseline gap-x-3">
        <dt className="min-w-0 text-body break-words">{label}</dt>
        <dd className="m-0 flex items-baseline gap-1.5 justify-end">
          {value === null ? (
            <span className="text-body text-ink-soft">—</span>
          ) : (
            <>
              <span className="font-display text-lead tabular-nums">{value}</span>
              {unit ? <span className="text-meta text-ink-soft">{unit}</span> : null}
            </>
          )}
        </dd>
        {value === null && hint ? <dd className="m-0 col-span-2 text-meta text-ink-soft">{hint}</dd> : null}
      </dl>
    </li>
  );
}

export function SubjectStatsBlock({ stats }: { stats: ViewSubject }) {
  const { syllabus, bank, retention } = stats;
  const percent = syllabus.leaves > 0 ? Math.round((syllabus.studied / syllabus.leaves) * 100) : 0;
  const ready = bank?.reduce((n, t) => n + t.ready, 0) ?? 0;
  const practiced = bank?.reduce((n, t) => n + t.practiced, 0) ?? 0;
  const mastered = bank?.reduce((n, t) => n + t.mastered, 0) ?? 0;
  return (
    <div data-subject-stats aria-label="Thống kê môn" role="group" className="flex min-w-0 flex-col gap-3">
      <NxList title="Thống kê môn này">
        <StatRow label="Đã học" value={`${syllabus.studied}/${syllabus.leaves}`} unit="phần" hint="" />
        <StatRow
          label="Câu sẵn sàng"
          value={bank === null ? null : String(ready)}
          unit="câu"
          hint="Tải bộ câu hỏi để có câu luyện"
        />
        <StatRow
          label="Đã luyện / thành thạo"
          value={bank === null ? null : `${practiced}/${mastered}`}
          hint="Luyện một câu để bắt đầu"
        />
        <StatRow
          label="Nhớ tốt hôm nay"
          value={retention === null ? null : `${Math.round(retention * 100)}%`}
          hint="Học một buổi để có thẻ"
        />
      </NxList>
      <CoverageBar percent={percent} />
    </div>
  );
}
