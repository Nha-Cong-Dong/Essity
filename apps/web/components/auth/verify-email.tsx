"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { type AuthResult, postJson } from "@/lib/auth-errors";
import { consumeLinkToken, postOnce } from "@/lib/link-token";

type VerifyResult = { verified: true; signedIn: boolean };
type State =
  | { view: "checking" }
  | { view: "ok"; signedIn: boolean }
  | { view: "expired"; signedIn: boolean }
  | { view: "failed"; token: string };

/** A ✓ before "Đã xác minh email." */
function Check() {
  return (
    <svg width="20" height="20" viewBox="0 0 16 16" aria-hidden="true" className="shrink-0 text-correct">
      <path d="m3 8.5 3.25 3L13 4.75" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function show(token: string, result: AuthResult<VerifyResult>): State {
  if (result.data) return { view: "ok", signedIn: result.data.signedIn };
  if (result.status === 400) return { view: "expired", signedIn: result.body?.signedIn === true };
  return { view: "failed", token }; // the token stays in memory for "Thử lại"
}

function verify(token: string) {
  return postJson<VerifyResult>("/api/auth/verify-email", { token });
}

/**
 * T1.13, canvas Auth "checking / ok / expired". The token is read once, removed from the URL,
 * and POSTed once (F8); the server never spends it while rendering, so a mail scanner's GET
 * leaves the link working.
 */
export function VerifyEmail() {
  const [state, setState] = useState<State>({ view: "checking" });

  useEffect(() => {
    const token = consumeLinkToken(window);
    if (token === null) {
      // No token, or a reload after it was removed: the link cannot be used again.
      queueMicrotask(() => setState({ view: "expired", signedIn: false }));
      return;
    }
    postOnce(token, () => verify(token)).then((result) => setState(show(token, result)));
  }, []);

  async function retry(token: string) {
    setState({ view: "checking" });
    setState(show(token, await verify(token)));
  }

  // F4: signed in, the app goes on by itself.
  useEffect(() => {
    if (state.view !== "ok" || !state.signedIn) return;
    // A full load, so every server component reads the now verified session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    const timer = setTimeout(() => window.location.assign("/onboarding"), 1500);
    return () => clearTimeout(timer);
  }, [state]);

  if (state.view === "checking") {
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <p className="m-0">Đang kiểm tra link…</p>
        <div className="h-5 w-3/4 rounded-sm bg-[color-mix(in_srgb,var(--line)_80%,transparent)]" />
        <div className="h-14 rounded-sm bg-[color-mix(in_srgb,var(--line)_80%,transparent)]" />
      </div>
    );
  }
  if (state.view === "ok") {
    return (
      <div className="flex flex-col gap-4" role="status">
        <p className="m-0 flex items-center gap-2 font-semibold">
          <Check />
          Đã xác minh email.
        </p>
        {state.signedIn ? (
          <>
            <p className="m-0 text-ink-soft">Đang chuyển tiếp…</p>
            <Button render={<a href="/onboarding" />} nativeButton={false} className="h-14 w-full">
              Ghi điểm xuất phát
            </Button>
          </>
        ) : (
          <Button render={<a href="/login" />} nativeButton={false} className="h-14 w-full">
            Đăng nhập
          </Button>
        )}
      </div>
    );
  }
  if (state.view === "expired") {
    // F5: a new link needs an address: the session's (/check-email), or sign in first.
    return (
      <div className="flex flex-col gap-4">
        <p className="m-0 font-semibold">Link này đã hết hạn hoặc đã được dùng.</p>
        <p className="m-0 text-ink-soft">Mỗi link chỉ dùng được một lần. Gửi link mới tới email của bạn.</p>
        <Button
          render={<a href={state.signedIn ? "/check-email" : "/login"} />}
          nativeButton={false}
          variant="secondary"
          className="h-14 w-full"
        >
          Gửi link mới
        </Button>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-4">
      <p className="m-0">Chưa kiểm tra được link. Kiểm tra kết nối rồi thử lại.</p>
      <Button variant="secondary" onClick={() => retry(state.token)} className="h-14 w-full">
        Thử lại
      </Button>
    </div>
  );
}
