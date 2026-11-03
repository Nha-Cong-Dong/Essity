// F3: sessions whose cards are being made. Kept in this browser so the "ready" toast can come
// from any page; core-api holds the truth (the submission's status).
const KEY = "essity.pending-sessions";

export type PendingSession = { sessionId: string; subjectId: string; subject: string };

export function readPendingSessions(): PendingSession[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) ?? "[]") as unknown;
    return Array.isArray(raw) ? (raw as PendingSession[]).filter((p) => typeof p?.sessionId === "string") : [];
  } catch {
    return [];
  }
}

function write(list: PendingSession[]) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* storage can be blocked: the toast is a convenience */
  }
}

export function rememberPendingSession(item: PendingSession) {
  write([...readPendingSessions().filter((p) => p.sessionId !== item.sessionId), item]);
}

export function forgetPendingSession(sessionId: string) {
  write(readPendingSessions().filter((p) => p.sessionId !== sessionId));
}
