"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useEffect, useState } from "react";

export const RAIL_KEY = "essity.rail";

/**
 * SHELL-ART: collapse / expand button of the left rail (≥ 1024px). The state lives on
 * <html data-rail="open|collapsed"> so the server-rendered rail and nav restyle through CSS
 * (see the rail-collapsed variant in globals.css) and is remembered in localStorage. Default open;
 * storage may be blocked, so every access is guarded.
 */
export function RailToggle() {
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    let saved: string | null = null;
    try {
      saved = localStorage.getItem(RAIL_KEY);
    } catch {
      /* storage blocked: stay open */
    }
    // Storage is not readable on the server, so the saved state can only be applied after mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (saved === "collapsed") setCollapsed(true);
    document.documentElement.dataset.rail = saved === "collapsed" ? "collapsed" : "open";
  }, []);
  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    const value = next ? "collapsed" : "open";
    document.documentElement.dataset.rail = value;
    try {
      localStorage.setItem(RAIL_KEY, value);
    } catch {
      /* not remembered */
    }
  }
  const Icon = collapsed ? PanelLeftOpen : PanelLeftClose;
  const label = collapsed ? "Mở rộng thanh bên" : "Thu gọn thanh bên";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-expanded={!collapsed}
      aria-controls="app-rail"
      aria-label={label}
      title={label}
      className="hidden size-11 shrink-0 items-center justify-center rounded-control text-ink-soft hover:bg-sheet/60 hover:text-ink focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-focus min-[1024px]:inline-flex"
    >
      <Icon aria-hidden="true" className="size-5" />
    </button>
  );
}
