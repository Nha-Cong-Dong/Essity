// T9.5a (US-10, DESIGN §6.13): the Thống kê screen's grid and copy. The grid mirrors
// core_api/domain/stats.py (T9.4a): columns are weeks from the Monday of the first week, rows are
// weekdays (Monday 0), days after today stay empty. Dates are "YYYY-MM-DD" learning days, so
// there is no timezone work here. No streak, no week-over-week comparison anywhere (principle 4).

export type SubjectSpan = { id: string; createdOn: string; examOn: string | null };
export type ActivityEvent = {
  day: string;
  subjectId: string;
  sections: string[];
  cardsSaved: number;
  questionsAnswered: number;
};
export type GridCell = {
  day: string;
  column: number;
  row: number;
  level: 0 | 1 | 2 | 3 | 4;
  future: boolean;
  examDay: boolean;
  subjects: string[];
  sections: string[];
  cardsSaved: number;
  questionsAnswered: number;
};

// Cards saved + questions answered in a day -> level 1..4 at these lower bounds; 0 is empty.
export const LEVEL_FLOORS = [1, 4, 10, 20] as const;

export function levelFor(work: number): GridCell["level"] {
  return LEVEL_FLOORS.filter((floor) => work >= floor).length as GridCell["level"];
}

const DAY_MS = 86_400_000;
const toMs = (day: string) => Date.parse(`${day}T00:00:00Z`);
const toDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);
const weekday = (ms: number) => (new Date(ms).getUTCDay() + 6) % 7;

export function buildGrid(
  spans: SubjectSpan[],
  events: ActivityEvent[],
  today: string,
  subjectId?: string,
): GridCell[] {
  const chosen = spans.filter((s) => subjectId === undefined || s.id === subjectId);
  if (chosen.length === 0) return [];
  const ids = new Set(chosen.map((s) => s.id));
  const daily = new Map<string, ActivityEvent[]>();
  for (const event of events) {
    if (ids.has(event.subjectId)) daily.set(event.day, [...(daily.get(event.day) ?? []), event]);
  }
  const todayMs = toMs(today);
  const activityDays = [...daily.keys()].map(toMs);
  const exams = chosen.flatMap((s) => (s.examOn === null ? [] : [toMs(s.examOn)]));
  const start = Math.min(...chosen.map((s) => toMs(s.createdOn)), ...activityDays);
  const end = Math.max(todayMs, ...exams, start, ...activityDays);
  const firstMonday = start - weekday(start) * DAY_MS;
  const examDays = new Set(exams);
  const cells: GridCell[] = [];
  for (let ms = start; ms <= end; ms += DAY_MS) {
    const day = toDay(ms);
    const future = ms > todayMs;
    const rows = future ? [] : (daily.get(day) ?? []); // clock skew: a future day stays empty
    const cardsSaved = rows.reduce((n, e) => n + e.cardsSaved, 0);
    const questionsAnswered = rows.reduce((n, e) => n + e.questionsAnswered, 0);
    cells.push({
      day,
      column: Math.floor((ms - firstMonday) / DAY_MS / 7),
      row: weekday(ms),
      level: levelFor(cardsSaved + questionsAnswered),
      future,
      examDay: examDays.has(ms),
      subjects: [...new Set(rows.map((e) => e.subjectId))].sort(),
      sections: [...new Set(rows.flatMap((e) => e.sections))].sort(),
      cardsSaved,
      questionsAnswered,
    });
  }
  return cells;
}

/** "còn 60 ngày"; on the day "thi hôm nay"; after it "đã thi". Never a negative number. */
export function daysLeftText(days: number): string {
  if (days > 0) return `còn ${days} ngày`;
  return days === 0 ? "thi hôm nay" : "đã thi";
}

export function percentOf(part: number, whole: number): number | null {
  return whole === 0 ? null : Math.round((100 * part) / whole);
}

/** One label per month, on the first column whose first day is in that month ("Th10"). */
export function monthLabels(cells: GridCell[]): { column: number; label: string }[] {
  const labels: { column: number; label: string }[] = [];
  let last = "";
  let column = -1;
  for (const cell of cells) {
    if (cell.column === column) continue; // only a column's first day names its month
    column = cell.column;
    const month = cell.day.slice(5, 7);
    if (month === last) continue;
    last = month;
    labels.push({ column, label: `Th${Number(month)}` });
  }
  return labels;
}
