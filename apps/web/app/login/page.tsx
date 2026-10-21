import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { connection } from "next/server";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { LoginForm } from "@/components/auth/login-form";
import { getSession } from "@/lib/session";

export const metadata: Metadata = { title: "Đăng nhập · Essity" };

// AC7: someone still signed in goes straight to the app. The proxy never does this (a dead
// cookie would loop), so the page asks core-api.
async function RedirectIfSignedIn() {
  await connection();
  const me = await getSession().catch(() => null); // core-api down: show the form
  if (me) redirect(me.email_verified ? "/today" : "/check-email");
  return null;
}

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
