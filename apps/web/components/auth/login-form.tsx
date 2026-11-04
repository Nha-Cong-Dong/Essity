"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

import { AUTH_LINK, AUTH_PILL, AuthField, AuthNote, PasswordField } from "@/components/auth/fields";
import { GoogleSection } from "@/components/auth/google-button";
import { Button } from "@/components/ui/button";
import { authMessage, postJson, rateLimitMessage } from "@/lib/auth-errors";
import { clearAllDrafts } from "@/lib/draft";
import { safeNext } from "@/lib/landing";
import { go } from "@/lib/navigate";

// T1.12, T1.24 (AC5, AC6): one field takes a username or an email (D3). The session token stays
// in an HttpOnly cookie set by /api/auth/login; this form only learns where to go next.
const SIGN_IN_PAGES = ["/", "/check-email"];

export function LoginForm() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();
  const [lockedFor, setLockedFor] = useState(0);
  const formRef = useRef<HTMLFormElement>(null);
  const [failed, setFailed] = useState(0);

  // After a refused sign-in focus goes to the first field marked invalid, which reads the error.
  useEffect(() => {
    if (failed > 0) formRef.current?.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus();
  }, [failed]);

  // AC6: after a 429 the button stays locked until Retry-After has passed.
  useEffect(() => {
    if (lockedFor <= 0) return;
    const timer = setTimeout(() => setLockedFor(0), lockedFor * 1000);
    return () => clearTimeout(timer);
  }, [lockedFor]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(undefined);
    const result = await postJson<{ next: string }>("/api/auth/login", {
      identifier: String(form.get("identifier")).trim(),
      password: String(form.get("password")),
    });
    if (result.data) {
      clearAllDrafts(); // answers a previous person left here (T2.15 review 🟡7)
      // A full load, so every server component reads the new session. Only the pages
      // /api/auth/login names are followed (review 266042d #3).
      go(safeNext(result.data.next, SIGN_IN_PAGES, "/"));
      return;
    }
    setBusy(false);
    setError(result.error);
    setFailed((n) => n + 1);
    if (result.error === "rate_limited") setLockedFor(result.retryAfter ?? 15 * 60);
  }

  const rateLimited = error === "rate_limited" && lockedFor > 0;
  const wrong = error === "invalid_credentials";
  return (
    <>
      <GoogleSection label="Đăng nhập bằng Google" />
      <form
        ref={formRef}
        method="post"
        onSubmit={submit}
        className="flex flex-col gap-5"
        noValidate
        aria-busy={busy || undefined}
      >
        {rateLimited && <AuthNote>{rateLimitMessage(lockedFor)}</AuthNote>}
        {error && !rateLimited && (
          <AuthNote id="login-error">{authMessage(error)}</AuthNote>
        )}
        <AuthField
          id="identifier"
          name="identifier"
          label="Tên đăng nhập hoặc email"
          type="text"
          autoComplete="username"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          placeholder="an.nguyen hoặc an@gmail.com"
          required
          readOnly={busy}
          invalid={wrong}
          describedBy={wrong ? "login-error" : undefined}
        />
        <div className="flex flex-col gap-1">
          <PasswordField
            id="password"
            name="password"
            label="Mật khẩu"
            autoComplete="current-password"
            required
            readOnly={busy}
            invalid={wrong}
            describedBy={wrong ? "login-error" : undefined}
          />
          <a href="/forgot-password" className={`${AUTH_PILL} self-end`}>
            Quên mật khẩu?
          </a>
        </div>
        <Button type="submit" pending={busy} disabled={rateLimited} className="w-full">
          {busy ? "Đang đăng nhập…" : "Đăng nhập"}
        </Button>
        <p className="m-0 text-center text-body">
          Chưa có tài khoản?{" "}
          <a href="/register" className={`${AUTH_LINK} inline-flex min-h-11 items-center px-1.5`}>
            Đăng ký
          </a>
        </p>
      </form>
    </>
  );
}
