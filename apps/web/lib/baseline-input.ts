// T1.18, US-11 AC3: what the baseline screen accepts, checked before anything is sent. core-api
// checks again; this only spares a round trip and says what to type (DESIGN.md §6.2).

export type BaselineError = "gpa_range" | "gpa_decimals" | "days_range";
export type Parsed<Value> = { value: Value } | { error: BaselineError };

// ASCII digits only (JS `\d` never matches other scripts), one optional dot or comma.
const GPA = /^(\d+)(?:[.,](\d+))?$/;

/**
 * GPA on the 4-point scale, written with a dot or a comma, sent with a dot (plan B7). Never
 * rounded: 2.857 is refused rather than turned into 2.86, which would quietly change a baseline.
 */
export function parseGpa(text: string): Parsed<string> {
  const match = GPA.exec(text.trim());
  if (!match) return { error: "gpa_range" };
  const [, whole, decimals] = match;
  const value = decimals === undefined ? whole : `${whole}.${decimals}`;
  if (Number(value) > 4) return { error: "gpa_range" };
  if (decimals !== undefined && decimals.length > 2) return { error: "gpa_decimals" };
  return { value };
}

/** Days ready before last term's exams: a whole number from 0 to 365. */
export function parseDays(text: string): Parsed<number> {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return { error: "days_range" };
  const days = Number(trimmed);
  return days <= 365 ? { value: days } : { error: "days_range" };
}
