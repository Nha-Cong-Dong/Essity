"use client";

import { type FormEvent, useState } from "react";

import { FieldError } from "@/components/field-error";
import { checkSubject, refusalErrors, type SubjectErrors, SubjectFields } from "@/components/subjects/subject-fields";
import { Button } from "@/components/ui/button";
import { postJson } from "@/lib/auth-errors";
import { go } from "@/lib/navigate";
import { SUBJECT_MESSAGES } from "@/lib/subject-copy";
import { isSubjectId } from "@/lib/subject-id";

// T1.20, DESIGN.md §6.8: "Môn mới" with a name and an exam date, then the upload step (US-01 AC7).
export function NewSubjectForm({ example }: { example: string }) {
  const [name, setName] = useState("");
  const [examDate, setExamDate] = useState("");
  const [errors, setErrors] = useState<SubjectErrors>({});
  const [formError, setFormError] = useState(false);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const checked = checkSubject(name, examDate);
    setErrors(checked.errors);
    setFormError(false);
    if (checked.errors.name || checked.errors.examDate || checked.iso === undefined) return;

    setBusy(true);
    const result = await postJson<{ id: unknown }>("/api/subjects", { name, exam_date: checked.iso });
    if (result.data) {
      // Only a UUID goes into the URL (review plan R3); anything else lands on the list.
      return go(isSubjectId(result.data.id) ? `/subjects/${result.data.id}/upload` : "/subjects");
    }
    if (result.status === 401) return go("/login");
    setBusy(false);
    const refused = refusalErrors(result.status, result.body);
    if (refused) setErrors(refused);
    else setFormError(true);
  }

  return (
    <form method="post" onSubmit={submit} className="flex flex-col gap-6" noValidate>
      <SubjectFields
        name={name}
        examDate={examDate}
        example={example}
        errors={errors}
        onName={setName}
        onExamDate={setExamDate}
      />
      {formError && <FieldError id="new-subject-error">{SUBJECT_MESSAGES.unavailable}</FieldError>}
      <Button type="submit" pending={busy} className="w-full">
        Tạo môn
      </Button>
    </form>
  );
}
