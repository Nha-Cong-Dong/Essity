import type { Metadata } from "next";

import { AuthLayout } from "@/components/auth/auth-layout";
import { VerifyEmail } from "@/components/auth/verify-email";

export const metadata: Metadata = { title: "Xác minh email · Essity" };

// T1.13: opened from the verification email. Sends no Referer (next.config.ts) and loads
// nothing from a third party, so the token in the URL goes nowhere.
export default function VerifyEmailPage() {
  return (
    <AuthLayout title="Xác minh email">
      <VerifyEmail />
    </AuthLayout>
  );
}
