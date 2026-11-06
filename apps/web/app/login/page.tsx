import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { LoginForm } from "@/components/auth/login-form";
import { RedirectIfSignedIn } from "@/components/auth/redirect-if-signed-in";

export const metadata: Metadata = { title: "Đăng nhập · Essity" };

export default function LoginPage() {
  return (
    <AuthLayout
      title="Đăng nhập"
      greeting={
        <>
          <span>Thật vui khi</span> <span>được gặp bạn</span>
        </>
      }
      bubble="Vào ôn thôi!"
    >
      <Suspense fallback={null}>
        <RedirectIfSignedIn />
      </Suspense>
      <LoginForm />
    </AuthLayout>
  );
}
