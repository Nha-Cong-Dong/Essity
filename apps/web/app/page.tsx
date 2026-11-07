import type { Metadata } from "next";
import { Suspense } from "react";

import { LandingEntry } from "@/components/landing/landing-entry";

export const metadata: Metadata = {
  title: "Essity",
  description:
    "Hôm nay ôn gì, đã có tôi lo! Trợ lí học tập tiên tiến. Quản lí lịch ôn luyện hiệu quả với thuật toán FSRS và đồ thị tri thức.",
};

// T0.15: "/" is the only public page of the app (proxy.ts lets it through); see LandingEntry.
export default function Home() {
  return (
    <Suspense fallback={null}>
      <LandingEntry />
    </Suspense>
  );
}
