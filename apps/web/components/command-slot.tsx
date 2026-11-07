"use client";

import { useEffect, useRef } from "react";

/**
 * E-03: the place a screen gives to CommandLive's portal. It is server-rendered with
 * `data-pending` (CommandLive ignores a pending slot) and the attribute is dropped once this
 * component has hydrated. Without it the portal could fill the slot while the page around it was
 * still hydrating, and React logged "Hydration failed" (#418) on /subjects/[id]/syllabus.
 */
export function CommandSlot({ bottom = false, className }: { bottom?: boolean; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.removeAttribute("data-pending");
  }, []);
  const mark = bottom ? { "data-command-slot-bottom": true } : { "data-command-slot": true };
  return <div ref={ref} {...mark} data-pending="true" className={className} />;
}
