"use client";

import { type ComponentType, useEffect, useState } from "react";

import { cn } from "@/lib/utils";

// CARD-MD: where a card's words are shown. The Markdown parser and KaTeX load on first use (dynamic
// import), so only pages that show cards pay for them. Until they arrive the words show as plain text
// (single line breaks kept, as old plain-text cards were written), which is also what a card of plain
// text looks like afterwards.
type Inner = ComponentType<{ text: string }>;
let loaded: Inner | null = null;

export function Markdown({ text, className }: { text: string; className?: string }) {
  const [Inner, setInner] = useState<Inner | null>(() => loaded);
  useEffect(() => {
    if (loaded) return;
    let alive = true;
    void import("./markdown-inner").then((m) => {
      loaded = m.default;
      if (alive) setInner(() => m.default);
    });
    return () => {
      alive = false;
    };
  }, []);
  return (
    <div
      className={cn(
        "whitespace-pre-line break-words [&_.katex-display]:overflow-x-auto [&_.katex-display]:overflow-y-hidden [&_a]:underline [&_ol]:my-1 [&_ol]:pl-5 [&_p]:m-0 [&_p+p]:mt-2 [&_ul]:my-1 [&_ul]:pl-5",
        className,
      )}
    >
      {Inner ? <Inner text={text} /> : text}
    </div>
  );
}
