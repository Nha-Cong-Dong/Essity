import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { AuthShell } from "@/components/shells";
import { requireVerifiedSession } from "@/lib/session";

export const metadata: Metadata = { title: "Điểm xuất phát · Essity" };

// Placeholder for the baseline screen (T1.18 builds it, DESIGN.md §6.2): where "Ghi điểm
// xuất phát" leads after verifying, so that link does not change when T1.18 lands.
async function Onboarding() {
  await connection();
  await requireVerifiedSession();
  return (
    <div className="flex max-w-[640px] flex-col gap-6">
      <h1 className="m-0 font-display text-title">Trước khi bắt đầu, ghi lại điểm xuất phát</h1>
      <a href="/today" className="font-medium text-ink underline decoration-ink-soft underline-offset-4">
        Nhập sau
      </a>
    </div>
  );
}

export default function OnboardingPage() {
  return (
    <AuthShell>
      <Suspense fallback={null}>
        <Onboarding />
      </Suspense>
    </AuthShell>
  );
}
