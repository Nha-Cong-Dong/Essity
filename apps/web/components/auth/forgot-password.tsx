"use client";

import { type FormEvent, useState } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { AuthBody, AuthState } from "@/components/auth/auth-state";
import { AUTH_PILL, AuthField, AuthNote } from "@/components/auth/fields";
import { FieldError } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { FORGOT_PASSWORD_SENT } from "@/lib/auth-copy";
import { authMessage, postJson, rateLimitMessage } from "@/lib/auth-errors";
import { maskEmail } from "@/lib/mask-email";

const GREETING = (
  <>
    <span>Quên cũng</span> <span>không sao</span>
  </>
);

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
      <AuthLayout title={FORGOT_PASSWORD_SENT.title} greeting={GREETING} bubble="Thư đã bay đi">
        <AuthState
          mark="mail"
          role="status"
          title={
            <>
              {FORGOT_PASSWORD_SENT.sentTo}{" "}
              <span className="text-hong-text">{maskEmail(sentTo)}</span>
            </>
          }
          actions={
            <a href="/login" className={AUTH_PILL}>
              Quay lại đăng nhập
            </a>
          }
        >
          <AuthBody>{FORGOT_PASSWORD_SENT.body}</AuthBody>
        </AuthState>
      </AuthLayout>
    );
  }
  return (
    <AuthLayout title="Quên mật khẩu" greeting={GREETING} bubble="Mình giúp bạn">
      <form method="post" onSubmit={submit} className="flex flex-col gap-5" noValidate>
        {error?.code === "rate_limited" && <AuthNote>{rateLimitMessage(error.retryAfter)}</AuthNote>}
        <p className="m-0 text-ink-soft">Nhập email bạn dùng để đăng ký. App sẽ gửi link đặt lại mật khẩu.</p>
        <AuthField id="email" name="email" label="Email" type="email" autoComplete="email" required />
        {error && error.code !== "rate_limited" && (
          <FieldError id="forgot-error">{authMessage(error.code)}</FieldError>
        )}
        <Button type="submit" pending={busy} className="w-full">
          Gửi link đặt lại
        </Button>
        <a href="/login" className={AUTH_PILL}>
          Quay lại đăng nhập
        </a>
      </form>
    </AuthLayout>
  );
}
