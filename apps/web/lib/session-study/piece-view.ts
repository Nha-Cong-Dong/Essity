// SESSION-V4-RESTORE: what a kept piece shows in the "Đã học trong buổi" timeline, derived from what
// core-api already returns (time + text). Nothing here is sent anywhere.

/** Local HH:MM of an ISO time, "" when it is not a time. */
export function hhmm(iso: string | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit", hour12: false });
}

const TITLE_MAX = 60;

/** The first clause of the note (up to the first full stop or line break), clamped. */
export function pieceTitle(text: string): string {
  const first = (text.trim().split(/\n|(?<=[.!?])\s/)[0] ?? "").replace(/[.!?]+$/, "").trim();
  return first.length > TITLE_MAX ? `${first.slice(0, TITLE_MAX).trimEnd()}…` : first;
}

/** Page ranges the learner named ("trang 20–25", "tr. 14"), as "tr.20–25" chips. */
export function pieceSources(text: string): string[] {
  const found: string[] = [];
  for (const m of text.matchAll(/\b(?:trang|tr)\.?\s*(\d{1,4})(?:\s*[–-]\s*(\d{1,4}))?/gi)) {
    found.push(`tr.${m[1]}${m[2] ? `–${m[2]}` : ""}`);
  }
  return found;
}
