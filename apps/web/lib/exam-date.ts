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
