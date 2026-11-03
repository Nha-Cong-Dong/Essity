"use client";

import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { AUTH_LINK, AuthField, AuthNote, PasswordField } from "@/components/auth/fields";
import { GoogleSection } from "@/components/auth/google-button";
import { FieldError, FieldHint } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { authMessage, PASSWORD_REASONS, postJson, rateLimitMessage } from "@/lib/auth-errors";
import { safeNext } from "@/lib/landing";
import { go } from "@/lib/navigate";
import { emailProblem, normalizeUsername, USERNAME_MAX, usernameProblem } from "@/lib/username";

// T1.13, T1.24 (AC1, AC5, AC6): username, email, password, then "Họ và tên" (optional, last;
// D7, D8). No phone (D4). Rules are told per field on blur, once there is text; the server still
// has the last word, and a 409 says "Tên này đã có người dùng." (D2). The password rules live in
// core-api; this only shows its reason.
type Field = "username" | "email" | "password" | "name";

const USERNAME_HINT = "3–20 ký tự: chữ thường không dấu, số, _ và .";
const PASSWORD_HINT = "Ít nhất 8 ký tự";

/** The field a server error code belongs to; anything else is a general error under the form. */
function fieldOf(code: string | undefined): Field | undefined {
  if (code === undefined) return undefined;
  if (code.startsWith("username_")) return "username";
  if (code === "invalid_email") return "email";
  if (PASSWORD_REASONS.has(code) || code === "invalid_password") return "password";
  if (code === "display_name_invalid") return "name";
  return undefined;
}

type Availability = { available: boolean; reason: string | null };

/** Asks web's own route; null on any failure (the caller treats it as "no answer"). */
async function getAvailability(username: string): Promise<Availability | null> {
  try {
    const response = await fetch(`/api/auth/username-available?username=${encodeURIComponent(username)}`);
    if (!response.ok) return null;
    const body = (await response.json()) as { available?: unknown; reason?: unknown };
    if (typeof body.available !== "boolean") return null;
    return { available: body.available, reason: typeof body.reason === "string" ? body.reason : null };
  } catch {
    return null;
  }
}

/** A field with the hint under it, which an error replaces. */
function Hinted({ id, hint, error, children }: { id: string; hint: string; error?: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-1.5">
      {children}
      {error ? <FieldError id={`${id}-error`}>{error}</FieldError> : <FieldHint id={`${id}-hint`}>{hint}</FieldHint>}
    </div>
  );
}

