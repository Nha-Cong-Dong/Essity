"use client";

import { useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet } from "@/components/ui/sheet";
import { PARTIAL_NOTE } from "@/lib/fixtures/session-study";
import { type Draft, savableCount } from "@/lib/session-study/drafts";

import { DraftCard } from "./session-draft-card";
import type { Act } from "./use-live-session";
import { Notice } from "./session-parts";

// T7.12a (US-02 AC4-AC8; DESIGN.md §6.7 vùng 4; design decisions C9, C12, C16, C18): the scope that
// was read, the draft cards, and the one primary button: "Đúng rồi, lưu" saves every card shown in
// one go. It sits at the end of the list, in the flow, not stuck to the screen: stuck at 320 px it
// would cover the cards and invite a reflex tap (the scope block exists to slow that down).

export type ScopeRow = { id: string; doc: string; from: number; to: number };

function PageThumb({ page }: { page: number }) {
  return (
    <div className="flex flex-col items-center gap-1">
      <div
        aria-hidden="true"
        className="h-20 w-16 rounded-slip border border-line bg-sheet bg-[linear-gradient(transparent_9px,var(--line)_9px,var(--line)_10px)] bg-size-[100%_10px]"
      />
      <span className="text-meta text-ink-soft">tr. {page}</span>
    </div>
  );
}

function ScopeBlock({ rows }: { rows: ScopeRow[] }) {
  const id = useId();
  const [editing, setEditing] = useState(false);
  return (
    <Sheet variant="sunken" className="flex flex-col gap-4">
      <h3 className="m-0 text-body font-semibold">Phạm vi đã học</h3>
      {rows.map((row) => (
        <div key={row.id} className="flex flex-wrap items-center gap-4">
          <div className="flex gap-3">
            <PageThumb page={row.from} />
            <PageThumb page={row.to} />
          </div>
          <p className="m-0 min-w-0 flex-1 basis-40 text-body wrap-anywhere">
            {row.doc}, tr. {row.from}–{row.to}
          </p>
        </div>
      ))}
      {editing ? (
        <form
          method="post"
          className="flex flex-wrap items-end gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            setEditing(false);
          }}
        >
          <div className="flex flex-col gap-1">
            <label className="text-meta text-ink-soft" htmlFor={`${id}-from`}>
              Từ trang
            </label>
            <Input id={`${id}-from`} inputMode="numeric" defaultValue={rows[0]?.from} className="w-28" />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-meta text-ink-soft" htmlFor={`${id}-to`}>
              Đến trang
            </label>
            <Input id={`${id}-to`} inputMode="numeric" defaultValue={rows[0]?.to} className="w-28" />
          </div>
          <Button type="submit" variant="secondary">
            Áp dụng
          </Button>
          <Button type="button" variant="quiet" onClick={() => setEditing(false)}>
            Hủy
          </Button>
        </form>
      ) : (
        <Button type="button" variant="quiet" className="self-start" aria-expanded={false} onClick={() => setEditing(true)}>
          Chỉnh phạm vi
        </Button>
      )}
    </Sheet>
  );
}

