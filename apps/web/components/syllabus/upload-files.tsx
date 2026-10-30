"use client";

import { useEffect, useRef, useState } from "react";

import { unreadableText } from "@/components/documents/document-list";
import { FieldError } from "@/components/field-error";
import { Marker } from "@/components/notebook";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SUBJECT, UPLOAD_FILES, type UploadState } from "@/lib/fixtures/syllabus";
import {
  defaultRole,
  type FileKind,
  needsConfirm,
  type Role,
  switchMain,
  type UploadFile,
} from "@/lib/syllabus/roles";

import { RolePicker } from "./role-picker";

// T7.5a (US-01 AC4, AC7; DESIGN §6.4; design-decisions.md): the upload form with a role for each
// file, from fixtures. The live upload form is not touched. One primary per state: the tray's
// "Tải tài liệu lên" while empty, "Vào môn học" once there is a file, "Lưu" while a name is edited.
// Sentences marked are provisional.

const COPY = {
  heading: `Tải tài liệu cho ${SUBJECT.name}`,
  lead: "Giáo trình, bộ câu hỏi, slide hoặc ảnh vở. Câu hỏi và thẻ sẽ dựa trên đúng những trang này.",
  empty: "Chưa có tài liệu. Tải giáo trình, bộ câu hỏi, slide hoặc ảnh vở để app biết bạn học từ đâu.",
  upload: "Tải tài liệu lên",
  uploadMore: "+ Tải tài liệu lên",
  enter: "Vào môn học",
  later: "Làm sau",
};

const EXT: Record<string, FileKind> = { pdf: "pdf", docx: "docx", pptx: "pptx", jpg: "image", jpeg: "image", png: "image" };

function StatusLine({ file, onRetry }: { file: UploadFile; onRetry: () => void }) {
  switch (file.state) {
    case "uploading":
      return (
        <>
          <p className="m-0 text-small text-ink-soft">Đang tải {file.progress ?? 0}%</p>
          <div aria-hidden="true" className="h-[3px] w-full overflow-hidden rounded-full bg-sunken">
            <div className="h-full bg-ink-soft" style={{ width: `${file.progress ?? 0}%` }} />
          </div>
        </>
      );
    case "reading":
      return <p className="m-0 text-small text-ink-soft">Đang đọc tài liệu…</p>;
    case "reading-toc":
      return <p className="m-0 text-small text-ink-soft">Đang đọc mục lục…</p>;
    case "ready":
      return <p className="m-0 text-small font-semibold text-correct">Sẵn sàng</p>;
    case "partial":
      return <p className="m-0 text-small font-semibold text-partial">{unreadableText(file.unreadable ?? [])}</p>;
    case "failed":
      return (
        <p className="m-0 flex flex-wrap items-center gap-x-1 text-small">
          Không tải được <span data-user className="wrap-anywhere">{file.name}</span>. Các file khác vẫn được giữ.
          <Button variant="quiet" onClick={onRetry}>
            Thử lại
          </Button>
        </p>
      );
  }
}

