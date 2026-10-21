"use client";

import { type FormEvent, useState } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { AUTH_LINK, AuthField, AuthNote } from "@/components/auth/fields";
import { FieldError } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { FORGOT_PASSWORD_SENT } from "@/lib/auth-copy";
import { authMessage, postJson, rateLimitMessage } from "@/lib/auth-errors";
import { maskEmail } from "@/lib/mask-email";

// T1.14, canvas Auth "forgot" then "check". The answer is the same for every address (AC5),
// so the page always moves on to "check your email".
export function ForgotPassword() {
  const [sentTo, setSentTo] = useState<string>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ code: string; retryAfter?: number }>();

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const email = String(new FormData(event.currentTarget).get("email")).trim();
    setBusy(true);
    setError(undefined);
    const result = await postJson("/api/auth/password-reset", { email });
    setBusy(false);
    if (result.data) setSentTo(email);
    else setError({ code: result.error ?? "unavailable", retryAfter: result.retryAfter });
  }

  if (sentTo !== undefined) {
    return (
      <AuthCard title={FORGOT_PASSWORD_SENT.title}>
        <p className="m-0 text-body">
          {FORGOT_PASSWORD_SENT.sentTo}{" "}
          <span className="font-hand text-hand text-hong">{maskEmail(sentTo)}</span>
        </p>
        <p className="m-0 text-ink-soft">{FORGOT_PASSWORD_SENT.body}</p>
        <a href="/login" className={AUTH_LINK}>
          Quay lại đăng nhập
        </a>
      </AuthCard>
    );
  }
  return (
    <AuthCard title="Quên mật khẩu">
      <form onSubmit={submit} className="flex flex-col gap-5" noValidate>
        {error?.code === "rate_limited" && <AuthNote>{rateLimitMessage(error.retryAfter)}</AuthNote>}
        <p className="m-0">Nhập email bạn dùng để đăng ký. App sẽ gửi link đặt lại mật khẩu.</p>
        <AuthField id="email" name="email" label="Email" type="email" autoComplete="email" required />
        {error && error.code !== "rate_limited" && (
          <FieldError id="forgot-error">{authMessage(error.code)}</FieldError>
        )}
        <Button type="submit" disabled={busy} className="h-14 w-full">
          Gửi link đặt lại
        </Button>
        <a href="/login" className={AUTH_LINK}>
          Quay lại đăng nhập
        </a>
      </form>
    </AuthCard>
  );
}
