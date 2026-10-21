import type { Metadata } from "next";

import { ForgotPassword } from "@/components/auth/forgot-password";

export const metadata: Metadata = { title: "Quên mật khẩu · Essity" };

export default function ForgotPasswordPage() {
  return <ForgotPassword />;
}
