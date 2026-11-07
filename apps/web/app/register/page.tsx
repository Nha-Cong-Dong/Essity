import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthLayout, Underlined } from "@/components/auth/auth-layout";
import { RedirectIfSignedIn } from "@/components/auth/redirect-if-signed-in";
import { RegisterForm } from "@/components/auth/register-form";

export const metadata: Metadata = { title: "Đăng ký · Essity" };

export default function RegisterPage() {
  return (
    <AuthLayout title="Tạo tài khoản" greeting={
        <>
          <span>Chào mừng</span>{" "}
          <span>
            <Underlined>bạn mới!</Underlined>
          </span>
        </>
      } bubble="Bắt đầu nhé">
      <Suspense fallback={null}>
        <RedirectIfSignedIn />
      </Suspense>
      <RegisterForm />
    </AuthLayout>
  );
}
