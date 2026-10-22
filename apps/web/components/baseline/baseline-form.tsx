"use client";

import { type FormEvent, useState } from "react";

import { AuthField } from "@/components/auth/fields";
import { FieldError } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { type AuthResult, authMessage, postJson } from "@/lib/auth-errors";
import { BASELINE_MESSAGES } from "@/lib/baseline-copy";
import { type BaselineError, parseDays, parseGpa } from "@/lib/baseline-input";
import { safeNext } from "@/lib/landing";
import { go } from "@/lib/navigate";

// T1.18, DESIGN.md §6.2: two fields and "Không nhớ", nothing else (US-11 AC1). Checked here
// first (AC3), then by core-api through /api/baseline.

type Errors = { gpa?: BaselineError; days?: BaselineError };

// core-api's 422 names a field; its sentence is the range one for that field.
const FIELD_ERRORS: Record<string, keyof Errors> = { gpa_before: "gpa", prior_ready_days: "days" };
const RANGE: Record<keyof Errors, BaselineError> = { gpa: "gpa_range", days: "days_range" };

export function BaselineForm() {
  const [gpa, setGpa] = useState("");
  const [days, setDays] = useState("");
  const [unknown, setUnknown] = useState(false);
  const [errors, setErrors] = useState<Errors>({});
  const [formError, setFormError] = useState<string>();
  const [busy, setBusy] = useState<"save" | "skip">();
  const skipping = busy === "skip";

  function follow(result: AuthResult<{ next: string }>) {
    if (result.data) return go(safeNext(result.data.next));
    if (result.status === 401) return go("/login");
    setBusy(undefined);
    if (result.status === 422) {
      const fields = result.body?.fields;
      const named = Array.isArray(fields) ? fields.map((field) => FIELD_ERRORS[String(field)]).filter(Boolean) : [];
      // A 422 naming no field comes from core-api's one body-level rule, days or "Không nhớ"
      // (review 266042d #2): it belongs under the day field, not as a network error.
      setErrors(Object.fromEntries((named.length > 0 ? named : ["days" as const]).map((field) => [field, RANGE[field]])));
      return;
    }
    setFormError(authMessage("unavailable"));
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const gpaParsed = parseGpa(gpa);
    const daysParsed = unknown ? { value: 0 } : parseDays(days);
    const found: Errors = {
      gpa: "error" in gpaParsed ? gpaParsed.error : undefined,
      days: "error" in daysParsed ? daysParsed.error : undefined,
    };
    setErrors(found);
    setFormError(undefined);
    if ("error" in gpaParsed || "error" in daysParsed) return;

    setBusy("save");
    // Built field by field: "Không nhớ" sends no day count (a disabled input is not in FormData).
    const body = unknown
      ? { gpa_before: gpaParsed.value, prior_days_unknown: true }
      : { gpa_before: gpaParsed.value, prior_ready_days: daysParsed.value, prior_days_unknown: false };
    follow(await postJson<{ next: string }>("/api/baseline", body));
  }

  // US-11 AC2: a POST, so core-api counts the skip and asks once more on a later visit.
  async function later() {
    setBusy("skip");
    setFormError(undefined);
    follow(await postJson<{ next: string }>("/api/baseline/skip"));
  }

  return (
    <form method="post" onSubmit={save} className="mt-8 flex flex-col gap-6" noValidate>
      <AuthField
        id="gpa"
        name="gpa"
        label="GPA hiện tại (thang 4)"
        inputMode="decimal"
        autoComplete="off"
        value={gpa}
        onChange={(event) => setGpa(event.target.value)}
        invalid={errors.gpa !== undefined}
        describedBy={errors.gpa ? "gpa-error" : undefined}
        className="max-w-50"
      >
        {errors.gpa && <FieldError id="gpa-error">{BASELINE_MESSAGES[errors.gpa]}</FieldError>}
      </AuthField>

      <div className="flex flex-col gap-1.5">
        <AuthField
          id="days"
          name="days"
          label="Kỳ trước, bạn học xong bao nhiêu ngày trước khi thi?"
          inputMode="numeric"
          autoComplete="off"
          value={unknown ? "0" : days}
          disabled={unknown}
          onChange={(event) => setDays(event.target.value)}
          invalid={errors.days !== undefined}
          describedBy={errors.days ? "days-error" : undefined}
          className="max-w-50"
        >
          {errors.days && <FieldError id="days-error">{BASELINE_MESSAGES[errors.days]}</FieldError>}
        </AuthField>
        <label className="inline-flex min-h-11 w-fit cursor-pointer items-center gap-3 text-body">
          <input
            type="checkbox"
            name="unknown"
            checked={unknown}
            onChange={(event) => {
              setUnknown(event.target.checked);
              if (event.target.checked) setErrors(({ gpa: gpaError }) => ({ gpa: gpaError }));
            }}
            className="size-5 accent-hong"
          />
          Không nhớ
        </label>
      </div>

      {formError && <FieldError id="baseline-error">{formError}</FieldError>}

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-4">
          {/* One request at a time: each button waits on its own, the other is off meanwhile. */}
          <Button type="submit" pending={busy === "save"} disabled={skipping}>
            {busy === "save" ? "Đang lưu…" : "Lưu và tiếp tục"}
          </Button>
          <Button type="button" variant="quiet" onClick={later} pending={skipping} disabled={busy === "save"}>
            Nhập sau
          </Button>
        </div>
        <p className="m-0 text-small text-ink-soft">Sau 7 ngày, mốc này sẽ không sửa được nữa.</p>
      </div>
    </form>
  );
}
