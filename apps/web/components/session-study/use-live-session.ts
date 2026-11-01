"use client";

import { useCallback, useEffect, useRef } from "react";

import type { SessionApi } from "@/lib/session-study/api";
import type { Draft, DraftAction } from "@/lib/session-study/drafts";

// T7.12 (US-02b AC6-AC9; ADR-0028): the draft cards of a session mirrored to core-api. The screen
// keeps its own list (the learner types into it); this sends what the learner did, one call after
// another (so a card added and then edited is never added twice), and tells the list what core-api
// answered: the card's real id and version, a 409 ("thẻ đã đổi ở nơi khác"), a refusal.
// Typing is saved a moment after the last key and when the learner leaves the card; "Lưu" waits
// for those first. Nothing is sent for a card that is not both titled and written.

/** An action on the list; a merge or split answers whether it took effect (the card closes then). */
export type Act = (action: DraftAction) => void | Promise<boolean>;

export type SaveResult = { kind: "ok" } | { kind: "empty" } | { kind: "conflict"; ids: string[] } | { kind: "error" };

const SAVE_DELAY_MS = 800;
export const isLocal = (id: string) => id.startsWith("new-");

export const COPY = {
  conflict: "Thẻ đã đổi ở nơi khác. Tải lại thẻ để xem bản mới.",
  draftNotSaved: "Chưa lưu được chữ vừa sửa. Mạng đang chập chờn, thử lại sau.",
  discardFailed: "Chưa bỏ được thẻ. Thử lại sau.",
  undoFailed: "Không khôi phục được thẻ này nữa.",
  needBoth: "Thẻ mới cần có tên và nội dung trước khi gộp hoặc tách.",
  mergeFailed: "Chưa gộp được hai thẻ. Thử lại sau.",
  splitFailed: "Chưa tách được thẻ. Thử lại sau.",
} as const;

