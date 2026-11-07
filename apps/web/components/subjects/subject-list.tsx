"use client";

import {
  type FormEvent,
  type KeyboardEvent,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";

import { FieldError } from "@/components/field-error";
import {
  checkSubject,
  refusalErrors,
  type SubjectErrors,
  SubjectFields,
} from "@/components/subjects/subject-fields";
import { FieldGrain } from "@/components/today-v2/field-art";
import { Mascot } from "@/components/mascot";
import { SubjectMenu } from "@/components/subjects/subject-menu";
import { SubjectsFrame } from "@/components/subjects/subjects-frame";
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
  /** Syllabus parts studied of all (from /v1/stats); absent when the stats did not answer. */
  progress?: { studied: number; leaves: number };
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
  const json = (await response.json().catch(() => ({}))) as Record<
    string,
    unknown
  >;
  return { status: response.status, json };
}

/** DELETE through web's route: deleted (204, or 404: already gone), refused, or not answered. */
async function deleteSubject(
  id: string,
): Promise<"deleted" | "signed_out" | "unavailable"> {
  let response: Response;
  try {
    response = await fetch(`/api/subjects/${id}`, { method: "DELETE" });
  } catch {
    return "unavailable";
  }
  if (response.status === 204 || response.status === 404) return "deleted";
  if (response.status === 401) return "signed_out";
  return "unavailable";
}

/** mockups subjects.html: a thin bar and "x/y phần" under the date line; no syllabus says so. */
function RowProgress({ studied, leaves }: { studied: number; leaves: number }) {
  if (leaves <= 0) return <span className="mt-2 text-meta text-ink-soft">Chưa có đề cương</span>;
  const done = Math.min(Math.max(studied, 0), leaves);
  return (
    <span className="mt-2 flex items-center gap-3">
      <span
        role="progressbar"
        aria-label="Tiến độ đề cương"
        aria-valuemin={0}
        aria-valuemax={leaves}
        aria-valuenow={done}
        className="h-1.5 min-w-0 flex-1 overflow-hidden rounded-full bg-block"
      >
        <span className="block h-full rounded-full bg-hong" style={{ width: `${(done / leaves) * 100}%` }} />
      </span>
      <span className="whitespace-nowrap text-meta text-ink-soft tabular-nums">
        {done}/{leaves} phần
      </span>
    </span>
  );
}

type RowProps = {
  initial: ListedSubject;
  example: string;
  onOpen: () => void;
  onDeleted: () => void;
  /** Tells the list a row is being edited or asked about deletion, so it can hide "Thêm môn". */
  onBusy: (id: string, busy: boolean) => void;
  /** A saved edit: the list takes the new values (the "Kỳ thi gần nhất" block reads them). */
  onChanged: (subject: ListedSubject) => void;
};

