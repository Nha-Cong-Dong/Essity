// T2.15 (plan step 8, 🟡14): the answer kept on this device, so a dropped connection or a closed
// tab loses nothing typed. core-api's draft (T2.9) is the one other devices see; this copy only
// wins while it holds text core-api never got. Cleared when the answer is submitted and when the
// user signs out here (signing out elsewhere cannot reach it: risk register).

const PREFIX = "essity:draft:";

/** A draft not touched for a week is dropped: the session it belonged to is long over. */
export const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

export type LocalDraft = {
  text: string;
  dontRemember: boolean;
  /** Whether core-api has this text: then core-api's draft is at least as new. */
  synced: boolean;
  savedAt: number;
};

type Options = { storage?: Storage | null; now?: number };

function local(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage;
  } catch {
    return null; // blocked by the browser's settings
  }
}

export function readDraft(attemptId: string, { storage = local(), now = Date.now() }: Options = {}): LocalDraft | null {
  if (!storage) return null;
  try {
    const raw = storage.getItem(PREFIX + attemptId);
    if (raw === null) return null;
    const draft = JSON.parse(raw) as Partial<LocalDraft>;
    if (
      typeof draft.text !== "string" ||
      typeof draft.dontRemember !== "boolean" ||
      typeof draft.synced !== "boolean" ||
      typeof draft.savedAt !== "number"
    ) {
      return null;
    }
    if (now - draft.savedAt > DRAFT_MAX_AGE_MS) {
      storage.removeItem(PREFIX + attemptId);
      return null;
    }
    return { text: draft.text, dontRemember: draft.dontRemember, synced: draft.synced, savedAt: draft.savedAt };
  } catch {
    return null;
  }
}

export function writeDraft(
  attemptId: string,
  draft: Omit<LocalDraft, "savedAt">,
  { storage = local(), now = Date.now() }: Options = {},
): void {
  try {
    storage?.setItem(PREFIX + attemptId, JSON.stringify({ ...draft, savedAt: now }));
  } catch {
    // Full or blocked: the draft still goes to core-api.
  }
}

export function clearDraft(attemptId: string, { storage = local() }: Options = {}): void {
  try {
    storage?.removeItem(PREFIX + attemptId);
  } catch {
    // Nothing to clear.
  }
}

/** Every draft on this device, on signing out: the next person here must not see them. */
export function clearAllDrafts({ storage = local() }: Options = {}): void {
  if (!storage) return;
  try {
    const keys: string[] = [];
    for (let n = 0; n < storage.length; n += 1) {
      const key = storage.key(n);
      if (key?.startsWith(PREFIX)) keys.push(key);
    }
    for (const key of keys) storage.removeItem(key);
  } catch {
    // Nothing to clear.
  }
}

/** What the answer box starts with: this device's text if core-api never got it, else core-api's. */
export function pickDraft(
  draft: LocalDraft | null,
  server: { answer_text: string; dont_remember: boolean },
): { text: string; dontRemember: boolean } {
  if (draft && !draft.synced) return { text: draft.text, dontRemember: draft.dontRemember };
  return { text: server.answer_text, dontRemember: server.dont_remember };
}
