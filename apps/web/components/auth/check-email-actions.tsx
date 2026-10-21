"use client";

import { useEffect, useState } from "react";

import { AUTH_LINK } from "@/components/auth/fields";
import { FieldError } from "@/components/field-error";
import { Button } from "@/components/ui/button";
import { authMessage, postJson, resendWait } from "@/lib/auth-errors";
import { signOut } from "@/lib/sign-out";

function clock(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

/**
 * "Gửi lại" with its countdown on the button ("Gửi lại (0:42)"), then "Đã gửi lại." (DESIGN.md
 * §6.1). The countdown only mirrors core-api's 60 seconds (F3): right after sign-up it starts
 * full, after signing in to an unverified account it starts at 0.
 */
export function CheckEmailActions({ initialWait }: { initialWait: number }) {
  const [left, setLeft] = useState(initialWait);
  const [resent, setResent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string>();

  useEffect(() => {
    if (left <= 0) return;
    const timer = setTimeout(() => setLeft(left - 1), 1000);
    return () => clearTimeout(timer);
  }, [left]);

  async function resend() {
    setBusy(true);
    setError(undefined);
    const result = await postJson("/api/auth/resend");
    setBusy(false);
    setLeft(resendWait(result));
    setResent(result.data !== undefined);
    // 429 is not an error here: the countdown says when to try again.
    if (!result.data && result.status !== 429) {
      // The sign-up cookie expired: start again. A full load, as after every account change.
      // eslint-disable-next-line @next/next/no-location-assign-relative-destination
      if (result.error === "no_email") window.location.assign("/register");
      else setError(result.error);
    }
  }

  async function wrongEmail() {
    if (!(await signOut({ then: "/register" }))) setError("unavailable");
  }

  return (
    <div className="flex flex-col gap-4">
      <Button variant="secondary" onClick={resend} disabled={busy || left > 0} className="h-14 w-full">
        {left > 0 ? `Gửi lại (${clock(left)})` : "Gửi lại"}
      </Button>
      <p className="m-0 min-h-6 text-small text-ink-soft" aria-live="polite">
        {resent ? "Đã gửi lại." : ""}
      </p>
      {error && <FieldError id="check-email-error">{authMessage(error)}</FieldError>}
      <p className="m-0 text-[15px]">
        Sai email?{" "}
        <button type="button" onClick={wrongEmail} className={AUTH_LINK}>
          Đăng xuất
        </button>{" "}
        để đăng ký bằng email khác.
      </p>
    </div>
  );
}
