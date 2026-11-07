"use client";

import { FileText, Image as ImageIcon, Paperclip } from "lucide-react";
import { useId, useRef } from "react";

import { Button } from "@/components/ui/button";
import type { FileRow } from "@/lib/fixtures/session-study";

import { MidTruncate, Notice } from "./session-parts";

// T7.12a (US-02 AC1, AC13; DESIGN.md §6.7 vùng 2; design decisions C7, C14): notebook photos and
// files. A real file input behind a "Chọn file" button (drag and drop is only a bonus), one row
// per file with a state written in words, never only in colour. A bad file never blocks the rest.

const STATE_TEXT: Record<Exclude<FileRow["state"], "uploading">, string> = {
  done: "Đã tải",
  "bad-type": "Định dạng này chưa dùng được. Dùng JPG, PNG, PDF, DOCX, PPTX hoặc TXT.",
  "too-big": "File này lớn quá. Chia nhỏ rồi tải lại.",
  "net-error": "Chưa tải được, mạng đang chập chờn.",
};

const ACCEPT = "image/*,.pdf,.docx,.pptx,.txt,.md";

export function FileDrop({
  rows,
  onAdd,
  onRemove,
  onRetry,
  tooManyPages,
  chips,
}: {
  /** C4D (mockup session.html): files are chips and the picker is the "Đính kèm" button of the composer row. */
  chips?: boolean;
  rows: FileRow[];
  onAdd: (files: File[]) => void;
  onRemove: (id: string) => void;
  onRetry: (id: string) => void;
  /** Pages over the limit of one round (DESIGN §6.7): the first N are read. */
  tooManyPages?: { total: number; read: number } | null;
}) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const chipRows = chips ? rows.filter((row) => row.state === "done") : [];
  const listRows = chips ? rows.filter((row) => row.state !== "done") : rows;
  return (
    <div className="flex flex-col gap-3">
      <div
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          onAdd(Array.from(event.dataTransfer.files));
        }}
        className={
          chips
            ? "contents"
            : "flex min-h-28 flex-col items-center justify-center gap-2 rounded-control border-[1.5px] border-dashed border-line-strong bg-sunken p-4 text-center"
        }
      >
        <input
          ref={input}
          id={chips ? "session-attach-input" : `${id}-input`}
          type="file"
          multiple
          accept={ACCEPT}
          className="sr-only"
          tabIndex={-1}
          aria-label="Chọn file bài nộp"
          onChange={(event) => {
            onAdd(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
        {!chips && (
          <>
            <Button type="button" variant="secondary" onClick={() => input.current?.click()}>
              Chọn file
            </Button>
            <p className="m-0 text-meta text-ink-soft">Ảnh vở, PDF, DOCX hoặc PPTX. Có thể thả file vào đây.</p>
          </>
        )}
      </div>
      {chipRows.length > 0 && (
        <ul data-testid="attach-chips" className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label="File đã chọn">
          {chipRows.map((row) => (
            <li key={row.id} className="inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-full bg-sunken pl-3.5 pr-1 text-meta font-medium text-ink">
              <Paperclip size={16} aria-hidden="true" className="shrink-0" />
              <span className="min-w-0">
                <MidTruncate text={row.name} />
              </span>
              <span className="sr-only">{STATE_TEXT.done}</span>
              <button
                type="button"
                aria-label={`Gỡ ${row.name}`}
                onClick={() => onRemove(row.id)}
                className="grid size-8 shrink-0 place-items-center rounded-full text-ink-soft hover:bg-line"
              >
                <span aria-hidden="true">×</span>
              </button>
            </li>
          ))}
        </ul>
      )}
      {tooManyPages && (
        <Notice role="status">
          <p className="m-0">
            Bài nộp có {tooManyPages.total} trang ảnh. App đọc {tooManyPages.read} trang đầu; phần còn lại nộp ở vòng sau.
          </p>
        </Notice>
      )}
      {listRows.length > 0 && (
        <ul className="m-0 flex list-none flex-col p-0" aria-live="polite" aria-label="File đã chọn">
          {listRows.map((row) => (
            <li key={row.id} className="flex min-h-14 items-center gap-3 border-t border-line py-2 first:border-t-0">
              <span className="grid size-10 shrink-0 place-items-center rounded-control bg-sunken text-ink-soft" aria-hidden="true">
                {row.kind === "image" ? <ImageIcon size={18} /> : <FileText size={18} />}
              </span>
              <div className="flex min-w-0 flex-1 flex-col">
                <span className="text-body">
                  <MidTruncate text={row.name} />
                </span>
                {row.state === "uploading" ? (
                  <span className="flex items-center gap-2 text-meta text-ink-soft">
                    Đang tải {row.percent ?? 0}%
                    <span aria-hidden="true" className="h-[3px] w-24 overflow-hidden rounded-full bg-line">
                      <span className="block h-[3px] rounded-full bg-hong" style={{ width: `${row.percent ?? 0}%` }} />
                    </span>
                  </span>
                ) : (
                  <span className={`text-meta ${row.state === "done" ? "text-ink-soft" : "text-partial"}`}>
                    {STATE_TEXT[row.state]}
                  </span>
                )}
              </div>
              {row.state === "net-error" && (
                <Button type="button" variant="quiet" onClick={() => onRetry(row.id)} aria-label={`Thử lại ${row.name}`}>
                  Thử lại
                </Button>
              )}
              <Button type="button" variant="quiet" onClick={() => onRemove(row.id)} aria-label={`Gỡ ${row.name}`}>
                Gỡ
              </Button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
