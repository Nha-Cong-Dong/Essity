import type { Metadata } from "next";

import { AuthLayout } from "@/components/auth/auth-layout";
import { ResetPassword } from "@/components/auth/reset-password";

export const metadata: Metadata = { title: "Đặt mật khẩu mới · Essity" };

// T1.14: opened from the reset email. Sends no Referer (next.config.ts) and loads nothing from
// a third party, so the token in the URL goes nowhere.
export default function ResetPasswordPage() {
  return (
    <AuthLayout title="Đặt lại mật khẩu">
      <ResetPassword />
    </AuthLayout>
  );
}
