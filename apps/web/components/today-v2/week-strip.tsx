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
  return (
    <section
      aria-labelledby="today-week"
      className={cn("min-w-0 rounded-tile bg-sheet p-6 shadow-sheet min-[901px]:p-8", className)}
    >
      <h2 id="today-week" className="m-0 font-display text-lead">
        Tuần này bạn đã học
      </h2>
      <ol className="m-0 mt-4 grid list-none grid-cols-7 gap-2 p-0">
        {cells.map((cell, index) => {
          const on = cell.count > 0;
          const isToday = cell.day === today;
          return (
            <li
              key={cell.day}
              aria-current={isToday ? "date" : undefined}
              className={cn(
                "flex min-w-0 flex-col items-center gap-1 rounded-slip px-1 py-3 text-meta",
                on ? "bg-hl text-ink" : "bg-rose-100 text-ink-soft",
                isToday && "outline-2 outline-offset-2 outline-hong",
              )}
            >
              <span>{NAMES[index]}</span>
              <b className="font-display text-lead tabular-nums">{cell.count}</b>
              <span className="sr-only">{on ? "phần đã học" : "nghỉ"}</span>
            </li>
          );
        })}
      </ol>
      <p className="m-0 mt-3 text-small text-ink-soft">Mỗi ô là số phần đã học trong ngày. Nghỉ một hôm cũng không sao.</p>
    </section>
  );
}
