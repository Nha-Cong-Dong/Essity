"use client";

import { Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { logMessage } from "@/lib/log-session-copy";
import { checkNote, type NoteRef, type NoteState, uploadNote } from "@/lib/note-upload";

// T4.13b (US-02 AC13; screens-html log-session.html "drop" and "thumbs"): notebook photos and note
// files are chosen before the sentence is sent, and go straight to storage once the draft session
// exists (core-api signs a URL per file for that session). Files go one after the other, so a long
// list does not eat the hourly limit at once. Lưu waits for them: `busy`.

type Row = { key: number; file: File; state: NoteState };

const STATUS = "text-small font-semibold text-ink-soft";
const WORKING = new Set<NoteState["kind"]>(["queued", "hashing", "uploading"]);

export function useNotes() {
  const [rows, setRows] = useState<Row[]>([]);
  const next = useRef(0);
  const session = useRef<string | null>(null);
  const chain = useRef(Promise.resolve());
  // `begin` runs from a call that started before the latest render: it reads the latest rows.
  const latest = useRef(rows);
  useEffect(() => {
    latest.current = rows;
  });
  const [hasSession, setHasSession] = useState(false);

  function update(key: number, state: NoteState) {
    setRows((all) => all.map((row) => (row.key === key ? { ...row, state } : row)));
  }

  function start(sessionId: string, row: Row) {
    chain.current = chain.current
      .then(() => uploadNote(sessionId, row.file, (state) => update(row.key, state)))
      .catch(() => update(row.key, { kind: "failed", code: "upload_failed" }));
  }

  function add(files: FileList | File[]) {
    const added: Row[] = Array.from(files).map((file) => {
      const problem = checkNote(file);
      const state: NoteState = problem ? { kind: "failed", code: `note_${problem}` } : { kind: "queued" };
      return { key: next.current++, file, state };
    });
    setRows((all) => [...all, ...added]);
    const sessionId = session.current;
    if (sessionId) for (const row of added) if (row.state.kind === "queued") start(sessionId, row);
  }

  /** The draft session exists: send what waits. A new session (the sentence was corrected and
   * sent again) takes the files again, the ones sent to the old draft included. */
  function begin(sessionId: string) {
    const again = session.current !== null && session.current !== sessionId;
    session.current = sessionId;
    setHasSession(true);
    const queued = latest.current.map((row) =>
      row.state.kind === "failed" || (!again && row.state.kind === "ready")
        ? row
        : { ...row, state: { kind: "queued" } as NoteState },
    );
    setRows(queued);
    for (const row of queued) if (row.state.kind === "queued") start(sessionId, row);
  }

  function remove(key: number) {
    setRows((all) => all.filter((row) => row.key !== key));
  }

  const notes: NoteRef[] = [];
  for (const { state } of rows) {
    if (state.kind === "ready" && !notes.some((note) => note.sha256 === state.note.sha256)) {
      notes.push(state.note);
    }
  }
  const busy = hasSession && rows.some((row) => WORKING.has(row.state.kind));
  return { rows, add, begin, remove, notes, busy };
}

function Status({ state }: { state: NoteState }) {
  if (state.kind === "queued") return <span className={STATUS}>Chờ gửi câu</span>;
  if (state.kind === "hashing") return <span className={STATUS}>Đang chuẩn bị…</span>;
  if (state.kind === "uploading") return <span className={STATUS}>đang tải {state.percent}%</span>;
  if (state.kind === "ready") return <span className={STATUS}>Đã tải lên</span>;
  return (
    <span role="alert" data-copy="tam" className="text-small text-pencil">
      {logMessage(state.code)}
    </span>
  );
}

/** The files chosen, each with its state; a refused one can be dropped from the list. */
export function NoteList({ rows, onRemove }: { rows: Row[]; onRemove: (key: number) => void }) {
  if (rows.length === 0) return null;
  return (
    <ul aria-label="Ghi chú đã chọn" className="mt-4 mb-0 flex list-none flex-col gap-3 p-0">
      {rows.map((row) => (
        <li key={row.key} className="flex min-w-0 flex-wrap items-center gap-x-4 gap-y-1">
          <b className="min-w-0 break-words font-semibold">{row.file.name}</b>
          <span role="status">
            <Status state={row.state} />
          </span>
          {row.state.kind === "uploading" ? (
            <progress
              value={row.state.percent}
              max={100}
              aria-label={`Đang tải ${row.file.name}`}
              className="h-2 w-24 accent-hong"
            />
          ) : null}
          {row.state.kind !== "hashing" && row.state.kind !== "uploading" ? (
            <Button type="button" variant="quiet" onClick={() => onRemove(row.key)}>
              Bỏ
              <span className="sr-only"> {row.file.name}</span>
            </Button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

/** The drop zone: drag files onto it or press to choose. */
export function NoteDrop({ onAdd }: { onAdd: (files: FileList | File[]) => void }) {
  const [over, setOver] = useState(false);
  return (
    <label
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setOver(false);
        onAdd(event.dataTransfer.files);
      }}
      className={`mt-7 flex min-h-35 cursor-pointer flex-col items-center justify-center gap-1.5 rounded-sheet border-[1.5px] border-dashed border-line-strong p-6 text-center focus-within:outline-2 focus-within:outline-offset-3 focus-within:outline-focus ${
        over ? "bg-rose-100" : "hover:bg-rose-100"
      }`}
    >
      <Upload className="size-6" aria-hidden="true" />
      <b className="font-semibold">
        Thả ảnh vở hoặc file ghi chú vào đây
      </b>
      <span className="text-small text-ink-soft">JPG, PNG, PDF, TXT, MD · không bắt buộc</span>
      <input
        type="file"
        accept="image/jpeg,image/png,application/pdf,text/plain,text/markdown,.jpg,.jpeg,.png,.pdf,.txt,.md"
        multiple
        className="sr-only"
        aria-label="Chọn ảnh vở hoặc file ghi chú"
        onChange={(event) => {
          onAdd(event.currentTarget.files ?? []);
          event.currentTarget.value = "";
        }}
      />
    </label>
  );
}
