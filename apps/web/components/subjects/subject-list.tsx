"use client";

import { type FormEvent, type KeyboardEvent, useEffect, useRef, useState } from "react";

import { FieldError } from "@/components/field-error";
import { checkSubject, refusalErrors, type SubjectErrors, SubjectFields } from "@/components/subjects/subject-fields";
import { Button } from "@/components/ui/button";
import { daysLeftText, formatExamDate } from "@/lib/exam-date";
import { go } from "@/lib/navigate";
import { SUBJECT_MESSAGES } from "@/lib/subject-copy";

// T1.20, DESIGN.md §6.8: the subject list. "Sửa" edits a row in place (plan K2) until the
// subject page arrives (T4.9). Page coverage ("đã học 43/120 trang") waits for T5.5.
// T2.3b (us-01 AC8, plan F7, F9): "Xóa môn" under the edit form, confirmed in place; a deleted
// row leaves "Đã xóa môn." where it was. Its sentences are placeholders (R09).

export type ListedSubject = {
  id: string;
  name: string;
  exam_date: string;
  days_until_exam: number;
  has_history: boolean;
};

/** PATCH through web's route (postJson only POSTs). */
async function patchSubject(id: string, body: Record<string, string>) {
  let response: Response;
  try {
    response = await fetch(`/api/subjects/${id}`, {
      method: "PATCH",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    return { status: 0 } as const;
  }
  const json = (await response.json().catch(() => ({}))) as Record<string, unknown>;
  return { status: response.status, json };
}

/** DELETE through web's route: deleted (204, or 404: already gone), refused, or not answered. */
async function deleteSubject(id: string): Promise<"deleted" | "history" | "signed_out" | "unavailable"> {
  let response: Response;
  try {
    response = await fetch(`/api/subjects/${id}`, { method: "DELETE" });
  } catch {
    return "unavailable";
  }
  if (response.status === 204 || response.status === 404) return "deleted";
  if (response.status === 409) return "history";
  if (response.status === 401) return "signed_out";
  return "unavailable";
}

type RowProps = {
  initial: ListedSubject;
  example: string;
  onOpen: () => void;
  onDeleted: () => void;
};

function SubjectRow({ initial, example, onOpen, onDeleted }: RowProps) {
  const [subject, setSubject] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(initial.name);
  const [examDate, setExamDate] = useState(formatExamDate(initial.exam_date));
  const [errors, setErrors] = useState<SubjectErrors>({});
  const [formError, setFormError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [hasHistory, setHasHistory] = useState(initial.has_history);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteFailed, setDeleteFailed] = useState(false);
  // Where focus goes once the view it names is on screen (plan F7): set with the state change
  // that shows that view, taken after the render.
  const focusTo = useRef<"keep" | "delete" | "history" | null>(null);
  const keepRef = useRef<HTMLButtonElement>(null);
  const deleteRef = useRef<HTMLButtonElement>(null);
  const historyRef = useRef<HTMLParagraphElement>(null);
  const ids = {
    name: `subject-${subject.id}-name`,
    confirm: `subject-${subject.id}-confirm`,
    deleteError: `subject-${subject.id}-delete-error`,
  };

  useEffect(() => {
    if (focusTo.current === null) return;
    ({ keep: keepRef, delete: deleteRef, history: historyRef })[focusTo.current].current?.focus();
    focusTo.current = null;
  });

  function askToDelete() {
    setDeleteFailed(false);
    setConfirming(true);
    focusTo.current = "keep";
  }

  function keep() {
    if (deleting) return;
    setConfirming(false);
    focusTo.current = "delete";
  }

  function onConfirmKey(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") keep();
  }

  async function confirmDelete() {
    setDeleting(true);
    setDeleteFailed(false);
    const outcome = await deleteSubject(subject.id);
    setDeleting(false);
    if (outcome === "deleted") return onDeleted();
    if (outcome === "signed_out") return go("/login");
    if (outcome === "history") {
      // History appeared after the page loaded (another tab began a review): say why, in place.
      setHasHistory(true);
      setConfirming(false);
      focusTo.current = "history";
      return;
    }
    setDeleteFailed(true);
  }

  function open() {
    onOpen();
    setName(subject.name);
    setExamDate(formatExamDate(subject.exam_date));
    setErrors({});
    setFormError(false);
    setSaved(false);
    setEditing(true);
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const checked = checkSubject(name, examDate);
    setErrors(checked.errors);
    setFormError(false);
    if (checked.errors.name || checked.errors.examDate || checked.iso === undefined) return;

    // Only what changed: core-api checks the date only when it changes (plan B11).
    const body: Record<string, string> = {};
    // core-api stores names composed (NFC): the same name typed as combining marks is no change.
    if (name.trim().normalize("NFC") !== subject.name) body.name = name;
    if (checked.iso !== subject.exam_date) body.exam_date = checked.iso;
    if (Object.keys(body).length === 0) return setEditing(false);

    setBusy(true);
    const result = await patchSubject(subject.id, body);
    setBusy(false);
    const changed = result.status === 200 ? (result.json?.subject as ListedSubject | undefined) : undefined;
    if (changed) {
      setSubject(changed);
      setEditing(false);
      setSaved(true);
      return;
    }
    if (result.status === 401) return go("/login");
    const refused =
      result.status === 404 ? { name: "subject_not_found" as const } : refusalErrors(result.status, result.json);
    if (refused) setErrors(refused);
    else setFormError(true);
  }

  return (
    <li className="flex flex-col gap-4 border-b border-line py-5 last:border-b-0">
      <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
        <span aria-hidden="true" className="h-14 w-11 shrink-0 rounded-slip bg-(color:--rose-200) shadow-sheet" />
        <span id={ids.name} className="min-w-0 flex-1 text-section font-semibold">
          {subject.name}
        </span>
        <span className="flex flex-col items-end text-small">
          <span>thi {formatExamDate(subject.exam_date)}</span>
          <span className="text-ink-soft">{daysLeftText(subject.days_until_exam)}</span>
        </span>
        {!editing && (
          <Button variant="quiet" onClick={open} aria-label={`Sửa ${subject.name}`}>
            Sửa
          </Button>
        )}
      </div>
      {/* Always on the page, so a screen reader reads "Đã lưu." when it appears (plan F7). */}
      <p role="status" className={saved ? "m-0 text-small text-ink-soft" : "sr-only"}>
        {saved ? SUBJECT_MESSAGES.saved : ""}
      </p>
      {editing && confirming && (
        <div
          role="group"
          aria-labelledby={`${ids.name} ${ids.confirm}`}
          onKeyDown={onConfirmKey}
          className="flex max-w-120 flex-col gap-5"
        >
          <p id={ids.confirm} data-copy="tam" className="m-0 text-body">
            Xóa môn này khỏi danh sách và phiên ôn?
          </p>
          <div role="alert">
            {deleteFailed && <FieldError id={ids.deleteError}>{SUBJECT_MESSAGES.unavailable}</FieldError>}
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Button
              type="button"
              variant="secondary"
              pending={deleting}
              onClick={confirmDelete}
              aria-describedby={deleteFailed ? ids.deleteError : undefined}
              data-copy="tam"
            >
              Xóa môn
            </Button>
            <Button ref={keepRef} type="button" variant="quiet" disabled={deleting} onClick={keep} data-copy="tam">
              Giữ môn
            </Button>
          </div>
        </div>
      )}
      {editing && !confirming && (
        <form method="post" onSubmit={save} className="flex max-w-120 flex-col gap-5" noValidate>
          <SubjectFields
            idPrefix={`edit-${subject.id}-`}
            name={name}
            examDate={examDate}
            example={example}
            errors={errors}
            onName={setName}
            onExamDate={setExamDate}
          />
          {formError && <FieldError id={`edit-${subject.id}-error`}>{SUBJECT_MESSAGES.unavailable}</FieldError>}
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" variant="secondary" pending={busy}>
              Lưu
            </Button>
            <Button type="button" variant="quiet" onClick={() => setEditing(false)}>
              Hủy
            </Button>
          </div>
        </form>
      )}
      {editing && !confirming && (
        <div className="max-w-120 border-t border-line pt-5">
          {hasHistory ? (
            <p ref={historyRef} tabIndex={-1} data-copy="tam" className="m-0 text-small text-ink-soft">
              Môn này đã có bài ôn nên chưa xóa được ở đây.
            </p>
          ) : (
            <Button
              ref={deleteRef}
              type="button"
              variant="quiet"
              onClick={askToDelete}
              aria-describedby={ids.name}
              data-copy="tam"
            >
              Xóa môn
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

/** Where a deleted subject was: no name, no button; focused so it is read (plan F7). */
function DeletedRow() {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <li className="border-b border-line py-5 last:border-b-0">
      <p ref={ref} tabIndex={-1} data-copy="tam" className="m-0 text-small text-ink-soft">
        Đã xóa môn.
      </p>
    </li>
  );
}

export function SubjectList({ subjects, example }: { subjects: ListedSubject[]; example: string }) {
  // One placeholder at a time (plan F7): a new delete, or "Sửa" on any row, drops the old one.
  // One state, updated from its latest value: two deletes answered in turn must not bring the
  // first subject back from a stale render (review 1ac2df7 #1).
  const [{ rows, deletedId }, setList] = useState<{ rows: ListedSubject[]; deletedId: string | null }>({
    rows: subjects,
    deletedId: null,
  });
  const remaining = rows.filter((subject) => subject.id !== deletedId);

  function dropPlaceholder() {
    setList((list) =>
      list.deletedId === null
        ? list
        : { rows: list.rows.filter((subject) => subject.id !== list.deletedId), deletedId: null },
    );
  }

  function deleted(id: string) {
    setList((list) => ({
      rows: list.rows.filter((subject) => subject.id === id || subject.id !== list.deletedId),
      deletedId: id,
    }));
  }

  if (remaining.length === 0) {
    return (
      <>
        {deletedId !== null && (
          <ul className="m-0 flex list-none flex-col p-0">
            <DeletedRow key={deletedId} />
          </ul>
        )}
        <div className="flex flex-col items-start gap-3 py-8">
          <p className="m-0 text-section font-semibold">Chưa có môn nào.</p>
          <p className="m-0 text-body text-ink-soft">Tạo môn đầu tiên bằng tên và ngày thi.</p>
          <Button render={<a href="/subjects/new" />} nativeButton={false} className="mt-3">
            Tạo môn
          </Button>
        </div>
      </>
    );
  }
  // One primary button per screen: "Tạo môn" above the list, or in the empty state (plan F9).
  return (
    <>
      <div className="-mt-16 mb-6 flex justify-end">
        <Button render={<a href="/subjects/new" />} nativeButton={false}>
          Tạo môn
        </Button>
      </div>
      <ul className="m-0 flex list-none flex-col p-0">
        {rows.map((subject) =>
          subject.id === deletedId ? (
            <DeletedRow key={subject.id} />
          ) : (
            <SubjectRow
              key={subject.id}
              initial={subject}
              example={example}
              onOpen={dropPlaceholder}
              onDeleted={() => deleted(subject.id)}
            />
          ),
        )}
      </ul>
    </>
  );
}
