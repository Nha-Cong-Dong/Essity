import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { CheckEmailActions } from "@/components/auth/check-email-actions";
import { RESEND_COOLDOWN_SECONDS } from "@/lib/auth-errors";
import { maskEmail } from "@/lib/mask-email";
import { getPendingEmail, getSession } from "@/lib/session";

export const metadata: Metadata = { title: "Kiểm tra email · Essity" };

// T1.13: the only screen an unverified account sees (DESIGN.md §6.1). The address comes from
// the session, or from the sign-up cookie before there is one (F1); it is masked here, on the
// server, so the full address never reaches the page.
async function SentTo() {
  await connection();
  const me = await getSession();
  if (me?.email_verified) redirect("/today");
  const email = me?.email ?? (await getPendingEmail());
  if (email === null) redirect("/register");
  return (
    <>
      <p className="m-0 text-body">
        Đã gửi link tới <span className="font-hand text-hand text-hong">{maskEmail(email)}</span>
      </p>
      <p className="m-0 text-ink-soft">
        Mở email và bấm vào link để tiếp tục. Nếu không thấy, xem cả mục thư rác.
      </p>
      <CheckEmailActions initialWait={me ? 0 : RESEND_COOLDOWN_SECONDS} />
    </>
  );
}

export default function CheckEmailPage() {
  return (
    <AuthCard title="Hãy kiểm tra email của bạn">
      <Suspense
        fallback={<div className="h-40 rounded-sm bg-[color-mix(in_srgb,var(--line)_80%,transparent)]" />}
      >
        <SentTo />
      </Suspense>
    </AuthCard>
  );
}
