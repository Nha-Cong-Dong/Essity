import { Sheet } from "@/components/ui/sheet";
import { CoverageBar } from "@/components/stats/stat-tile";
import type { ViewSubject } from "@/lib/stats-view";

// Hackathon D7: this subject's own numbers (moved here from the stats screen).
export function SubjectStatsBlock({ stats }: { stats: ViewSubject }) {
  const { syllabus, bank, retention } = stats;
  const percent = syllabus.leaves > 0 ? Math.round((syllabus.studied / syllabus.leaves) * 100) : 0;
  const ready = bank?.reduce((n, t) => n + t.ready, 0) ?? 0;
  const practiced = bank?.reduce((n, t) => n + t.practiced, 0) ?? 0;
  const mastered = bank?.reduce((n, t) => n + t.mastered, 0) ?? 0;
  return (
    <Sheet variant="tile" aria-label="Thống kê môn" data-subject-stats className="flex flex-col gap-4">
      <h2 className="m-0 font-display text-lead">Thống kê môn này</h2>
      <dl className="m-0 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div>
          <dt className="text-meta text-ink-soft">Đã học</dt>
          <dd className="m-0 font-display text-display">
            {syllabus.studied}/{syllabus.leaves} phần
          </dd>
        </div>
        <div>
          <dt className="text-meta text-ink-soft">Câu sẵn sàng</dt>
          <dd className="m-0 font-display text-display">{bank === null ? "chưa có" : ready}</dd>
        </div>
        <div>
          <dt className="text-meta text-ink-soft">Đã luyện / thành thạo</dt>
          <dd className="m-0 font-display text-display">{bank === null ? "–" : `${practiced} / ${mastered}`}</dd>
        </div>
        <div>
          <dt className="text-meta text-ink-soft">Nhớ tốt hôm nay</dt>
          <dd className="m-0 font-display text-display">{retention === null ? "chưa có thẻ" : `${Math.round(retention * 100)}%`}</dd>
        </div>
      </dl>
      <CoverageBar percent={percent} />
    </Sheet>
  );
}