export function RegisterForm() {
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState("");
  const [serverError, setServerError] = useState<string>();
  const [retryAfter, setRetryAfter] = useState<number>();
  const [problems, setProblems] = useState<Partial<Record<Field, string>>>({});
  const latestName = useRef("");
  const formRef = useRef<HTMLFormElement>(null);
  const [failed, setFailed] = useState(0);

  // After a refused sign-up focus goes to the first field in error: a screen reader then reads that
  // field and, through aria-describedby, its sentence (a server error is not a live region).
  useEffect(() => {
    if (failed > 0) formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }, [failed]);

  const setProblem = (field: Field, message: string | undefined) =>
    setProblems((now) => ({ ...now, [field]: message }));
  const clear = (field: Field) => {
    setProblem(field, undefined);
    if (fieldOf(serverError) === field) setServerError(undefined);
  };

  async function checkUsername(value: string) {
    latestName.current = value;
    if (value === "") return clear("username");
    const rule = usernameProblem(value);
    if (rule) return setProblem("username", rule);
    // Only a well-formed name is asked about. A failed or slow check says nothing: the sign-up
    // itself answers 409 if the name was taken after all.
    const result = await getAvailability(value);
    if (latestName.current !== value || !result || result.available) return;
    const code = { reserved: "username_reserved", invalid: "username_invalid" }[result.reason ?? ""] ?? "username_taken";
    setProblem("username", authMessage(code));
  }

  function checkEmail(value: string) {
    setProblem("email", value.trim() === "" ? undefined : (emailProblem(value.trim()) ?? undefined));
  }

  function checkPassword(value: string) {
    setProblem("password", value === "" || value.length >= 8 ? undefined : authMessage("too_short"));
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setServerError(undefined);
    setProblems({});
    const name = String(form.get("name")).trim();
    const result = await postJson<{ next: string }>("/api/auth/register", {
      username: normalizeUsername(String(form.get("username")).trim()),
      email: String(form.get("email")).trim(),
      password: String(form.get("password")),
      ...(name ? { display_name: name } : {}),
    });
    if (result.data) {
      // Review plan R3: only the page the flow knows, never whatever `next` came back.
      go(safeNext(result.data.next, ["/check-email"], "/check-email"));
      return;
    }
    setBusy(false);
    setServerError(result.error);
    setRetryAfter(result.retryAfter);
    setFailed((n) => n + 1);
  }

  const serverField = fieldOf(serverError);
  const message = (field: Field): string | undefined =>
    problems[field] ?? (serverField === field ? authMessage(serverError) : undefined);
  const generalError = serverError !== undefined && serverField === undefined && serverError !== "rate_limited";
  const describe = (field: Field, id: string) => (message(field) ? `${id}-error` : `${id}-hint`);
  return (
    <>
      <GoogleSection label="Đăng ký bằng Google" />
      <form ref={formRef} method="post" onSubmit={submit} className="flex flex-col gap-5" noValidate aria-busy={busy || undefined}>
        {serverError === "rate_limited" && <AuthNote>{rateLimitMessage(retryAfter)}</AuthNote>}
        {generalError && <AuthNote id="register-error">{authMessage(serverError)}</AuthNote>}
        <Hinted id="username" hint={USERNAME_HINT} error={message("username")}>
          <AuthField
            id="username"
            name="username"
            label="Tên đăng nhập"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            autoCorrect="off"
            spellCheck={false}
            placeholder="an.nguyen"
            maxLength={USERNAME_MAX}
            required
            readOnly={busy}
            value={username}
            onChange={(event) => {
              setUsername(normalizeUsername(event.target.value));
              clear("username");
            }}
            onBlur={(event) => void checkUsername(normalizeUsername(event.target.value.trim()))}
            invalid={message("username") !== undefined}
            describedBy={describe("username", "username")}
          />
        </Hinted>
        <Hinted id="email" hint="Để xác nhận tài khoản và lấy lại mật khẩu" error={message("email")}>
          <AuthField
            id="email"
            name="email"
            label="Email"
            type="email"
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            inputMode="email"
            placeholder="an@gmail.com"
            required
            readOnly={busy}
            onChange={() => clear("email")}
            onBlur={(event) => checkEmail(event.target.value)}
            invalid={message("email") !== undefined}
            describedBy={describe("email", "email")}
          />
        </Hinted>
        <Hinted id="password" hint={PASSWORD_HINT} error={message("password")}>
          <PasswordField
            id="password"
            name="password"
            label="Mật khẩu"
            autoComplete="new-password"
            required
            readOnly={busy}
            onChange={() => clear("password")}
            onBlur={(event) => checkPassword(event.target.value)}
            invalid={message("password") !== undefined}
            describedBy={describe("password", "password")}
          />
        </Hinted>
        <fieldset className="m-0 min-w-0 border-0 border-t border-line p-0 pt-5">
          <legend className="sr-only">Thông tin thêm</legend>
          <Hinted
            id="name"
            hint="Essity gọi bạn bằng tên này. Bỏ trống thì dùng tên đăng nhập."
            error={message("name")}
          >
            <AuthField
              id="name"
              name="name"
              label="Họ và tên (không bắt buộc)"
              type="text"
              autoComplete="name"
              placeholder="Nguyễn Văn An"
              maxLength={60}
              readOnly={busy}
              onChange={() => clear("name")}
              invalid={message("name") !== undefined}
              describedBy={describe("name", "name")}
            />
          </Hinted>
        </fieldset>
        <Button type="submit" pending={busy} className="w-full">
          {busy ? "Đang tạo tài khoản…" : "Tạo tài khoản"}
        </Button>
        <p className="m-0 text-center text-body">
          Đã có tài khoản?{" "}
          <a href="/login" className={`${AUTH_LINK} inline-flex min-h-11 items-center px-1.5`}>
            Đăng nhập
          </a>
        </p>
      </form>
    </>
  );
}
