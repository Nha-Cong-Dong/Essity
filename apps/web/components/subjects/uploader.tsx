"use client";

import { FileUp } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { DocRole } from "@/components/syllabus/doc-role";
import { patchDocument } from "@/lib/syllabus/api";
import type { Role } from "@/lib/syllabus/roles";

import { checkFile, uploadPdf, type UploadState } from "@/lib/upload-client";
import { uploadMessage } from "@/lib/upload-copy";

// T4.6 (US-01 AC7; screens-html/screens/subject-new.html, states "upload" and "files"): choose or
// drop PDFs, each goes straight to storage with its own row: "đang tải 64%", "Đang đọc tài liệu…"
// (stored, waiting for ai-service: T4.7), or the reason it was refused. Files go one after the
// other, so a long list does not eat the 30-asks-an-hour limit all at once.

type Row = { key: number; name: string; state: UploadState; role?: Role };

const STATUS = "text-small font-semibold text-ink-soft";

const POLL_MS = 3000;
const MAX_POLLS = 100; // 5 minutes of 3 s

// The file is stored; ai-service reads it in the background. Ask until the document reaches a
// terminal status, so the row does not stay on "Đang đọc tài liệu…" until a reload (REALFIX).
function ReadStatus({ documentId, role }: { documentId: string; role?: Role }) {
  const [phase, setPhase] = useState<"reading" | "ready" | "failed">("reading");
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let tries = 0;
    const look = async () => {
      let status: string | null = null;
      try {
        const response = await fetch(`/api/documents/${documentId}`);
        if (response.ok) status = ((await response.json()) as { status?: string }).status ?? null;
      } catch {
        // offline: try again
      }
      if (!alive) return;
      if (status === "indexed") {
        // The tab fixes the role (H2) but a new document is auxiliary: say so once it is read. Without
        // this the Đề cương page finds no textbook while stats already count the sections.
        const apiRole = role === "main" ? "textbook" : role === "bank" ? "question_bank" : null;
        if (apiRole) await patchDocument(documentId, { role: apiRole }).catch(() => undefined);
        if (!alive) return;
        return setPhase("ready");
      }
      if (status === "failed" || status === "rejected") return setPhase("failed");
      if (++tries < MAX_POLLS) timer = setTimeout(() => void look(), POLL_MS);
    };
    timer = setTimeout(() => void look(), POLL_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [documentId, role]);
  if (phase === "failed") {
    return (
      <p role="alert" className="m-0 text-small text-pencil">
        Chưa đọc được tài liệu này. Thử tải lại file.
      </p>
    );
  }
  return (
    <span className={STATUS} role="status">
      {phase === "ready" ? "Đã đọc xong" : "Đang đọc tài liệu…"}
    </span>
  );
}

function Status({ state, role }: { state: UploadState; role?: Role }) {
  if (state.kind === "hashing") return <span className={STATUS} role="status">Đang chuẩn bị…</span>;
  if (state.kind === "uploading") {
    return (
      <span className={STATUS} role="status">
        đang tải {state.percent}%
      </span>
    );
  }
  if (state.kind === "done" && state.documentId) return <ReadStatus documentId={state.documentId} role={role} />;
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

// V15: the one small tag under a stored file, from the tab it was put in.
const ROLE_TAG: Record<Role, string> = { main: "#giáo trình chính", supplementary: "#giáo trình phụ", bank: "#câu hỏi" };

// T7.5 (US-01 AC4): once a file is stored, its role is chosen right under it (DocRole). The first
// file is the main textbook when the subject has none yet; the rest are supplementary.
export function Uploader({
  subjectId,
  hasMain = true,
  fixedRole,
  onCount,
}: {
  subjectId: string;
  hasMain?: boolean;
  /** H2: the upload tab decides the role of every file put in it. */
  fixedRole?: Role;
  /** V14: how many files of this tab are stored, so the screen's own button can show. */
  onCount?: (done: number, uploading: number) => void;
}) {
  const [rows, setRows] = useState<Row[]>([]);
  const [over, setOver] = useState(false);
  const next = useRef(0);
  const busy = useRef(Promise.resolve());
  const claimed = useRef(hasMain);

  const doneCount = rows.filter((row) => row.state.kind === "done").length;
  const runningCount = rows.filter((row) => row.state.kind === "hashing" || row.state.kind === "uploading").length;
  useEffect(() => {
    onCount?.(doneCount, runningCount);
  }, [doneCount, runningCount, onCount]);

  function update(key: number, state: UploadState) {
    setRows((all) =>
      all.map((row) => {
        if (row.key !== key) return row;
        if (state.kind !== "done" || row.role !== undefined) return { ...row, state };
        const role: Role = fixedRole ?? (claimed.current ? "supplementary" : "main");
        claimed.current = true;
        return { ...row, state, role };
      }),
    );
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
        className={`mt-6 flex cursor-pointer flex-col items-center gap-2 rounded-sheet border-2 border-dashed border-rose-300 px-6 py-10 text-center focus-within:outline-2 focus-within:outline-offset-3 focus-within:outline-focus ${
          over ? "bg-rose-100" : "bg-rose-50"
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
              <Status state={row.state} role={fixedRole} />
              {row.state.kind === "uploading" ? (
                <progress
                  value={row.state.percent}
                  max={100}
                  aria-label={`Đang tải ${row.name}`}
                  className="h-2 w-full accent-hong"
                />
              ) : null}
              {row.state.kind === "done" && fixedRole ? (
                <span className="w-fit rounded-control bg-rose-100 px-2 py-1 text-small font-semibold">{ROLE_TAG[fixedRole]}</span>
              ) : null}
              {row.state.kind === "done" && !fixedRole && row.state.documentId && row.role ? (
                <DocRole subjectId={subjectId} documentId={row.state.documentId} name={row.name} initialRole={row.role} />
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {!fixedRole && rows.some((row) => row.state.kind === "done") ? (
        <div className="mt-6">
          <Button render={<a href={`/subjects/${subjectId}/syllabus`} />}>Vào môn học</Button>
        </div>
      ) : null}
    </div>
  );
}
