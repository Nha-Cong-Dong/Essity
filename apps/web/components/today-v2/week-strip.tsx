import { cn } from "@/lib/utils";

// V21 "Tuần này bạn đã học": seven cells Mon..Sun, the number of sections learned each day. No streak,
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

export function weekFromCells(
  cells: { day: string; sections: string[]; future?: boolean }[],
  today = new Date().toISOString().slice(0, 10),
): WeekCell[] {
  return weekFor(today, new Map(cells.map((cell) => [cell.day, cell.sections.length])));
}

export function WeekStrip({ cells, today, className }: { cells: WeekCell[]; today: string; className?: string }) {
  const top = Math.max(1, ...cells.map((cell) => cell.count));
  return (
    <section aria-labelledby="today-week" className={cn("min-w-0", className)}>
      <h2 id="today-week" className="m-0 text-body font-semibold">
        Tuần này bạn đã học
      </h2>
      <ol className="m-0 mt-4 grid h-28 list-none grid-cols-7 items-end gap-3 p-0">
        {cells.map((cell, index) => {
          const on = cell.count > 0;
          const isToday = cell.day === today;
          return (
            <li
              key={cell.day}
              aria-current={isToday ? "date" : undefined}
              className="flex h-full min-w-0 flex-col items-center justify-end gap-1 text-meta text-ink-soft"
            >
              <b className="font-serif font-medium text-ink tabular-nums">{cell.count}</b>
              <span
                aria-hidden="true"
                className={cn("w-full max-w-9 rounded-slip", on ? "bg-hong" : "bg-line-strong", isToday && "outline-2 outline-offset-2 outline-ink")}
                style={{ height: on ? `${Math.max(12, (cell.count / top) * 56)}px` : "2px" }}
              />
              <span className={cn(isToday && "font-semibold text-ink")}>{NAMES[index]}</span>
              <span className="sr-only">{on ? "phần đã học" : "nghỉ"}</span>
            </li>
          );
        })}
      </ol>
      <p className="m-0 mt-3 text-meta text-ink-soft">Mỗi cột là số phần đã học trong ngày. Nghỉ một hôm cũng không sao.</p>
    </section>
  );
}
