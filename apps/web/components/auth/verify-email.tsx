"use client";

import { type MouseEvent, useEffect, useRef, useState } from "react";

import { AuthBody, AuthState } from "@/components/auth/auth-state";
import { Button } from "@/components/ui/button";
import { type AuthResult, postJson } from "@/lib/auth-errors";
import { clearAllDrafts } from "@/lib/draft";
import { NEXT_PAGES, safeNext } from "@/lib/landing";
import { consumeLinkToken, postOnce } from "@/lib/link-token";
import { go } from "@/lib/navigate";

type VerifyResult = { verified: true; signedIn: boolean; next?: string };
type State =
  | { view: "checking" }
  | { view: "ok"; signedIn: boolean; next?: string }
  | { view: "expired"; signedIn: boolean }
  | { view: "failed"; token: string };

function show(token: string, result: AuthResult<VerifyResult>): State {
  if (result.data) return { view: "ok", signedIn: result.data.signedIn, next: result.data.next };
  if (result.status === 400) return { view: "expired", signedIn: result.body?.signedIn === true };
  return { view: "failed", token }; // the token stays in memory for "Thử lại"
}

/** The person asked for less motion: the page then waits for the button (plan E5). */
function prefersLessMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
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

  // F4, AC11: signed in, the app goes on by itself to the one page the button names (plan E5),
  // unless the person asked for less motion; then the button alone moves on.
  const dest = state.view === "ok" ? safeNext(state.next, NEXT_PAGES) : "/today";
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  // This device now belongs to the person who signed in: answers left by the last one go.
  const signedIn = state.view === "ok" && state.signedIn;
  useEffect(() => {
    if (signedIn) clearAllDrafts();
  }, [signedIn]);
  useEffect(() => {
    if (state.view !== "ok" || !state.signedIn) return;
    if (prefersLessMotion()) return;
    timer.current = setTimeout(() => go(dest), 1500);
    return () => clearTimeout(timer.current);
  }, [state, dest]);

  // The anchor would load the page while the timer still runs: go once, from here. A click that
  // opens a new tab (a modifier key) stays the browser's, and this tab still goes on by itself.
  function goNow(event: MouseEvent) {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    clearTimeout(timer.current);
    go(dest);
  }

  if (state.view === "checking") {
    return (
      <div className="flex flex-col gap-4" aria-busy="true">
        <p className="m-0 font-display text-lead font-semibold">Đang kiểm tra link…</p>
        <div className="h-5 w-3/4 rounded-full bg-sunken" />
        <div className="h-13 rounded-full bg-sunken" />
      </div>
    );
  }
  if (state.view === "ok") {
    return (
      <AuthState
        mark="ok"
        role="status"
        title="Đã xác minh email."
        actions={
          state.signedIn ? (
            dest === "/subjects/new" ? (
              <Button render={<a href="/subjects/new" />} nativeButton={false} onClick={goNow} className="w-full">
                Tạo môn đầu tiên
              </Button>
            ) : (
              <Button render={<a href="/today" />} nativeButton={false} onClick={goNow} className="w-full">
                Vào hôm nay
              </Button>
            )
          ) : (
            <Button render={<a href="/login" />} nativeButton={false} className="w-full">
              Đăng nhập
            </Button>
          )
        }
      >
        {/* "ok" exists only after the effect, so reading matchMedia here cannot split hydration. */}
        {state.signedIn && !prefersLessMotion() && <AuthBody>Đang chuyển tiếp…</AuthBody>}
      </AuthState>
    );
  }
  if (state.view === "expired") {
    // F5: a new link needs an address: the session's (/check-email), or sign in first.
    return (
      <AuthState
        mark="expired"
        title="Link này đã hết hạn hoặc đã được dùng."
        actions={
          <Button
            render={<a href={state.signedIn ? "/check-email" : "/login"} />}
            nativeButton={false}
            variant="secondary"
            className="w-full"
          >
            Gửi link mới
          </Button>
        }
      >
        <AuthBody>Mỗi link chỉ dùng được một lần. Gửi link mới tới email của bạn.</AuthBody>
      </AuthState>
    );
  }
  return (
    <AuthState
      mark="warn"
      title="Chưa kiểm tra được link."
      actions={
        <Button variant="secondary" onClick={() => retry(state.token)} className="w-full">
          Thử lại
        </Button>
      }
    >
      <AuthBody>Kiểm tra kết nối rồi thử lại.</AuthBody>
    </AuthState>
  );
}
