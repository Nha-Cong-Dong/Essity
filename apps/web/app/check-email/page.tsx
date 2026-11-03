import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthLayout } from "@/components/auth/auth-layout";
import { SentTo } from "@/components/auth/sent-to";
import { CHECK_EMAIL_TITLE } from "@/lib/auth-copy";

export const metadata: Metadata = { title: "Kiểm tra email · Essity" };

// T1.13: the only screen an unverified account sees (DESIGN.md §6.1); SentTo reads the session.

export default function CheckEmailPage() {
  return (
    <AuthLayout title={CHECK_EMAIL_TITLE}>
      <Suspense
        fallback={<div className="h-40 rounded-control bg-sunken" />}
      >
        <SentTo />
      </Suspense>
    </AuthLayout>
  );
}
