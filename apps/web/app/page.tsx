import type { Metadata } from "next";
import { cookies } from "next/headers";
import { Suspense } from "react";

import { Landing } from "@/components/landing/landing";
import { LandingRedirect } from "@/components/landing-redirect";
import { SESSION_COOKIE } from "@/lib/cookies";

export const metadata: Metadata = {
  title: "Essity",
  description:
    "Tối nay ôn gì, đã có app lo. Trợ lí học tập thông minh. Quản lí lịch ôn tập hiệu quả với thuật toán FSRS.",
};

// T0.15: "/" is the only public page of the app (proxy.ts lets it through). A visitor without a
// session cookie sees the landing; with one, the way into the app as before: the page asks
// core-api whether the cookie is a live, verified session (landingFor).
export default async function Home() {
  if ((await cookies()).has(SESSION_COOKIE)) {
    return (
      <Suspense fallback={null}>
        <LandingRedirect />
      </Suspense>
    );
  }
  return <Landing />;
}
