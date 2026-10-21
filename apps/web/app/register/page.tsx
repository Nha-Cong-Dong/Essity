import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { RedirectIfSignedIn } from "@/components/auth/redirect-if-signed-in";
import { RegisterForm } from "@/components/auth/register-form";

export const metadata: Metadata = { title: "Đăng ký · Essity" };

export default function RegisterPage() {
  return (
    <AuthCard title="Đăng ký">
      <Suspense fallback={null}>
        <RedirectIfSignedIn />
      </Suspense>
      <RegisterForm />
    </AuthCard>
  );
}
