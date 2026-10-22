import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { BaselineForm } from "@/components/baseline/baseline-form";
import { PageFold } from "@/components/motifs";
import { Marker } from "@/components/notebook";
import { AuthShell } from "@/components/shells";
import { Sheet } from "@/components/ui/sheet";
import { requireBaselineToEnter } from "@/lib/onboarding";

export const metadata: Metadata = { title: "Điểm xuất phát · Essity" };

// T1.18, DESIGN.md §6.2: the baseline, once after verifying and before the first subject. A second
// visit after "Nhập sau" shows this same screen (US-11 AC2, DESIGN §10 #16).
async function Onboarding() {
  await connection();
  await requireBaselineToEnter();
  return <BaselineForm />;
}

export default function OnboardingPage() {
  return (
    <AuthShell>
      <Sheet className="relative w-full max-w-160" aria-labelledby="onboarding-title">
        <PageFold />
        <h1 id="onboarding-title" className="m-0 font-display text-title">
          <Marker>Trước khi bắt đầu, ghi lại điểm xuất phát</Marker>
        </h1>
        <p className="mt-3.5 mb-0 max-w-[56ch] text-read text-ink-soft">
          Cuối học kỳ, app sẽ so sánh với hai con số này để cho bạn biết cách học mới có hiệu quả không.
        </p>
        <Suspense fallback={<div aria-busy="true" className="mt-8 h-72 rounded-control bg-sunken" />}>
          <Onboarding />
        </Suspense>
      </Sheet>
    </AuthShell>
  );
}
