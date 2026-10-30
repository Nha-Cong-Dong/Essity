import type { ReactNode } from "react";

import styles from "./stats.module.css";

// T9.5a (DESIGN §6.13, §7): a StatTile is a label, a number written out, a plain line under it,
// and a thin bar that only repeats the number (aria-hidden). It never shows a verdict, an arrow or
// a comparison. Without data there is no bar, only a neutral line.

/** CoverageBar: the thin bar. `percent` 0..100; decoration only. */
export function CoverageBar({ percent }: { percent: number }) {
  return (
    <div aria-hidden="true" className={styles.bar} data-coverage-bar>
      <div className={styles.fill} style={{ width: `${Math.min(Math.max(percent, 0), 100)}%` }} />
    </div>
  );
}

/** MiniNotebook: a 32x44 notebook with the pink spine, the subject's mark (decoration). */
export function MiniNotebook() {
  return (
    <span
      aria-hidden="true"
      className="relative block h-11 w-8 shrink-0 overflow-hidden rounded-control bg-rose-100 shadow-sheet"
    >
      <span className="absolute inset-y-0 left-0 w-1.5 bg-spine" />
    </span>
  );
}

export function StatTile({
  label,
  value,
  note,
  percent,
  children,
}: {
  label: string;
  value: ReactNode;
  note?: ReactNode;
  percent?: number | null;
  children?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1" data-stat-tile>
      <dl className="m-0 flex min-w-0 flex-col gap-1">
        <dt className="text-meta text-ink-soft">{label}</dt>
        <dd className="m-0 text-lead tabular-nums wrap-anywhere">
          {value}
        </dd>
        {note && (
          <dd className="m-0 text-meta text-ink-soft wrap-anywhere">
            {note}
          </dd>
        )}
      </dl>
      {percent != null && <CoverageBar percent={percent} />}
      {children}
    </div>
  );
}
