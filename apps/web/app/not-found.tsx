import type { Metadata } from "next";

import { NotFoundBody } from "@/components/not-found-body";
import { AppShell } from "@/components/shells";

export const metadata: Metadata = { title: "Không tìm thấy · Essity" };

// E-06: an unknown address, in Vietnamese and with the navigation (no account slot: the page works
// signed out too, and the nav links lead to the sign-in when needed).
export default function NotFound() {
  return (
    <AppShell>
      <NotFoundBody />
    </AppShell>
  );
}
