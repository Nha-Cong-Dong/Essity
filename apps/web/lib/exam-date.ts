// T1.20, plan K10: the exam date is typed day/month/year (Vietnamese order, whatever the
// browser's locale) and sent as ISO. Arithmetic only: new Date("31/02/2027") would roll it into
// March, and new Date("2026-12-15") is UTC midnight, a day early west of Greenwich.

export type DateError = "date_format";

// ASCII digits; one separator, the same twice; a four-digit year.
const TYPED = /^(\d{1,2})([/.-])(\d{1,2})\2(\d{4})$/;
const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;

function daysIn(month: number, year: number): number {
  if (month === 2) return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0 ? 29 : 28;
  return [4, 6, 9, 11].includes(month) ? 30 : 31;
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "15/12/2026", "15-12-2026" or "15.12.2026" → "2026-12-15"; a date the calendar lacks is refused. */
export function parseExamDate(text: string): { value: string } | { error: DateError } {
  const match = TYPED.exec(text.trim());
  if (!match) return { error: "date_format" };
  const [day, month, year] = [Number(match[1]), Number(match[3]), Number(match[4])];
  if (month < 1 || month > 12 || day < 1 || day > daysIn(month, year)) return { error: "date_format" };
  return { value: `${year}-${pad(month)}-${pad(day)}` };
}

/** "2026-12-15" → "15/12/2026". */
export function formatExamDate(iso: string): string {
  const match = ISO.exec(iso);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : iso;
}

/** core-api's days_until_exam (plan K3) in words. */
export function daysLeftText(days: number): string {
  if (days > 0) return `còn ${days} ngày`;
  return days === 0 ? "thi hôm nay" : "đã thi";
}

// Risk register R24, plan D11: the example in the date field and its message. It must be a date
// core-api accepts, so it is computed from the user's learning day, not the server's clock.

const parts = (now: Date, timeZone: string) =>
  Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(now)
      .map(({ type, value }) => [type, value]),
  );

/** core_api.domain.learning_day in TypeScript: before dayStartHour, it is still yesterday. */
export function learningDay(now: Date, timeZone: string, dayStartHour: number): string {
  const local = parts(now, timeZone);
  const day = new Date(Date.UTC(Number(local.year), Number(local.month) - 1, Number(local.day)));
  if (Number(local.hour) < dayStartHour) day.setUTCDate(day.getUTCDate() - 1);
  return day.toISOString().slice(0, 10);
}

/** 15/12 of this year while it is still ahead (an exam today is refused), else of next year. */
export function examExample(today: string): string {
  const year = Number(today.slice(0, 4));
  return today < `${year}-12-15` ? `15/12/${year}` : `15/12/${year + 1}`;
}

/** The example for a user; a zone Intl does not know gives next year's, which is always accepted. */
export function exampleFor(now: Date, timeZone: string, dayStartHour: number): string {
  try {
    return examExample(learningDay(now, timeZone, dayStartHour));
  } catch {
    return `15/12/${now.getUTCFullYear() + 1}`;
  }
}