export function ReviewArea({
  drafts,
  dispatch,
  sections,
  scope,
  partialNote,
  saveError,
  saving,
  newId,
  onSave,
  onRetryRead,
  onReload,
  lateCount,
  say,
}: {
  drafts: Draft[];
  dispatch: Act;
  /** Outline sections a card can be filed under; none = the picker is not shown (T7.12). */
  sections?: string[];
  scope: ScopeRow[];
  partialNote: boolean;
  saveError: boolean;
  saving: boolean;
  newId: () => string;
  onSave: () => void;
  onRetryRead: () => void;
  onReload: (id: string) => void;
  /** AI cards that arrived while the user was already here (appended at the end). */
  lateCount: number;
  say: (text: string) => void;
}) {
  const [mergeFrom, setMergeFrom] = useState<string | null>(null);
  const [justAdded, setJustAdded] = useState<string | null>(null);
  const count = savableCount(drafts);
  const mergeTitle = drafts.find((d) => d.id === mergeFrom)?.title ?? "";
  const hadRetired = drafts.some((d) => d.status === "retired");
  const scopeText = scope.length > 1 ? `${scope.length} tài liệu` : scope[0] ? `${scope[0].doc} tr. ${scope[0].from}–${scope[0].to}` : null;

  function add() {
    const id = newId();
    dispatch({ type: "add", id });
    setJustAdded(id);
  }

  return (
    <div className="flex flex-col gap-6">
      {partialNote && (
        <Notice role="status">
          <p className="m-0">{PARTIAL_NOTE}</p>
          <Button type="button" variant="secondary" onClick={onRetryRead}>
            Thử lại
          </Button>
        </Notice>
      )}
      {lateCount > 0 && <p className="m-0 text-meta text-ink-soft">Có {lateCount} thẻ nháp mới ở cuối danh sách.</p>}
      {scope.length > 0 && <ScopeBlock rows={scope} />}
      {drafts.length >= 6 && (
        <a href="#session-save" className="self-start text-body underline decoration-line-strong underline-offset-4">
          Xuống nút lưu
        </a>
      )}

      {mergeFrom !== null && (
        <div role="status" className="flex flex-wrap items-center gap-3 rounded-control bg-sunken px-4 py-2">
          <span className="min-w-0 flex-1 basis-48 text-body wrap-anywhere">Chọn thẻ để gộp với “{mergeTitle}”</span>
          <Button type="button" variant="quiet" onClick={() => setMergeFrom(null)}>
            Hủy
          </Button>
        </div>
      )}

      {drafts.length === 0 ? (
        <p className="m-0 text-body text-ink-soft">Chưa tách được thẻ nào từ bài nộp này.</p>
      ) : (
        <ol className="m-0 flex list-none flex-col p-0" aria-label="Thẻ nháp">
          {drafts.map((draft) => (
            <DraftCard
              key={draft.key ?? draft.id}
              draft={draft}
              dispatch={dispatch}
              mergeFrom={mergeFrom}
              onMergeStart={setMergeFrom}
              onMergeInto={async (targetId) => {
                if (mergeFrom) {
                  const done = await dispatch({ type: "merge", sourceId: mergeFrom, targetId });
                  if (done !== false) say("Đã gộp hai thẻ");
                }
                setMergeFrom(null);
              }}
              sections={sections}
              newId={newId}
              onReload={onReload}
              startEditing={draft.id === justAdded}
              say={say}
            />
          ))}
        </ol>
      )}

      <div id="session-save" className="flex flex-col gap-4 border-t border-line pt-6">
        {saveError && (
          <Notice role="alert">
            <p className="m-0">Chưa lưu được. Các thẻ nháp vẫn còn nguyên.</p>
            <Button type="button" variant="secondary" autoFocus onClick={onSave}>
              Thử lại
            </Button>
          </Notice>
        )}
        <p className="m-0 text-meta text-ink-soft">
          {count > 0 ? (
            <>
              Sẽ lưu {count} thẻ{scopeText ? ` · ${scopeText}` : ""}.{hadRetired ? " Không tính thẻ đã bỏ." : ""}
            </>
          ) : (
            <span id="session-save-why">Thêm ít nhất một thẻ để lưu.</span>
          )}
        </p>
        <div className="flex flex-col-reverse gap-3 min-[481px]:flex-row min-[481px]:items-center min-[481px]:justify-between">
          <Button type="button" variant="secondary" className="max-[480px]:w-full" onClick={add}>
            Thêm thẻ
          </Button>
          <Button
            type="button"
            className="max-[480px]:w-full aria-disabled:bg-sunken aria-disabled:text-ink-soft aria-disabled:shadow-none"
            pending={saving}
            aria-disabled={count === 0 || undefined}
            aria-describedby={count === 0 ? "session-save-why" : undefined}
            onClick={() => {
              if (count > 0) onSave();
            }}
          >
            Đúng rồi, lưu
          </Button>
        </div>
      </div>
    </div>
  );
}
