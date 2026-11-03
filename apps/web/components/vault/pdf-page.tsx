"use client";

import { useEffect, useRef, useState } from "react";

// G4: one page of the original PDF, drawn with pdf.js, the cited passage marked on top. The text
// layer is searched for the passage (whitespace folded); every text run it touches gets a box.
// Any failure (blocked fetch, bad file, no match) calls `onFail` and the panel shows the page text.

type Box = { left: number; top: number; width: number; height: number };

const fold = (text: string) => text.replace(/\s+/g, " ").trim().toLowerCase();

/** Boxes (px) of the runs that overlap `quote`, from pdf.js text items already in viewport space. */
export function matchBoxes(items: { str: string; box: Box }[], quote: string): Box[] {
  let hay = "";
  const owner: number[] = [];
  items.forEach((item, i) => {
    const piece = fold(item.str);
    if (!piece) return;
    if (hay) {
      hay += " ";
      owner.push(-1);
    }
    for (let k = 0; k < piece.length; k++) owner.push(i);
    hay += piece;
  });
  const needle = fold(quote);
  const at = needle ? hay.indexOf(needle) : -1;
  if (at < 0) return [];
  const hit = new Set(owner.slice(at, at + needle.length).filter((i) => i >= 0));
  return [...hit].map((i) => items[i].box);
}

export function PdfPage({ url, page, quote, onFail }: { url: string; page: number; quote: string; onFail: () => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [boxes, setBoxes] = useState<Box[]>([]);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
        const doc = await pdfjs.getDocument({ url }).promise;
        const pdfPage = await doc.getPage(page);
        const base = pdfPage.getViewport({ scale: 1 });
        const scale = Math.min(1.6, 640 / base.width);
        const viewport = pdfPage.getViewport({ scale });
        const el = canvas.current;
        const ctx = el?.getContext("2d");
        if (!el || !ctx || cancelled) return;
        el.width = Math.floor(viewport.width);
        el.height = Math.floor(viewport.height);
        await pdfPage.render({ canvasContext: ctx, viewport }).promise;
        const content = await pdfPage.getTextContent();
        const items = content.items.flatMap((raw) => {
          if (!("str" in raw)) return [];
          const t = pdfjs.Util.transform(viewport.transform, raw.transform);
          const height = raw.height * scale || Math.hypot(t[2], t[3]);
          return [{ str: raw.str, box: { left: t[4], top: t[5] - height, width: raw.width * scale, height } }];
        });
        const found = matchBoxes(items, quote);
        if (cancelled) return;
        if (found.length === 0) throw new Error("no match");
        setSize({ w: el.width, h: el.height });
        setBoxes(found);
      } catch {
        if (!cancelled) onFail();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [url, page, quote, onFail]);

  return (
    <div className="relative max-w-full overflow-auto" style={size ? { width: size.w } : undefined}>
      <canvas ref={canvas} className="block max-w-full" aria-label={`Trang ${page} của tài liệu gốc`} />
      {boxes.map((b, i) => (
        <span
          key={i}
          aria-hidden="true"
          className="pointer-events-none absolute bg-hl/45"
          style={{ left: b.left, top: b.top, width: b.width, height: b.height }}
        />
      ))}
    </div>
  );
}
