"use client";

import { type FormEvent, useEffect, useState } from "react";

import { AuthNote, PasswordField } from "@/components/auth/fields";
import { FieldError, FieldHint } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { authMessage, PASSWORD_REASONS, postJson, rateLimitMessage } from "@/lib/auth-errors";
import { consumeLinkToken } from "@/lib/link-token";
import { afterReset, type ResetState } from "@/lib/reset-state";

/** A ✓ before "Đã đặt mật khẩu mới." */
function Check() {
  return (
    <svg width="20" height="20" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0 text-correct">
      <path
        d="m3 8.5 3.25 3L13 4.75"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

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
      <div aria-busy="true" className="h-40 rounded-control bg-sunken" />
    );
  }
  if (state.view === "done") {
    return (
      <div className="flex flex-col gap-4" role="status">
        <p className="m-0 flex items-center gap-2 font-semibold">
          <Check />
          Đã đặt mật khẩu mới.
        </p>
        <p className="m-0 text-ink-soft">Đăng nhập bằng mật khẩu mới.</p>
        <Button render={<a href="/login" />} nativeButton={false} className="w-full">
          Đăng nhập
        </Button>
      </div>
    );
  }
  if (state.view === "expired") {
    return (
      <div className="flex flex-col gap-4">
        <p className="m-0 font-semibold">Link này đã hết hạn hoặc đã được dùng.</p>
        <p className="m-0 text-ink-soft">Mỗi link chỉ dùng được một lần. Gửi link mới tới email của bạn.</p>
        <Button
          render={<a href="/forgot-password" />}
          nativeButton={false}
          variant="secondary"
          className="w-full"
        >
          Gửi link mới
        </Button>
      </div>
    );
  }
  const { token, error, retryAfter } = state;
  const passwordError = error !== undefined && (PASSWORD_REASONS.has(error) || error === "invalid_password");
  return (
    <form onSubmit={(event) => submit(event, token)} className="flex flex-col gap-5" noValidate>
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
