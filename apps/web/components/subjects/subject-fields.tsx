"use client";

import { CalendarDays } from "lucide-react";
import { useRef, useSyncExternalStore } from "react";

import { AuthField } from "@/components/auth/fields";
import { FieldError } from "@/components/field-error";
import { formatExamDate, parseExamDate } from "@/lib/exam-date";
import { PLACEHOLDER_MESSAGES, type SubjectMessage, subjectMessage } from "@/lib/subject-copy";

// The two fields of a subject, and nothing else (US-01 AC1). The exam date is a text field
// typed day/month/year; the calendar button only helps fill it (plan K10).

export type SubjectErrors = { name?: SubjectMessage; examDate?: SubjectMessage };

const noSubscribe = () => () => undefined;
// Browsers without showPicker get no calendar button: a button that does nothing is worse.
const canPick = () => "showPicker" in HTMLInputElement.prototype;

function Message({ id, code, example }: { id: string; code: SubjectMessage; example: string }) {
  const text = subjectMessage(code, example);
  return <FieldError id={id}>{PLACEHOLDER_MESSAGES.has(code) ? <span data-copy="tam">{text}</span> : text}</FieldError>;
}

export function SubjectFields({
  idPrefix = "",
  name,
  examDate,
  example,
  errors,
  onName,
  onExamDate,
}: {
  idPrefix?: string;
  name: string;
  examDate: string;
  /** The example date for the placeholder and the format message (R24). */
  example: string;
  errors: SubjectErrors;
  onName: (value: string) => void;
  onExamDate: (value: string) => void;
}) {
  const ids = {
    name: `${idPrefix}subject-name`,
    date: `${idPrefix}exam-date`,
  };
  const dateInput = useRef<HTMLInputElement>(null);
  const picker = useRef<HTMLInputElement>(null);
  const pickable = useSyncExternalStore(noSubscribe, canPick, () => false);
  const typed = parseExamDate(examDate);

  function openCalendar() {
    try {
      picker.current?.showPicker();
    } catch {
      // Blocked or unsupported: the typed field is the way, so say nothing and go back to it.
      dateInput.current?.focus();
    }
  }

  return (
    <>
      <AuthField
        id={ids.name}
        name="name"
        label="Môn"
        autoComplete="off"
        value={name}
        onChange={(event) => onName(event.target.value)}
        invalid={errors.name !== undefined}
        describedBy={errors.name ? `${ids.name}-error` : undefined}
      >
        {errors.name && <Message id={`${ids.name}-error`} code={errors.name} example={example} />}
      </AuthField>

      <AuthField
        id={ids.date}
        name="exam_date"
        label="Ngày thi"
        inputMode="numeric"
        autoComplete="off"
        placeholder={example}
        ref={dateInput}
        value={examDate}
        onChange={(event) => onExamDate(event.target.value)}
        invalid={errors.examDate !== undefined}
        describedBy={errors.examDate ? `${ids.date}-error` : undefined}
      >
        {pickable && (
          <div className="relative w-fit">
            <button
              type="button"
              onClick={openCalendar}
              className="inline-flex min-h-11 items-center gap-2 rounded-control px-1 text-body font-medium text-ink underline decoration-line-strong decoration-[1.5px] underline-offset-[5px] hover:decoration-ink"
            >
              <CalendarDays className="size-5" aria-hidden="true" />
              Chọn ngày trên lịch
            </button>
            {/* Rendered (showPicker ignores a hidden input) but invisible, under the button so the
                calendar opens there. No name: the text field is the only value sent, and no min:
                the learning day, not the clock, says what "after today" means. */}
            <input
              ref={picker}
              type="date"
              aria-hidden="true"
              tabIndex={-1}
              value={"value" in typed ? typed.value : ""}
              onChange={(event) => {
                if (!event.target.value) return;
                onExamDate(formatExamDate(event.target.value));
                dateInput.current?.focus();
              }}
              className="pointer-events-none absolute bottom-0 left-0 size-px opacity-0"
            />
          </div>
        )}
        {errors.examDate && <Message id={`${ids.date}-error`} code={errors.examDate} example={example} />}
      </AuthField>
    </>
  );
}

/** The fields' own checks, before anything is sent: an empty name, a date not on the calendar. */
export function checkSubject(name: string, examDate: string): { errors: SubjectErrors; iso?: string } {
  const parsed = parseExamDate(examDate);
  const errors: SubjectErrors = {
    name: name.trim() === "" ? "name_empty" : undefined,
    examDate: "error" in parsed ? "date_format" : undefined,
  };
  return { errors, iso: "value" in parsed ? parsed.value : undefined };
}

/** A refusal from web's /api/subjects routes, as field errors (or null when it is no field's). */
export function refusalErrors(status: number, body: Record<string, unknown> | undefined): SubjectErrors | null {
  if (status !== 422 && status !== 404) return null;
  if (body?.error === "exam_date_not_in_future") return { examDate: "exam_date_not_in_future" };
  if (body?.error === "exam_date_too_far") return { examDate: "exam_date_too_far" };
  const fields = Array.isArray(body?.fields) ? body.fields : [];
  if (fields.includes("name")) return { name: "name_invalid" };
  if (fields.includes("exam_date")) return { examDate: "date_format" };
  return null;
}
