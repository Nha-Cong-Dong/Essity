import type { ViewSubject } from "@/lib/stats-view";

// Hackathon D7, V22: this subject's own numbers as a tile of the landing's "nx" list: label | value.
// Only the NUMBER is display-sized; the unit is a 14px word beside it; with no data the value is "—"
// and one meta line says what to do.
function StatRow({ label, value, unit, hint }: { label: string; value: string | null; unit?: string; hint: string }) {
  return (
    <li className="border-t border-line py-3.5 first:border-t-0">
      <dl className="m-0 grid grid-cols-[minmax(7.5rem,auto)_minmax(0,1fr)] items-baseline gap-x-4">
        <dd className="m-0 order-first flex flex-wrap items-baseline gap-x-1.5">
          {value === null ? (
            <span className="text-body text-ink-soft">—</span>
          ) : (
            <>
              <span className="font-display text-verdict leading-none font-semibold tracking-[-0.03em] tabular-nums">{value}</span>
              {unit ? <span className="text-meta text-ink-soft">{unit}</span> : null}
            </>
          )}
        </dd>
        <dt className="min-w-0 text-body break-words">{label}</dt>
        {value === null && hint ? <dd className="m-0 col-span-2 mt-1 text-meta text-ink-soft">{hint}</dd> : null}
      </dl>
    </li>
  );
}

export function SubjectStatsBlock({ stats }: { stats: ViewSubject }) {
  const { syllabus, bank, retention } = stats;
  const ready = bank?.reduce((n, t) => n + t.ready, 0) ?? 0;
  const practiced = bank?.reduce((n, t) => n + t.practiced, 0) ?? 0;
  const mastered = bank?.reduce((n, t) => n + t.mastered, 0) ?? 0;
  return (
    <div
      data-subject-stats
      aria-label="Thống kê môn"
      role="group"
      className="min-w-0 rounded-tile bg-sheet px-6 py-3 shadow-sheet"
    >
      <h2 className="sr-only">Thống kê môn này</h2>
      <ul className="m-0 flex list-none flex-col p-0">
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
      </ul>
    </div>
  );
}
