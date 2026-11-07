"use client";

import { usePathname, useRouter } from "next/navigation";
import { useMemo, useState, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";

import { CommandBar } from "@/components/command-bar";
import { OutlineChat } from "@/components/syllabus/syllabus-chat";
import { liveCommands } from "@/lib/command-client";

// T9.3 (US-18; DESIGN §6.14): the command bar of a subject, live. The layout of /subjects/[id]
// keeps this one component (and so the undo stack) across the subject's screens; it draws the bar
// into the slot of the screen's AppShell. A screen without that slot (the focus shell of a study
// session) shows no bar. After a command applies or is undone, `router.refresh()` reads the screen
// again.

export const SLOT = "[data-command-slot]";
const SYLLABUS = new RegExp("^/subjects/[^/]+/syllabus$"); // B3: the bar lives on the outline page only
// A screen may ask for the bar at its foot instead (outline customise screen).
const BOTTOM = "[data-command-slot-bottom]";
const EXAMPLE = "phần 3.4 kết thúc ở trang 80";

// Module-level so React does not resubscribe (a new function identity each render) on every commit.
const watchBody = (notify: () => void) => {
  const watch = new MutationObserver(notify);
  // `data-pending` going away (CommandSlot hydrated) is a change too.
  watch.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["data-pending"] });
  return () => watch.disconnect();
};
// E-03: a slot still marked `data-pending` has not hydrated yet; filling it would break its hydration.
const ready = (selector: string) => document.querySelector(`${selector}:not([data-pending])`);
const readSlot = () => ready(BOTTOM) ?? ready(SLOT);
const noSlot = () => null;

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
  // A streamed page brings its slot after this host hydrated (a full page load), so the slot is
  // watched for, not read once: without it the outline chat was missing after a reload.
  const slot = useSyncExternalStore(watchBody, readSlot, noSlot);

  if (slot === null || !SYLLABUS.test(pathname)) return null;
  // The foot of the outline screen is the plain-language chat (E3), not the command bar.
  if (slot.matches(BOTTOM)) {
    return createPortal(<OutlineChat subjectId={subjectId} onChanged={() => router.refresh()} />, slot);
  }
  return createPortal(<CommandBar example={EXAMPLE} run={live.run} undo={live.undo} />, slot);
}
