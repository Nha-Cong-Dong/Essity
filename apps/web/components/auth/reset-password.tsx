"use client";

import { type FormEvent, useEffect, useState } from "react";

import { AuthNote, PasswordField } from "@/components/auth/fields";
import { AuthBody, AuthState } from "@/components/auth/auth-state";
import { FieldError, FieldHint } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { authMessage, PASSWORD_REASONS, postJson, rateLimitMessage } from "@/lib/auth-errors";
import { consumeLinkToken } from "@/lib/link-token";
import { afterReset, type ResetState } from "@/lib/reset-state";

/**
 * T1.14, canvas Auth "reset". The token leaves the URL at once (F8) and stays in memory until
 * the new password is sent: a refused password keeps the form and the link (F6); only an
 * expired or used link shows "expired". No sign-in afterwards: every session has ended.
 */
export function ResetPassword() {
  const [state, setState] = useState<ResetState>({ view: "loading" });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const token = consumeLinkToken(window);
    queueMicrotask(() => setState(token ? { view: "form", token } : { view: "expired" }));
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>, token: string) {
    event.preventDefault();
    const password = String(new FormData(event.currentTarget).get("password"));
    setBusy(true);
    const result = await postJson("/api/auth/password-reset/confirm", { token, password });
    setBusy(false);
    setState(afterReset(token, result));
  }

  if (state.view === "loading") {
    return (
      <div aria-busy="true" className="flex flex-col gap-4">
        <div className="h-5 w-1/3 rounded-full bg-sunken" />
        <div className="h-13 rounded-control bg-sunken" />
        <div className="h-13 rounded-full bg-sunken" />
      </div>
    );
  }
  if (state.view === "done") {
    return (
      <AuthState
        mark="ok"
        role="status"
        title="Đã đặt mật khẩu mới."
        actions={
          <Button render={<a href="/login" />} nativeButton={false} className="w-full">
            Đăng nhập
          </Button>
        }
      >
        <AuthBody>Đăng nhập bằng mật khẩu mới.</AuthBody>
      </AuthState>
    );
  }
  if (state.view === "expired") {
    return (
      <AuthState
        mark="expired"
        title="Link này đã hết hạn hoặc đã được dùng."
        actions={
          <Button render={<a href="/forgot-password" />} nativeButton={false} variant="secondary" className="w-full">
            Gửi link mới
          </Button>
        }
      >
        <AuthBody>Mỗi link chỉ dùng được một lần. Gửi link mới tới email của bạn.</AuthBody>
      </AuthState>
    );
  }
  const { token, error, retryAfter } = state;
  const passwordError = error !== undefined && (PASSWORD_REASONS.has(error) || error === "invalid_password");
  return (
    <form method="post" onSubmit={(event) => submit(event, token)} className="flex flex-col gap-5" noValidate>
      {error === "rate_limited" && <AuthNote>{rateLimitMessage(retryAfter)}</AuthNote>}
      <PasswordField
        id="password"
        name="password"
        label="Mật khẩu mới"
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
      {error && !passwordError && error !== "rate_limited" && (
        <FieldError id="reset-error">{authMessage(error)}</FieldError>
      )}
      <Button type="submit" pending={busy} className="w-full">
        Lưu mật khẩu
      </Button>
    </form>
  );
}
