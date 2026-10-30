"use client";

import { type Dispatch, useId, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { Draft, DraftAction } from "@/lib/session-study/drafts";

import { Notice } from "./session-parts";

// T7.12a (US-02 AC5-AC8, US-02b; DESIGN.md §6.7 vùng 4; design decisions C1, C9-C11, C15, C18):
// one draft card, straight on the page and told apart by a rule above it. Tap the text to edit in
// place; Xong, leaving the field, Ctrl+Enter and Esc all keep what was typed (a draft, saved on the
// way). Discarding is one tap with Hoàn tác; merging and splitting ask once more and can be cancelled.

export const SECTIONS = ["3.1", "3.2", "3.3", "3.4"];
const NO_SECTION = "";
const ANCHORS_SHOWN = 2;

const ruled =
  "block field-sizing-content min-h-16 w-full resize-none rounded-none border-0 bg-transparent bg-[linear-gradient(transparent_31px,var(--line)_31px,var(--line)_32px)] bg-size-[100%_32px] [background-attachment:local] p-0 text-answer text-hong outline-none focus-visible:rounded-control focus-visible:outline-2 focus-visible:outline-offset-8 focus-visible:outline-focus";

const SOURCE_NOTE = { notes: "Chỉ thấy trong vở", document: "Chỉ thấy trong giáo trình" } as const;

export type DraftCardProps = {
  draft: Draft;
  dispatch: Dispatch<DraftAction>;
  /** Id of the card being merged into another, or null. */
  mergeFrom: string | null;
  onMergeStart: (id: string) => void;
  onMergeInto: (id: string) => void;
  newId: () => string;
  onReload: (id: string) => void;
  /** Starts a card straight in edit mode (the one just added). */
  startEditing?: boolean;
  say: (text: string) => void;
};

export function DraftCard(props: DraftCardProps) {
  const { draft, dispatch, mergeFrom, onMergeStart, onMergeInto, newId, onReload, say } = props;
  const id = useId();
  const [editing, setEditing] = useState(props.startEditing ?? false);
  const [mode, setMode] = useState<"idle" | "split" | "more">("idle");
  const [moreAnchors, setMoreAnchors] = useState(false);
  const [saved, setSaved] = useState(false);
  const [parts, setParts] = useState<[string, string]>(["", ""]);

  const label = draft.title.trim() || "thẻ mới";

  if (draft.status === "retired") {
    return (
      <li id={`session-card-${draft.id}`} className="flex flex-wrap items-center gap-3 rounded-control bg-sunken px-4 py-2">
        <span className="min-w-0 flex-1 text-meta text-ink-soft wrap-anywhere">Đã bỏ thẻ “{label}”.</span>
        <Button
          type="button"
          variant="quiet"
          autoFocus
          onClick={() => {
            dispatch({ type: "undo", id: draft.id });
            say(`Đã khôi phục thẻ ${label}`);
          }}
        >
          Hoàn tác
        </Button>
      </li>
    );
  }

  function finishEdit() {
    setEditing(false);
    setSaved(true);
  }

  function openSplit() {
    const words = draft.summary.split(/(?<=[.;])\s+/);
    const half = Math.max(1, Math.ceil(words.length / 2));
    setParts([words.slice(0, half).join(" "), words.slice(half).join(" ")]);
    setMode("split");
  }

  const merging = mergeFrom !== null;
  const anchors = moreAnchors ? draft.anchors : draft.anchors.slice(0, ANCHORS_SHOWN);

  return (
    <li id={`session-card-${draft.id}`} className="flex flex-col gap-3 border-t border-line py-6 first:border-t-0 first:pt-0">
      <div className="flex flex-wrap items-center gap-2">
        <label className="sr-only" htmlFor={`${id}-section`}>
          Mục đề cương của thẻ {label}
        </label>
        <select
          id={`${id}-section`}
          value={draft.section ?? NO_SECTION}
          onChange={(event) => dispatch({ type: "edit", id: draft.id, patch: { section: event.target.value || null } })}
          className="h-10 max-w-full rounded-full bg-rose-100 px-4 text-meta text-ink outline-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
        >
          {SECTIONS.map((section) => (
            <option key={section} value={section}>
              Mục {section}
            </option>
          ))}
          <option value={NO_SECTION}>Chưa gắn mục</option>
        </select>
        {draft.source !== "both" && <span className="text-meta text-ink-soft">{SOURCE_NOTE[draft.source]}</span>}
      </div>

      {editing ? (
        <div
          className="flex flex-col gap-3"
          onKeyDown={(event) => {
            if (event.key === "Escape" || (event.key === "Enter" && (event.ctrlKey || event.metaKey))) {
              event.preventDefault();
              finishEdit();
            }
          }}
          onBlur={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) finishEdit();
          }}
        >
          <label className="sr-only" htmlFor={`${id}-title`}>
            Tên thẻ
          </label>
          <Input
            id={`${id}-title`}
            autoFocus={draft.title === ""}
            value={draft.title}
            onChange={(event) => dispatch({ type: "edit", id: draft.id, patch: { title: event.target.value } })}
          />
          <label className="sr-only" htmlFor={`${id}-summary`}>
            Nội dung thẻ {label}
          </label>
          <textarea
            id={`${id}-summary`}
            autoFocus={draft.title !== ""}
            value={draft.summary}
            onChange={(event) => dispatch({ type: "edit", id: draft.id, patch: { summary: event.target.value } })}
            className={ruled}
          />
          <Button type="button" variant="quiet" className="self-start" onClick={finishEdit}>
            Xong
          </Button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => {
            setEditing(true);
            setSaved(false);
          }}
          aria-label={`Sửa thẻ ${label}`}
          className="flex w-full flex-col gap-1 rounded-control text-left"
        >
          <span className="text-read font-semibold wrap-anywhere">{draft.title || "Thẻ chưa có tên"}</span>
          <span className="text-body whitespace-pre-line wrap-anywhere">{draft.summary}</span>
        </button>
      )}
      {saved && !editing && (
        <p className="m-0 text-meta text-ink-soft" role="status">
          Đã lưu nháp
        </p>
      )}

      {draft.conflict && (
        <Notice role="alert">
          <p className="m-0">Thẻ này đã đổi ở nơi khác.</p>
          <div className="flex flex-col gap-1">
            <span className="text-meta text-ink-soft">Chữ của bạn</span>
            <p className="m-0 whitespace-pre-line">{draft.conflict.mine}</p>
          </div>
          <Button type="button" variant="secondary" onClick={() => onReload(draft.id)}>
            Tải lại thẻ
          </Button>
        </Notice>
      )}

      {anchors.length > 0 && (
        <ul className="m-0 flex list-none flex-col gap-3 p-0" aria-label="Nguồn của thẻ">
          {anchors.map((anchor) => (
            <li key={anchor.id}>
              <figure className="m-0">
                <blockquote className="m-0 border-l border-line-strong pl-3.5 text-body leading-[1.75] wrap-anywhere">
                  <mark className="[background:linear-gradient(var(--hl-band),var(--hl-band))_0_100%/100%_38%_no-repeat] px-px text-ink [box-decoration-break:clone]">
                    {anchor.quote}
                  </mark>
                </blockquote>
                <figcaption className="mt-1 pl-3.75 text-meta text-ink-soft wrap-anywhere">{anchor.label}</figcaption>
              </figure>
            </li>
          ))}
        </ul>
      )}
      {draft.anchors.length > ANCHORS_SHOWN && (
        <Button
          type="button"
          variant="quiet"
          className="self-start"
          aria-expanded={moreAnchors}
          onClick={() => setMoreAnchors((value) => !value)}
        >
          {moreAnchors ? "Thu gọn nguồn" : `Xem thêm ${draft.anchors.length - ANCHORS_SHOWN} nguồn`}
        </Button>
      )}

      {merging && mergeFrom !== draft.id && (
        <Button type="button" variant="secondary" className="self-start" onClick={() => onMergeInto(draft.id)}>
          Gộp vào đây
        </Button>
      )}

      {mode === "split" && (
        <div className="flex flex-col gap-4 rounded-control bg-sunken p-4">
          {[0, 1].map((n) => (
            <div key={n} className="flex flex-col gap-1">
              <label htmlFor={`${id}-part-${n}`} className="text-meta text-ink-soft">
                Thẻ {n + 1} sau khi tách
              </label>
              <textarea
                id={`${id}-part-${n}`}
                value={parts[n]}
                onChange={(event) => setParts((p) => (n === 0 ? [event.target.value, p[1]] : [p[0], event.target.value]))}
                className={ruled}
              />
            </div>
          ))}
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="secondary"
              disabled={parts[0].trim() === "" || parts[1].trim() === ""}
              onClick={() => {
                dispatch({
                  type: "split",
                  id: draft.id,
                  parts: [
                    { id: draft.id, title: draft.title, summary: parts[0] },
                    { id: newId(), title: `${draft.title} (tiếp)`, summary: parts[1] },
                  ],
                });
                say("Đã tách thành hai thẻ");
              }}
            >
              Tách thẻ
            </Button>
            <Button type="button" variant="quiet" onClick={() => setMode("idle")}>
              Hủy
            </Button>
          </div>
        </div>
      )}

      {mode === "more" && (
        <div className="flex flex-col gap-3 rounded-control bg-sunken p-4">
          <p className="m-0 text-body">Thêm ý từ tài liệu nào? Gõ @ rồi chọn trong bài nộp ở vòng sau.</p>
          <Button type="button" variant="quiet" className="self-start" onClick={() => setMode("idle")}>
            Đóng
          </Button>
        </div>
      )}

      {!merging && mode === "idle" && (
        <div className="flex flex-wrap gap-x-1 gap-y-0">
          <Button
            type="button"
            variant="quiet"
            onClick={() => {
              dispatch({ type: "discard", id: draft.id });
              say(`Đã bỏ thẻ ${label}`);
            }}
          >
            Bỏ thẻ
          </Button>
          <Button type="button" variant="quiet" onClick={() => onMergeStart(draft.id)}>
            Gộp
          </Button>
          <Button type="button" variant="quiet" onClick={openSplit}>
            Tách
          </Button>
          <Button type="button" variant="quiet" onClick={() => setMode("more")}>
            Thêm ý từ @…
          </Button>
        </div>
      )}
    </li>
  );
}
