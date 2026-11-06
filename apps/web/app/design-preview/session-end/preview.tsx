"use client";

import { SessionEndDialog } from "@/components/session-study/session-end-dialog";

export function EndPreview({ empty }: { empty: boolean }) {
  return <SessionEndDialog open empty={empty} recorded={3} onHome={() => undefined} onMore={() => undefined} />;
}
