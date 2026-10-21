import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";
import { RedirectIfSignedIn } from "@/components/auth/redirect-if-signed-in";

export const metadata: Metadata = { title: "Đăng nhập · Essity" };

export default function LoginPage() {
  return (
    <AuthCard title="Đăng nhập">
      <Suspense fallback={null}>
        <RedirectIfSignedIn />
      </Suspense>
      <LoginForm />
    </AuthCard>
  );
}
