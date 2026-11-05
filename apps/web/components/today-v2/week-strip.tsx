import { cn } from "@/lib/utils";

// "Tuần này": seven cells Mon..Sun, the number of activities (cards saved + questions answered) each day. No streak,
// no counter of missed days: resting is fine (the pressure metrics are dropped, PRD US-11).

export type WeekCell = { day: string; count: number };

const NAMES = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

/** Monday of the week of an ISO date (YYYY-MM-DD), as ISO; pure calendar maths in UTC. */
function mondayOf(iso: string): number {
  const date = Date.parse(`${iso}T00:00:00Z`);
  const weekday = (new Date(date).getUTCDay() + 6) % 7;
  return date - weekday * 86_400_000;
}

const isoOf = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** The seven days of the week that holds `today`, from the stats grid (cells are per day). */
export function weekFor(today: string, counts: Map<string, number>): WeekCell[] {
  const start = mondayOf(today);
  return Array.from({ length: 7 }, (_, k) => {
    const day = isoOf(start + k * 86_400_000);
    return { day, count: counts.get(day) ?? 0 };
  });
}

/** Activity of a day = cards saved + practice questions answered (the same count the year heatmap uses). */
export function weekFromCells(
  cells: { day: string; cardsSaved: number; questionsAnswered: number; future?: boolean }[],
  today = new Date().toISOString().slice(0, 10),
): WeekCell[] {
  return weekFor(today, new Map(cells.map((cell) => [cell.day, cell.cardsSaved + cell.questionsAnswered])));
}

export function WeekStrip({ cells, today, className }: { cells: WeekCell[]; today: string; className?: string }) {
  const top = Math.max(1, ...cells.map((cell) => cell.count));
  const empty = cells.every((cell) => cell.count === 0);
  // DESIGN-V4 (mockups today.html): from 1024px this is the bottom half of the field poster (the review
  // is its top half); below 1024px it is a white sheet. `--now` (pink, with a ring) marks today, never teal.
  return (
    <section
      aria-labelledby="today-week"
      data-tier="week"
      className={cn(
        "flex min-w-0 flex-col rounded-tile bg-sheet p-6 text-ink shadow-sheet",
        "min-[1024px]:[border-top-left-radius:0] min-[1024px]:[border-top-right-radius:0] min-[1024px]:bg-field min-[1024px]:p-8 min-[1024px]:pt-4 min-[1024px]:text-on-plum min-[1024px]:shadow-none",
        className,
      )}
    >
      <h2 id="today-week" className="m-0 font-display text-tile">
        Tuần này
      </h2>
      {empty ? (
        <p className="m-0 mt-3 text-read text-ink-soft min-[1024px]:text-on-plum-soft" data-week-empty>
          Chưa có hoạt động nào trong tuần này.
        </p>
      ) : null}
      <ol hidden={empty} className="m-0 mt-4 grid min-h-36 flex-1 list-none grid-cols-7 items-end gap-2.5 p-0">
        {cells.map((cell, index) => {
          const on = cell.count > 0;
          const isToday = cell.day === today;
          return (
            <li
              key={cell.day}
              aria-current={isToday ? "date" : undefined}
              className="flex h-full min-w-0 flex-col items-center justify-end gap-1.5 text-meta text-ink-soft min-[1024px]:text-on-plum-soft"
            >
              <b className="font-display text-body text-ink tabular-nums min-[1024px]:text-on-plum">{cell.count}</b>
              <span
                aria-hidden="true"
                className={cn(
                  "w-full max-w-9.5 rounded-slip",
                  !on && "bg-line-strong min-[1024px]:bg-on-plum-soft/55",
                  on && !isToday && "bg-hong min-[1024px]:bg-on-plum-soft",
                  on &&
                    isToday &&
                    "bg-now shadow-[0_0_0_2px_var(--sheet),0_0_0_3.5px_var(--ink)] min-[1024px]:bg-now-on-field min-[1024px]:shadow-[0_0_0_2px_var(--field),0_0_0_3.5px_var(--on-plum)]",
                )}
                style={{ height: on ? `${Math.max(12, (cell.count / top) * 96)}px` : "2px" }}
              />
              <span className={cn("flex flex-col items-center gap-1", isToday && "font-semibold text-ink min-[1024px]:text-on-plum")}>
                {NAMES[index]}
                {isToday ? <span aria-hidden="true" className="block size-1.5 rounded-full bg-ink min-[1024px]:bg-on-plum" /> : null}
              </span>
              <span className="sr-only">{on ? "hoạt động" : "nghỉ"}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
