import type { Metadata } from "next";
import { Suspense } from "react";

import { AuthCard } from "@/components/auth/auth-card";
import { SentTo } from "@/components/auth/sent-to";

export const metadata: Metadata = { title: "Kiểm tra email · Essity" };

// T1.13: the only screen an unverified account sees (DESIGN.md §6.1); SentTo reads the session.

export default function CheckEmailPage() {
  return (
    <AuthCard title="Hãy kiểm tra email của bạn">
      <Suspense
        fallback={<div className="h-40 rounded-control bg-sunken" />}
      >
        <SentTo />
      </Suspense>
    </AuthCard>
  );
}
