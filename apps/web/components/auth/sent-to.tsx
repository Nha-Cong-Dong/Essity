import { redirect } from "next/navigation";
import { connection } from "next/server";

import { AuthBody, AuthState } from "@/components/auth/auth-state";
import { CheckEmailActions } from "@/components/auth/check-email-actions";
import { RESEND_COOLDOWN_SECONDS } from "@/lib/auth-errors";
import { landingFor } from "@/lib/landing";
import { maskEmail } from "@/lib/mask-email";
import { getPendingEmail, getSession } from "@/lib/session";

// T1.13, /check-email: the address comes from the session, or from the sign-up cookie before
// there is one (F1); it is masked here, on the server, so the full address never reaches the page.
// A verified account is sent on by landingFor.
export async function SentTo() {
  await connection();
  const me = await getSession();
  if (me?.email_verified) redirect(landingFor(me));
  const email = me?.email ?? (await getPendingEmail());
  if (email === null) redirect("/register");
  return (
    <>
      <AuthState mark="mail" title={<>Đã gửi link tới <span className="text-hong-text">{maskEmail(email)}</span></>}>
        <AuthBody>Mở email và bấm vào link để tiếp tục. Nếu không thấy, xem cả mục thư rác.</AuthBody>
      </AuthState>
      <CheckEmailActions initialWait={me ? 0 : RESEND_COOLDOWN_SECONDS} />
    </>
  );
}