function SubjectRow({ initial, example, onOpen, onDeleted, onBusy, onChanged }: RowProps) {
  const [subject, setSubject] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(initial.name);
  const [examDate, setExamDate] = useState(formatExamDate(initial.exam_date));
  const [errors, setErrors] = useState<SubjectErrors>({});
  const [formError, setFormError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteFailed, setDeleteFailed] = useState(false);
  // Where focus goes once the view it names is on screen (plan F7): set with the state change
  // that shows that view, taken after the render.
  const focusTo = useRef<"keep" | "delete" | "edit" | "name" | null>(null);
  const editRef = useRef<HTMLButtonElement>(null);
  const keepRef = useRef<HTMLButtonElement>(null);
  const ids = {
    name: `subject-${subject.id}-name`,
    confirm: `subject-${subject.id}-confirm`,
    deleteError: `subject-${subject.id}-delete-error`,
  };

  useEffect(() => {
    onBusy(initial.id, editing || confirming);
    return () => onBusy(initial.id, false);
  }, [initial.id, editing, confirming, onBusy]);

  useEffect(() => {
    if (focusTo.current === null) return;
    if (focusTo.current === "name") document.getElementById(`edit-${subject.id}-subject-name`)?.focus();
    else ({ keep: keepRef, delete: editRef, edit: editRef })[focusTo.current].current?.focus();
    focusTo.current = null;
  });

  function askToDelete() {
    onOpen();
    setSaved(false);
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
    setDeleteFailed(true);
  }

  function open() {
    onOpen();
    setName(subject.name);
    setExamDate(formatExamDate(subject.exam_date));
    setErrors({});
    setFormError(false);
    setSaved(false);
    setConfirming(false);
    setEditing(true);
    focusTo.current = "name";
  }

  // Leaves the edit form for the row and gives focus back to "Sửa" (not while a save is running).
  function closeEdit() {
    if (busy) return;
    setEditing(false);
    focusTo.current = "edit";
  }

  // Escape works wherever focus is while the form is open (it was form-only before).
  useEffect(() => {
    if (!editing) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") closeEdit();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  });

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const checked = checkSubject(name, examDate);
    setErrors(checked.errors);
    setFormError(false);
    if (
      checked.errors.name ||
      checked.errors.examDate ||
      checked.iso === undefined
    )
      return;

    // Only what changed: core-api checks the date only when it changes (plan B11).
    const body: Record<string, string> = {};
    // core-api stores names composed (NFC): the same name typed as combining marks is no change.
    if (name.trim().normalize("NFC") !== subject.name) body.name = name;
    if (checked.iso !== subject.exam_date) body.exam_date = checked.iso;
    if (Object.keys(body).length === 0) return setEditing(false);

    setBusy(true);
    const result = await patchSubject(subject.id, body);
    setBusy(false);
    const changed =
      result.status === 200
        ? (result.json?.subject as ListedSubject | undefined)
        : undefined;
    if (changed) {
      setSubject(changed);
      onChanged(changed);
      setEditing(false);
      setSaved(true);
      return;
    }
    if (result.status === 401) return go("/login");
    const refused =
      result.status === 404
        ? { name: "subject_not_found" as const }
        : refusalErrors(result.status, result.json);
    if (refused) setErrors(refused);
    else setFormError(true);
  }

  const letter = Array.from(subject.name.trim())[0]?.toLocaleUpperCase("vi") ?? "";
  return (
    <li className="min-w-0 border-t border-line first:border-t-0">
      {/* DESIGN-V4 (mockups subjects.html): a row of the one white sheet: letter tile | name + date line |
          "⋯" (Sửa, Xóa). The name wraps between words, never inside one. */}
      <div className="grid grid-cols-[3rem_minmax(0,1fr)_auto] items-center gap-x-4 py-4 min-[640px]:grid-cols-[3.5rem_minmax(0,1fr)_auto]">
        <span
          aria-hidden="true"
          className="grid size-12 place-items-center rounded-slip bg-block font-display text-lead font-bold text-hong-text min-[640px]:size-14"
        >
          {letter}
        </span>
        <div className="flex min-w-0 flex-col">
          <a
            id={ids.name}
            href={`/subjects/${subject.id}`}
            className="min-w-0 font-display text-tile font-semibold break-words text-inherit no-underline hover:text-hong-text"
          >
            {subject.name}
          </a>
          {/* The space between the halves keeps them two words for a screen reader (plan G9). */}
          <span className="flex flex-wrap gap-x-2 text-meta">
            <span className="whitespace-nowrap">
              thi {formatExamDate(subject.exam_date)}
            </span>{" "}
            <span className="whitespace-nowrap text-ink-soft">
              {daysLeftText(subject.days_until_exam)}
            </span>
          </span>
          {subject.progress ? <RowProgress {...subject.progress} /> : null}
        </div>
        {!editing && !confirming ? (
          <SubjectMenu
            ref={editRef}
            name={subject.name}
            onEdit={open}
            onDelete={askToDelete}
            describedBy={ids.name}
          />
        ) : (
          <span aria-hidden="true" className="size-11" />
        )}
      </div>
      {/* Always on the page, so a screen reader reads "Đã lưu." when it appears (plan F7). */}
      <p
        role="status"
        className={
          saved ? "m-0 pb-3 text-small text-ink-soft" : "sr-only"
        }
      >
        {saved ? SUBJECT_MESSAGES.saved : ""}
      </p>
      {confirming && (
        <div
          role="group"
          aria-labelledby={`${ids.name} ${ids.confirm}`}
          onKeyDown={onConfirmKey}
          className="flex max-w-120 flex-col gap-5 pb-5"
        >
          <p id={ids.confirm} className="m-0 text-body">
            Xóa môn {subject.name}? Lịch sử ôn và luyện tập của môn cũng sẽ ẩn
            theo.
          </p>
          <div role="alert">
            {deleteFailed && (
              <FieldError id={ids.deleteError}>
                {SUBJECT_MESSAGES.unavailable}
              </FieldError>
            )}
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Button
              type="button"
              variant="secondary"
              pending={deleting}
              onClick={confirmDelete}
              aria-describedby={deleteFailed ? ids.deleteError : undefined}
            >
              Xóa môn
            </Button>
            <Button
              ref={keepRef}
              type="button"
              variant="quiet"
              disabled={deleting}
              onClick={keep}
            >
              Giữ môn
            </Button>
          </div>
        </div>
      )}
      {editing && !confirming && (
        <form
          method="post"
          onSubmit={save}
          className="flex max-w-120 flex-col gap-5 pb-5"
          noValidate
        >
          <SubjectFields
            idPrefix={`edit-${subject.id}-`}
            name={name}
            examDate={examDate}
            example={example}
            errors={errors}
            onName={setName}
            onExamDate={setExamDate}
          />
          {formError && (
            <FieldError id={`edit-${subject.id}-error`}>
              {SUBJECT_MESSAGES.unavailable}
            </FieldError>
          )}
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" variant="secondary" pending={busy}>
              Lưu
            </Button>
            <Button
              type="button"
              variant="quiet"
              onClick={closeEdit}
            >
              Hủy
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

/** The soonest exam still ahead, as the one field block of the screen (DESIGN-V4: the one field, sticky). */
function NextExam({ subjects }: { subjects: ListedSubject[] }) {
  const ahead = subjects.filter((subject) => subject.days_until_exam >= 0);
  if (ahead.length === 0) return null;
  const next = ahead.reduce((a, b) =>
    b.days_until_exam < a.days_until_exam ? b : a,
  );
  return (
    <aside
      aria-label="Kỳ thi gần nhất"
      className="relative isolate flex min-w-0 flex-col gap-5 overflow-hidden rounded-tile bg-field p-6 text-on-plum max-[1099px]:order-first min-[1100px]:sticky min-[1100px]:top-6 min-[1100px]:col-span-4 min-[1100px]:p-8"
    >
      <FieldGrain />
      <p className="m-0 font-display text-lead">Kỳ thi gần nhất</p>
      <p className="m-0 flex items-baseline gap-3">
        <span className={`font-display leading-none font-semibold tracking-[-0.05em] tabular-nums ${next.days_until_exam === 0 ? "text-title" : "text-display"}`}>
          {next.days_until_exam === 0 ? "Hôm nay" : next.days_until_exam}
        </span>{" "}
        <span className="text-lead font-semibold">{next.days_until_exam === 0 ? "có kỳ thi" : "ngày"}</span>
      </p>
      <div className="flex flex-col gap-1">
        <p className="m-0 font-display text-tile font-semibold break-words">{next.name}</p>
        <p className="m-0 text-body text-on-plum-soft">thi {formatExamDate(next.exam_date)}</p>
      </div>
      <a
        href={`/subjects/${next.id}`}
        className="inline-flex min-h-13 max-w-full items-center justify-center self-stretch rounded-full bg-on-plum-action px-6 py-2 text-center font-semibold text-on-plum-action-fg no-underline hover:brightness-105"
      >
        Vào {next.name}
      </a>
    </aside>
  );
}

/** Where a deleted subject was: no name, no button; focused so it is read (plan F7). */
function DeletedRow() {
  const ref = useRef<HTMLParagraphElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <li className="border-t border-line py-5 first:border-t-0">
      <p ref={ref} tabIndex={-1} className="m-0 text-small text-ink-soft">
        Đã xóa môn.
      </p>
    </li>
  );
}

export function SubjectList({
  subjects,
  example,
}: {
  subjects: ListedSubject[];
  example: string;
}) {
  // One placeholder at a time (plan F7): a new delete, or "Sửa" on any row, drops the old one.
  // One state, updated from its latest value: two deletes answered in turn must not bring the
  // first subject back from a stale render (review 1ac2df7 #1).
  const [{ rows, deletedId }, setList] = useState<{
    rows: ListedSubject[];
    deletedId: string | null;
  }>({
    rows: subjects,
    deletedId: null,
  });
  const remaining = rows.filter((subject) => subject.id !== deletedId);
  // Rows being edited or asked about deletion: no "Tạo môn" / "Thêm môn" meanwhile (user 05/11).
  const [busyIds, setBusyIds] = useState<ReadonlySet<string>>(new Set());
  const setBusy = useCallback((id: string, busy: boolean) => {
    setBusyIds((cur) => {
      if (cur.has(id) === busy) return cur;
      const next = new Set(cur);
      if (busy) next.add(id);
      else next.delete(id);
      return next;
    });
  }, []);
  const anyBusy = busyIds.size > 0;

  function dropPlaceholder() {
    setList((list) =>
      list.deletedId === null
        ? list
        : {
            rows: list.rows.filter((subject) => subject.id !== list.deletedId),
            deletedId: null,
          },
    );
  }

  function changed(next: ListedSubject) {
    setList((list) => ({
      ...list,
      rows: list.rows.map((row) => (row.id === next.id ? { ...row, ...next } : row)),
    }));
  }

  function deleted(id: string) {
    setList((list) => ({
      rows: list.rows.filter(
        (subject) => subject.id === id || subject.id !== list.deletedId,
      ),
      deletedId: id,
    }));
  }

  // One frame at the root, the branch inside it, so both branches render the same tree above the
  // list: deleting the last subject keeps the same h1 node and drops only "Tạo môn" from its row
  // (T2.3c plan G15). One primary button per screen: "Tạo
  // môn" beside the title, or in the empty state (plan F9).
  return (
    <SubjectsFrame
      action={
        remaining.length > 0 && !anyBusy ? (
          <Button render={<a href="/subjects/new" />} nativeButton={false}>
            Tạo môn
          </Button>
        ) : undefined
      }
    >
      {remaining.length === 0 ? (
        <>
          {deletedId !== null && (
            <ul className="m-0 mb-5 flex list-none flex-col rounded-tile bg-sheet px-6 p-0 shadow-sheet">
              <DeletedRow key={deletedId} />
            </ul>
          )}
          {/* No subject yet: one field block with Bé Trang and the one primary button (DESIGN-V4). */}
          <section
            aria-labelledby="subjects-empty"
            className="relative isolate grid items-center gap-6 overflow-hidden rounded-tile bg-field p-8 text-on-plum min-[700px]:grid-cols-[minmax(0,1fr)_auto] min-[700px]:p-12"
          >
            <FieldGrain />
            <div className="flex flex-col items-start gap-3">
              <h2 id="subjects-empty" className="m-0 font-display text-title">
                Chưa có môn nào.
              </h2>
              <p className="m-0 text-read text-on-plum-soft">Tạo môn đầu tiên bằng tên và ngày thi.</p>
              <a
                href="/subjects/new"
                className="mt-2 inline-flex h-13 items-center rounded-full bg-on-plum-action px-6 font-semibold text-on-plum-action-fg no-underline hover:brightness-105"
              >
                Tạo môn
              </a>
            </div>
            <Mascot pose="rong" tone="solid" size="lg" className="max-[699px]:order-first max-[699px]:size-36" />
          </section>
        </>
      ) : (
        <div className="grid min-w-0 items-start gap-5 min-[1100px]:grid-cols-12">
          <ul className="m-0 list-none rounded-tile bg-sheet px-5 py-1 shadow-sheet min-[640px]:px-6 min-[1100px]:col-span-8">
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
                  onBusy={setBusy}
                  onChanged={changed}
                />
              ),
            )}
          </ul>
          <NextExam subjects={remaining} />
        </div>
      )}
    </SubjectsFrame>
  );
}