export function useDraftSync(
  api: SessionApi | undefined,
  drafts: Draft[],
  dispatch: (action: DraftAction) => void,
  say: (text: string) => void,
) {
  const latest = useRef(drafts);
  // The id and version core-api holds, set the moment it answers (a render may come later).
  const real = useRef(new Map<string, string>());
  const versions = useRef(new Map<string, number>());
  const timers = useRef(new Map<string, number>());
  const queue = useRef<Promise<unknown>>(Promise.resolve());

  useEffect(() => {
    latest.current = drafts;
  }, [drafts]);
  useEffect(() => {
    const pending = timers.current;
    return () => pending.forEach((t) => window.clearTimeout(t));
  }, []);

  const serverId = (id: string) => real.current.get(id) ?? (isLocal(id) ? null : id);
  const versionOf = (id: string) => versions.current.get(serverId(id) ?? id) ?? latest.current.find((d) => d.id === id)?.version ?? 1;
  // A card added here is known by its local id until core-api answers, then by the real one.
  const current = (id: string) => latest.current.find((d) => d.id === id || d.id === real.current.get(id));
  // Cards dropped while their add was still in flight: the server copy is dropped when it lands.
  const dropped = useRef(new Set<string>());
  const remember = (card: Draft) => versions.current.set(card.id, card.version);

  function later<T>(task: () => Promise<T>): Promise<T> {
    const next = queue.current.then(task, task);
    queue.current = next.catch(() => undefined);
    return next;
  }

  async function writeThrough(id: string) {
    if (!api) return;
    const card = current(id);
    if (!card || card.status !== "draft") return;
    const title = card.title.trim();
    const content = card.summary.trim();
    if (title === "" || content === "") return;
    const known = serverId(id);
    if (known === null) {
      const added = await api.add(card.title, card.summary);
      if (added.ok) {
        real.current.set(id, added.data.id);
        remember(added.data);
        dispatch({ type: "synced", id, to: added.data.id, version: added.data.version });
        if (dropped.current.has(id)) {
          const gone = await api.discard(added.data.id);
          if (gone.ok) remember(gone.data);
        }
      } else say(COPY.draftNotSaved);
      return;
    }
    const sent = await api.edit(known, versionOf(id), { title: card.title, content: card.summary });
    if (sent.ok) {
      remember(sent.data);
      dispatch({ type: "synced", id, to: known, version: sent.data.version });
    } else if (sent.error === "unit_changed_elsewhere") {
      dispatch({ type: "conflict", id, mine: card.summary });
      say(COPY.conflict);
    } else say(COPY.draftNotSaved);
  }

  function schedule(id: string) {
    window.clearTimeout(timers.current.get(id));
    timers.current.set(
      id,
      window.setTimeout(() => {
        timers.current.delete(id);
        void later(() => writeThrough(id));
      }, SAVE_DELAY_MS),
    );
  }

  /** Sends every card still waiting for its pause, and waits for everything already sent. */
  async function flush() {
    for (const [id, timer] of [...timers.current]) {
      window.clearTimeout(timer);
      timers.current.delete(id);
      void later(() => writeThrough(id));
    }
    await later(async () => undefined);
  }

  async function merge(sourceId: string, targetId: string): Promise<boolean> {
    if (!api) return false;
    await flush();
    const ids = [serverId(targetId), serverId(sourceId)];
    if (ids[0] === null || ids[1] === null) {
      say(COPY.needBoth);
      return false;
    }
    const merged = await api.merge([ids[0], ids[1]]);
    if (!merged.ok) {
      say(merged.error === "unit_changed_elsewhere" ? COPY.conflict : COPY.mergeFailed);
      return false;
    }
    remember(merged.data);
    dispatch({ type: "replace", ids: [sourceId, targetId], drafts: [merged.data] });
    return true;
  }

  async function split(id: string, parts: { title: string; summary: string }[]): Promise<boolean> {
    if (!api) return false;
    await flush();
    const known = serverId(id);
    if (known === null) {
      say(COPY.needBoth);
      return false;
    }
    const made = await api.split(known, versionOf(id), parts.map((p) => ({ title: p.title, content: p.summary })));
    if (!made.ok) {
      if (made.error === "unit_changed_elsewhere") {
        dispatch({ type: "conflict", id, mine: current(id)?.summary ?? "" });
        say(COPY.conflict);
      } else say(COPY.splitFailed);
      return false;
    }
    made.data.forEach(remember);
    dispatch({ type: "replace", ids: [id], drafts: made.data });
    return true;
  }

  const act: Act = useCallback(
    (action) => {
      if (!api) {
        dispatch(action);
        return;
      }
      switch (action.type) {
        case "edit":
          dispatch(action);
          if (action.patch.title !== undefined || action.patch.summary !== undefined) schedule(action.id);
          return;
        case "discard": {
          dispatch(action);
          const id = serverId(action.id);
          if (id === null) {
            dropped.current.add(action.id);
            return;
          }
          void later(async () => {
            const done = await api.discard(id);
            if (done.ok) remember(done.data);
            else {
              dispatch({ type: "undo", id: action.id });
              say(COPY.discardFailed);
            }
          });
          return;
        }
        case "undo": {
          dispatch(action);
          dropped.current.delete(action.id);
          const id = serverId(action.id);
          if (id === null) return;
          void later(async () => {
            const done = await api.undo(id);
            if (done.ok) remember(done.data);
            else {
              dispatch({ type: "discard", id: action.id });
              say(COPY.undoFailed);
            }
          });
          return;
        }
        case "merge":
          return merge(action.sourceId, action.targetId);
        case "split":
          return split(action.id, action.parts);
        default:
          dispatch(action);
      }
    },
    // The helpers read refs only, so one closure per api is enough.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [api, dispatch, say],
  );

  async function reload(id: string) {
    const known = serverId(id);
    if (!api || known === null) return;
    const fresh = await api.get(known);
    if (!fresh.ok) {
      say(COPY.draftNotSaved);
      return;
    }
    remember(fresh.data);
    dispatch({ type: "reload", draft: { ...fresh.data, id } });
  }

  /** "Lưu": every card shown that core-api knows, each with the version this screen saw. */
  async function saveAll(): Promise<SaveResult> {
    if (!api) return { kind: "error" };
    await flush();
    const cards = latest.current
      .filter((d) => d.status === "draft" && serverId(d.id) !== null)
      .map((d) => ({ local: d.id, id: serverId(d.id) as string, version: versionOf(d.id) }));
    if (cards.length === 0) return { kind: "empty" };
    const saved = await api.save(cards.map(({ id, version }) => ({ id, version })));
    if (saved.ok) return { kind: "ok" };
    if (saved.error !== "unit_changed_elsewhere") return { kind: "error" };
    const stale: string[] = [];
    for (const card of cards) {
      const fresh = await api.get(card.id);
      if (fresh.ok && fresh.data.version !== card.version) {
        stale.push(card.local);
        dispatch({ type: "conflict", id: card.local, mine: current(card.local)?.summary ?? "" });
      }
    }
    return { kind: "conflict", ids: stale };
  }

  return { act, saveAll, reload };
}
