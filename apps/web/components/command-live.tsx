"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { CommandBar } from "@/components/command-bar";
import { liveCommands } from "@/lib/command-client";

// T9.3 (US-18; DESIGN §6.14): the command bar of a subject, live. The layout of /subjects/[id]
// keeps this one component (and so the undo stack) across the subject's screens; it draws the bar
// into the slot of the screen's AppShell. A screen without that slot (the focus shell of a study
// session) shows no bar. After a command applies or is undone, `router.refresh()` reads the screen
// again.

export const SLOT = "[data-command-slot]";
const EXAMPLE = "mục 3.4 kết thúc ở trang 80";

export function CommandLive({ subjectId }: { subjectId: string }) {
  const router = useRouter();
  const pathname = usePathname();
  // One id per mount of the subject's screens (core-api: the "other session" rule of undo).
  const [screenSessionId] = useState(() => crypto.randomUUID());
  const live = useMemo(
    () =>
      liveCommands({
        subjectId,
        screenSessionId,
        changed: () => router.refresh(),
        signedOut: () => router.push("/login"),
      }),
    [subjectId, screenSessionId, router],
  );

  // Each screen draws its own shell: the slot is read again after every commit (React compares the
  // snapshot after a navigation), and the server and the first client render show no bar.
  void pathname;
  const slot = useSyncExternalStore(
    () => () => undefined,
    () => document.querySelector(SLOT),
    () => null,
  );

  if (slot === null) return null;
  return createPortal(<CommandBar example={EXAMPLE} run={live.run} undo={live.undo} />, slot);
}
