"use client";

import { type FormEvent, useState } from "react";

import { AUTH_LINK, AuthField, AuthNote, PasswordField } from "@/components/auth/fields";
import { FieldError, FieldHint } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { authMessage, PASSWORD_REASONS, postJson, rateLimitMessage } from "@/lib/auth-errors";

// T1.13, canvas Auth "register": exactly two fields (AC1), a show/hide button instead of
// "type it again". The password rules live in core-api; this only shows its reason.
export function RegisterForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [retryAfter, setRetryAfter] = useState<number>();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    const result = await postJson<{ next: string }>("/api/auth/register", {
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
    if (result.data) {
      window.location.assign(result.data.next);
      return;
    }
    setBusy(false);
    setError(result.error);
    setRetryAfter(result.retryAfter);
  }

  const passwordError = error !== undefined && (PASSWORD_REASONS.has(error) || error === "invalid_password");
  const emailError = error === "invalid_email";
  const otherError = error !== undefined && !passwordError && !emailError;
  return (
    <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
      {error === "rate_limited" && <AuthNote>{rateLimitMessage(retryAfter)}</AuthNote>}
      <AuthField
        id="email"
        name="email"
        label="Email"
        type="email"
        autoComplete="email"
        required
        invalid={emailError}
        describedBy={emailError ? "email-error" : undefined}
      >
        {emailError && <FieldError id="email-error">{authMessage(error)}</FieldError>}
      </AuthField>
      <PasswordField
        id="password"
        name="password"
        label="Mật khẩu"
        autoComplete="new-password"
        required
        invalid={passwordError}
        describedBy={passwordError ? "password-error" : "password-hint"}
      >
        {passwordError ? (
          <FieldError id="password-error">{authMessage(error)}</FieldError>
        ) : (
          <FieldHint id="password-hint">Ít nhất 8 ký tự. Không cần ký tự đặc biệt.</FieldHint>
        )}
      </PasswordField>
      {otherError && error !== "rate_limited" && (
        <FieldError id="register-error">{authMessage(error)}</FieldError>
      )}
      <Button type="submit" pending={busy} className="w-full">
        Đăng ký
      </Button>
      <p className="m-0 text-body">
        Đã có tài khoản?{" "}
        <a href="/login" className={AUTH_LINK}>
          Đăng nhập
        </a>
      </p>
    </form>
  );
}
