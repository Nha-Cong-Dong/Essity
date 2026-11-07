"use client";

import "katex/dist/katex.min.css";
import { useEffect } from "react";
import { startLanding } from "./motion";

/** Animates the finished landing markup (see motion.ts). Renders nothing. */
export function LandingMotion() {
  useEffect(() => {
    const root = document.querySelector<HTMLElement>("[data-landing]");
    if (!root) return;
    return startLanding(root);
  }, []);
  return null;
}
