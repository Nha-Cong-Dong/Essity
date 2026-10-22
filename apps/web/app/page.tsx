import { Suspense } from "react";

import { LandingRedirect } from "@/components/landing-redirect";

// The proxy sends a visitor without a session to /login before this runs.
export default function Home() {
  return (
    <Suspense fallback={null}>
      <LandingRedirect />
    </Suspense>
  );
}
