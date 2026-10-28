"use client";

import { FileUp } from "lucide-react";
import { useRef, useState } from "react";

import { checkFile, uploadPdf, type UploadState } from "@/lib/upload-client";
import { uploadMessage } from "@/lib/upload-copy";

// T4.6 (US-01 AC7; screens-html/screens/subject-new.html, states "upload" and "files"): choose or
// drop PDFs, each goes straight to storage with its own row: "đang tải 64%", "Đang đọc tài liệu…"
// (stored, waiting for ai-service: T4.7), or the reason it was refused. Files go one after the
// other, so a long list does not eat the 30-asks-an-hour limit all at once.

type Row = { key: number; name: string; state: UploadState };

const STATUS = "text-small font-semibold text-ink-soft";

function Status({ state }: { state: UploadState }) {
  if (state.kind === "hashing") return <span className={STATUS} role="status">Đang chuẩn bị…</span>;
  if (state.kind === "uploading") {
    return (
      <span className={STATUS} role="status">
        đang tải {state.percent}%
      </span>
    );
  }
  if (state.kind === "checking" || state.kind === "done") {
    return (
      <span className={STATUS} role="status">
        Đang đọc tài liệu…
      </span>
    );
  }
  return (
    <p role="alert" data-copy="tam" className="m-0 text-small text-pencil">
      {uploadMessage(state.code)}
    </p>
  );
}

export function Uploader({ subjectId }: { subjectId: string }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [over, setOver] = useState(false);
  const next = useRef(0);
  const busy = useRef(Promise.resolve());

  function update(key: number, state: UploadState) {
    setRows((all) => all.map((row) => (row.key === key ? { ...row, state } : row)));
  }

  function add(files: FileList | File[]) {
    for (const file of Array.from(files)) {
      const key = next.current++;
      const problem = checkFile(file);
      setRows((all) => [
        ...all,
        { key, name: file.name, state: problem ? { kind: "failed", code: problem } : { kind: "hashing" } },
      ]);
      if (problem) continue;
      busy.current = busy.current
        .then(() => uploadPdf(subjectId, file, (state) => update(key, state)))
        .catch(() => update(key, { kind: "failed", code: "unavailable" }));
    }
  }

  return (
    <div>
      <label
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);
          add(event.dataTransfer.files);
        }}
        className={`mt-6 flex cursor-pointer flex-col items-center gap-2 rounded-sheet border-2 border-dashed border-line-strong px-6 py-10 text-center focus-within:outline-2 focus-within:outline-offset-3 focus-within:outline-focus ${
          over ? "bg-rose-100" : "bg-sunken"
        }`}
      >
        <FileUp className="size-6" aria-hidden="true" />
        <b data-copy="tam" className="font-semibold">
          Thả file vào đây hoặc bấm để chọn
        </b>
        <span className="text-small text-ink-soft" data-copy="tam">
          Chỉ PDF, tối đa 100 MB mỗi file
        </span>
        <input
          type="file"
          accept="application/pdf,.pdf"
          multiple
          className="sr-only"
          onChange={(event) => {
            add(event.currentTarget.files ?? []);
            event.currentTarget.value = "";
          }}
        />
      </label>
      {rows.length > 0 ? (
        <ul className="mt-6 mb-0 flex list-none flex-col gap-4 p-0">
          {rows.map((row) => (
            <li key={row.key} className="flex min-w-0 flex-col gap-2 border-b border-line pb-4">
              <b className="min-w-0 break-words">{row.name}</b>
              <Status state={row.state} />
              {row.state.kind === "uploading" ? (
                <progress
                  value={row.state.percent}
                  max={100}
                  aria-label={`Đang tải ${row.name}`}
                  className="h-2 w-full accent-hong"
                />
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
