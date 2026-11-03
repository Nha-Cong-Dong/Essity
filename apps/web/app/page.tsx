import type { Metadata } from "next";
import { Suspense } from "react";

import { LandingEntry } from "@/components/landing/landing-entry";

export const metadata: Metadata = {
  title: "Essity",
  description:
    "Tối nay ôn gì, đã có app lo. Trợ lí học tập thông minh. Quản lí lịch ôn tập hiệu quả với thuật toán FSRS.",
};

// T0.15: "/" is the only public page of the app (proxy.ts lets it through); see LandingEntry.
export default function Home() {
  return (
    <Suspense fallback={null}>
      <LandingEntry />
    </Suspense>
  );
}
