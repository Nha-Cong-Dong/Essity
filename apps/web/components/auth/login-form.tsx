"use client";

import { type FormEvent, useEffect, useState } from "react";

import { AUTH_LINK, AuthField, AuthNote, PasswordField } from "@/components/auth/fields";
import { FieldError } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { authMessage, postJson, rateLimitMessage } from "@/lib/auth-errors";
import { safeNext } from "@/lib/landing";
import { go } from "@/lib/navigate";

// T1.12, canvas Auth "login". The session token stays in an HttpOnly cookie set by
// /api/auth/login; this form only learns where to go next.
const SIGN_IN_PAGES = ["/", "/check-email"];

export function LoginForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [lockedFor, setLockedFor] = useState(0);

  // AC6: after a 429 the button stays locked until Retry-After has passed.
  useEffect(() => {
    if (lockedFor <= 0) return;
    const timer = setTimeout(() => setLockedFor(0), lockedFor * 1000);
    return () => clearTimeout(timer);
  }, [lockedFor]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    const result = await postJson<{ next: string }>("/api/auth/login", {
      email: String(form.get("email")),
      password: String(form.get("password")),
    });
    if (result.data) {
      // A full load, so every server component reads the new session. Only the pages
      // /api/auth/login names are followed (review 266042d #3).
      go(safeNext(result.data.next, SIGN_IN_PAGES, "/"));
      return;
    }
    setBusy(false);
    setError(result.error);
    if (result.error === "rate_limited") setLockedFor(result.retryAfter ?? 15 * 60);
  }

  const rateLimited = error === "rate_limited" && lockedFor > 0;
  const wrong = error === "invalid_credentials";
  return (
    <form method="post" onSubmit={submit} className="flex flex-col gap-5" noValidate>
      {rateLimited && <AuthNote>{rateLimitMessage(lockedFor)}</AuthNote>}
      <AuthField
        id="email"
        name="email"
        label="Email"
        type="email"
        autoComplete="email"
        required
        invalid={wrong}
        describedBy={wrong ? "login-error" : undefined}
      />
      <PasswordField
        id="password"
        name="password"
        label="Mật khẩu"
        autoComplete="current-password"
        required
        invalid={wrong}
        describedBy={wrong ? "login-error" : undefined}
      />
      {error && !rateLimited && <FieldError id="login-error">{authMessage(error)}</FieldError>}
      <Button type="submit" pending={busy} disabled={rateLimited} className="w-full">
        {busy ? "Đang đăng nhập…" : "Đăng nhập"}
      </Button>
      <div className="flex flex-col gap-2.5 text-body">
        <a href="/forgot-password" className={AUTH_LINK}>
          Quên mật khẩu?
        </a>
        <span>
          Chưa có tài khoản?{" "}
          <a href="/register" className={AUTH_LINK}>
            Đăng ký
          </a>
        </span>
      </div>
    </form>
  );
}