export function UploadScreen({ state }: { state: UploadState }) {
  const config = state === "upload-empty" ? null : UPLOAD_FILES[state];
  const [files, setFiles] = useState<UploadFile[]>(config?.files ?? []);
  const [earlierMain, setEarlierMain] = useState<string | null>(config?.existingMain ?? null);
  const [swap, setSwap] = useState<{ id: string; focus: boolean } | null>(
    config?.open ? { id: config.open, focus: false } : null,
  );
  const [rejected, setRejected] = useState<string[]>(config?.rejected ?? []);
  const [rename, setRename] = useState<{ id: string; value: string; error: string | null } | null>(
    state === "upload-rename"
      ? { id: "b", value: "Slide tuần 1-6", error: "Đã có tài liệu tên “Slide tuần 1-6”. Đặt tên khác, ví dụ “Slide tuần 1-6 2”." }
      : null,
  );
  const [live, setLive] = useState("");
  const swapButton = useRef<HTMLButtonElement>(null);
  const picker = useRef<HTMLUListElement>(null);
  const chooser = useRef<HTMLInputElement>(null);
  const nameInput = useRef<HTMLInputElement>(null);
  const subjectHasMain = earlierMain !== null || files.some((f) => f.role === "main");
  const uploading = files.filter((f) => f.state === "uploading").length;

  useEffect(() => {
    if (swap?.focus) swapButton.current?.focus();
  }, [swap]);

  function pick(id: string, role: Role) {
    const file = files.find((f) => f.id === id)!;
    if (role === "main" && file.kind === "image") return;
    if (role === "main") {
      const current = files.find((f) => f.role === "main" && f.id !== id);
      if (current || earlierMain !== null) {
        if (needsConfirm(current, earlierMain !== null)) {
          setSwap({ id, focus: true });
          return;
        }
        setFiles(switchMain(files, id));
        setLive(`Giáo trình chính giờ là ${file.name}.`);
        return;
      }
    }
    setFiles(files.map((f) => (f.id === id ? { ...f, role, chosen: true } : f)));
  }

  function confirmSwap(id: string) {
    const file = files.find((f) => f.id === id)!;
    setFiles(switchMain(files, id));
    setEarlierMain(null);
    setSwap(null);
    setLive(`Giáo trình chính giờ là ${file.name}.`);
  }

  function keepMain(id: string) {
    setSwap(null);
    queueMicrotask(() => picker.current?.querySelector<HTMLInputElement>(`[data-file="${id}"] input[type=radio]:checked`)?.focus());
  }

  function saveName() {
    if (!rename) return;
    const value = rename.value.trim();
    if (files.some((f) => f.id !== rename.id && f.name.toLowerCase() === value.toLowerCase())) {
      setRename({ ...rename, error: `Đã có tài liệu tên “${value}”. Đặt tên khác, ví dụ “${value} 2”.` });
      nameInput.current?.focus();
      return;
    }
    setFiles(files.map((f) => (f.id === rename.id ? { ...f, name: value } : f)));
    setLive(`Đã đổi tên thành ${value}.`);
    const id = rename.id;
    setRename(null);
    queueMicrotask(() => document.getElementById(`edit-${id}`)?.focus());
  }

  function onChosen(list: FileList | null) {
    if (!list) return;
    const added: UploadFile[] = [];
    const refused: string[] = [];
    for (const item of Array.from(list)) {
      const kind = EXT[item.name.split(".").pop()?.toLowerCase() ?? ""];
      if (!kind) {
        refused.push(`Không nhận ${item.name}. App nhận PDF, DOCX, PPTX, JPG và PNG.`);
        continue;
      }
      const base: UploadFile = { id: `n${files.length + added.length}`, name: item.name.replace(/\.[^.]+$/, ""), kind, role: "supplementary", state: "ready" };
      added.push({ ...base, role: defaultRole(base, { subjectHasMain, batch: [...files, ...added] }) });
    }
    setFiles([...files, ...added]);
    setRejected(refused);
  }

  const editing = rename !== null;
  const tray = (primary: boolean) => (
    <>
      <input
        ref={chooser}
        type="file"
        multiple
        hidden
        accept=".pdf,.docx,.pptx,.jpg,.jpeg,.png"
        onChange={(e) => onChosen(e.target.files)}
        data-testid="file-input"
      />
      <Button variant={primary ? "primary" : "secondary"} onClick={() => chooser.current?.click()}>
        {primary ? COPY.upload : COPY.uploadMore}
      </Button>
    </>
  );

  return (
    <div data-state={state}>
      <h1 className="m-0 font-display text-title">
        <Marker>{COPY.heading}</Marker>
      </h1>
      <p className="m-0 mt-2 text-read text-ink-soft">{COPY.lead}</p>

      {rejected.length > 0 && (
        <div role="alert" className="mt-4 flex flex-col gap-1 rounded-sheet bg-sunken p-4 text-body">
          {rejected.map((line) => (
            <p key={line} className="m-0 wrap-anywhere">
              {line}
            </p>
          ))}
        </div>
      )}

      {files.length === 0 ? (
        <div className="mt-6 rounded-sheet bg-rose-50 p-6">
          <p className="m-0 text-body">{COPY.empty}</p>
          <div className="mt-4">{tray(true)}</div>
        </div>
      ) : (
        <ul ref={picker} className="m-0 mt-6 flex list-none flex-col p-0">
          {files.map((file) => {
            const renaming = rename?.id === file.id;
            const existing = swap?.id === file.id;
            const currentName = files.find((f) => f.role === "main" && f.id !== file.id)?.name ?? earlierMain;
            return (
              <li key={file.id} data-file={file.id} className="flex flex-col gap-3 border-b border-line py-5 first:pt-0">
                {renaming ? (
                  <form
                    method="post"
                    className="flex flex-col gap-2"
                    onSubmit={(e) => {
                      e.preventDefault();
                      saveName();
                    }}
                    onKeyDown={(e) => {
                      if (e.key === "Escape") {
                        setRename(null);
                        queueMicrotask(() => document.getElementById(`edit-${file.id}`)?.focus());
                      }
                    }}
                  >
                    <label className="flex flex-col gap-1">
                      <span className="sr-only">Tên ngắn</span>
                      <Input
                        ref={nameInput}
                        value={rename.value}
                        onChange={(e) => setRename({ ...rename, value: e.target.value, error: null })}
                        aria-invalid={rename.error !== null || undefined}
                        aria-describedby={rename.error ? `name-err-${file.id}` : undefined}
                      />
                    </label>
                    {rename.error && <FieldError id={`name-err-${file.id}`}>{rename.error}</FieldError>}
                    <div className="flex items-center gap-2">
                      <Button type="submit">Lưu</Button>
                      <Button
                        type="button"
                        variant="quiet"
                        onClick={() => {
                          setRename(null);
                          queueMicrotask(() => document.getElementById(`edit-${file.id}`)?.focus());
                        }}
                      >
                        Hủy
                      </Button>
                    </div>
                  </form>
                ) : (
                  <div className="flex items-center justify-between gap-2">
                    <p data-user className="m-0 min-w-0 text-body font-semibold wrap-anywhere">
                      {file.name}
                    </p>
                    <button
                      id={`edit-${file.id}`}
                      type="button"
                      aria-label={`Sửa tên ${file.name}`}
                      className="flex size-11 shrink-0 items-center justify-center rounded-control text-ink-soft focus-visible:outline-2 focus-visible:outline-focus"
                      onClick={() => setRename({ id: file.id, value: file.name, error: null })}
                    >
                      <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">
                        <path d="m2 14 .8-3.2L11 2.6a1.4 1.4 0 0 1 2 0l.4.4a1.4 1.4 0 0 1 0 2L5.2 13.2z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
                      </svg>
                    </button>
                  </div>
                )}
                <div className="flex flex-col gap-1">
                  <StatusLine
                    file={file}
                    onRetry={() => setFiles(files.map((f) => (f.id === file.id ? { ...f, state: "ready" } : f)))}
                  />
                </div>
                <RolePicker file={file} onPick={(role) => pick(file.id, role)} />
                {existing && (
                  <div role="group" aria-label="Đổi giáo trình chính" className="rounded-sheet bg-sunken p-4" data-swap>
                    <p className="m-0 text-body wrap-anywhere">
                      Môn này đã có giáo trình chính: <span data-user>{currentName}</span>. Đổi sang <span data-user>{file.name}</span>?
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      <Button ref={swapButton} variant="secondary" onClick={() => confirmSwap(file.id)}>
                        Đổi sang file này
                      </Button>
                      <Button variant="quiet" onClick={() => keepMain(file.id)}>
                        Giữ nguyên
                      </Button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {files.length > 0 && (
        <div className="mt-6 flex flex-col items-stretch gap-4 sm:flex-row sm:items-center">
          {tray(false)}
          <Button
            variant={editing ? "secondary" : "primary"}
            aria-describedby={uploading > 0 ? "uploading-note" : undefined}
            render={<a href={`/subjects/${SUBJECT.id}`} />}
          >
            {COPY.enter}
          </Button>
          <a href={`/subjects/${SUBJECT.id}`} className="inline-flex min-h-11 items-center justify-center text-body underline">
            {COPY.later}
          </a>
        </div>
      )}
      {uploading > 0 && (
        <p id="uploading-note" className="m-0 mt-3 text-small text-ink-soft">
          Còn {uploading} file đang tải. File đang tải sẽ dừng nếu bạn rời trang.
        </p>
      )}
      {files.length === 0 && (
        <p className="m-0 mt-4">
          <a href={`/subjects/${SUBJECT.id}`} className="inline-flex min-h-11 items-center text-body underline">
            {COPY.later}
          </a>
        </p>
      )}
      <p role="status" className="sr-only" data-live>
        {live}
      </p>
    </div>
  );
}
