"use client";

import { type FormEvent, useState } from "react";

import { FieldError } from "@/components/field-error";
import { checkSubject, refusalErrors, type SubjectErrors, SubjectFields } from "@/components/subjects/subject-fields";
import { Button } from "@/components/ui/button";
import { daysLeftText, formatExamDate } from "@/lib/exam-date";
import { go } from "@/lib/navigate";
import { SUBJECT_MESSAGES } from "@/lib/subject-copy";

// T1.20, DESIGN.md §6.8: the subject list. "Sửa" edits a row in place (plan K2) until the
// subject page arrives (T4.9). Page coverage ("đã học 43/120 trang") waits for T5.5.

export type ListedSubject = { id: string; name: string; exam_date: string; days_until_exam: number };

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

function SubjectRow({ initial }: { initial: ListedSubject }) {
  const [subject, setSubject] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(initial.name);
  const [examDate, setExamDate] = useState(formatExamDate(initial.exam_date));
  const [errors, setErrors] = useState<SubjectErrors>({});
  const [formError, setFormError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);

  function open() {
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
        <span className="min-w-0 flex-1 text-section font-semibold">{subject.name}</span>
        <span className="flex flex-col items-end text-small">
          <span>thi {formatExamDate(subject.exam_date)}</span>
          {subject.days_until_exam > 0 ? (
            <span className="text-ink-soft">{daysLeftText(subject.days_until_exam)}</span>
          ) : (
            // "thi hôm nay" and "đã thi" are no document's yet (DESIGN §6.8 has only "còn N ngày").
            <span className="text-ink-soft" data-copy="tam">{daysLeftText(subject.days_until_exam)}</span>
          )}
        </span>
        {!editing && (
          <Button variant="quiet" onClick={open} aria-label={`Sửa ${subject.name}`}>
            Sửa
          </Button>
        )}
      </div>
      {saved && (
        <p role="status" className="m-0 text-small text-ink-soft">
          {SUBJECT_MESSAGES.saved}
        </p>
      )}
      {editing && (
        <form method="post" onSubmit={save} className="flex max-w-120 flex-col gap-5" noValidate>
          <SubjectFields
            idPrefix={`edit-${subject.id}-`}
            name={name}
            examDate={examDate}
            errors={errors}
            onName={setName}
            onExamDate={setExamDate}
          />
          {formError && <FieldError id={`edit-${subject.id}-error`}>{SUBJECT_MESSAGES.unavailable}</FieldError>}
          <div className="flex flex-wrap items-center gap-4">
            <Button type="submit" variant="secondary" pending={busy}>
              <span data-copy="tam">Lưu</span>
            </Button>
            <Button type="button" variant="quiet" onClick={() => setEditing(false)}>
              <span data-copy="tam">Hủy</span>
            </Button>
          </div>
        </form>
      )}
    </li>
  );
}

export function SubjectList({ subjects }: { subjects: ListedSubject[] }) {
  if (subjects.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3 py-8">
        <p className="m-0 text-section font-semibold">Chưa có môn nào.</p>
        <p className="m-0 text-body text-ink-soft">Tạo môn đầu tiên bằng tên và ngày thi.</p>
        <Button render={<a href="/subjects/new" />} nativeButton={false} className="mt-3">
          Tạo môn
        </Button>
      </div>
    );
  }
  return (
    <ul className="m-0 flex list-none flex-col p-0">
      {subjects.map((subject) => (
        <SubjectRow key={subject.id} initial={subject} />
      ))}
    </ul>
  );
}
