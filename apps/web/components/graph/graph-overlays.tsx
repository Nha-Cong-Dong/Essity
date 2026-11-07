"use client";

import Link from "next/link";
import { type ReactNode, useEffect, useRef } from "react";

import { Mascot } from "@/components/mascot";
import type { MultiCard } from "@/lib/graph-multi";
import type { Topic } from "@/lib/graph-topic";

// GRAPH-V4-CANVAS (.work/DESIGN-V4/mockups/graph.html): the pieces that float over the full-bleed
// canvas of /graph: the legend, the zoom buttons, the detail card, and the empty state.

const SHEET = "rounded-[18px] border border-line bg-sheet text-ink";

/** Legend card, top left. Each topic is a colour toggle with its card count; the card list sits inside (keyboard route). */
export function GraphLegend({
  topics,
  hidden,
  onToggle,
  total,
  mode,
  cardList,
}: {
  topics: Topic[];
  hidden: ReadonlySet<string>;
  onToggle: (id: string) => void;
  total: number;
  mode: "subject" | "chapter";
  cardList: ReactNode;
}) {
  const box = useRef<HTMLDetailsElement>(null);
  // A phone keeps only the title (the mockup hides the rows); the toggles open with a tap.
  useEffect(() => {
    if (box.current && window.innerWidth < 900) box.current.open = false;
  }, []);
  const unit = mode === "chapter" ? "chương" : "môn";
  return (
    <details
      ref={box}
      open
      data-graph-legend
      className={`${SHEET} absolute top-3 left-3 z-10 max-h-[calc(100%-1.5rem)] w-[min(15rem,calc(100%-11.5rem))] overflow-auto px-3 py-1 text-meta min-[900px]:top-5 min-[900px]:left-5 min-[900px]:w-60 min-[900px]:px-4`}
    >
      <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-2 font-display text-body font-semibold">
        <span>Đồ thị kiến thức</span>
        <span className="shrink-0 text-meta font-normal whitespace-nowrap text-ink-soft">{total} thẻ</span>
      </summary>
      <ul className="m-0 mb-2 flex list-none flex-col gap-1 p-0">
        {topics.map((t) => (
          <li key={t.id}>
            <button
              type="button"
              aria-pressed={!hidden.has(t.id)}
              onClick={() => onToggle(t.id)}
              className="flex min-h-11 w-full items-center gap-2.5 rounded-control px-1 text-left hover:bg-sunken aria-[pressed=false]:text-ink-soft aria-[pressed=false]:line-through"
            >
              <span aria-hidden="true" className="inline-block size-3 shrink-0 rounded-full" style={{ background: t.color }} />
              <span className="min-w-0 flex-1 truncate">{t.name}</span>
              <span className="text-ink-soft">{t.cards}</span>
            </button>
          </li>
        ))}
      </ul>
      <p className="m-0 mb-2 text-caption text-ink-soft">
        Mỗi màu là một {unit}; nút lớn là {unit}, thẻ nhiều liên kết thì to hơn.
      </p>
      {mode === "chapter" && (
        <Link href="/graph" className="mb-1 inline-flex min-h-11 items-center rounded-full px-3 font-semibold text-ink no-underline hover:bg-sunken">
          Xem mọi môn
        </Link>
      )}
      <details data-card-list className="border-t border-line">
        <summary className="flex min-h-11 cursor-pointer items-center font-medium">Danh sách thẻ</summary>
        <ul className="m-0 mb-2 flex max-h-60 list-none flex-col overflow-auto p-0">{cardList}</ul>
      </details>
    </details>
  );
}

const ZBTN =
  "grid size-11 place-items-center rounded-full border border-line bg-sheet text-ink hover:bg-sunken focus-visible:outline-2 focus-visible:outline-focus";
const ICON = { viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", className: "size-[18px]", "aria-hidden": true } as const;

/** Zoom buttons: a column bottom left on desktop, a row top right on a phone (the sheet owns the bottom). */
export function ZoomControls({ onIn, onOut, onFit }: { onIn: () => void; onOut: () => void; onFit: () => void }) {
  return (
    <div role="group" aria-label="Thu phóng" className="absolute top-3 right-3 z-10 flex gap-2 min-[900px]:top-auto min-[900px]:right-auto min-[900px]:bottom-5 min-[900px]:left-5 min-[900px]:flex-col">
      <button type="button" aria-label="Phóng to" className={ZBTN} onClick={onIn}>
        <svg {...ICON}><path d="M12 5v14M5 12h14" /></svg>
      </button>
      <button type="button" aria-label="Thu nhỏ" className={ZBTN} onClick={onOut}>
        <svg {...ICON}><path d="M5 12h14" /></svg>
      </button>
      <button type="button" aria-label="Vừa khung" className={ZBTN} onClick={onFit}>
        <svg {...ICON}><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" /></svg>
      </button>
    </div>
  );
}

/** The picked card: a card at the right on desktop, a bottom sheet on a phone. Not modal: the graph stays usable. */
export function DetailCard({
  card,
  subject,
  color,
  related,
  onPick,
  onClose,
}: {
  card: MultiCard;
  subject: string;
  color: string;
  related: { id: string; title: string }[];
  onPick: (id: string) => void;
  onClose: () => void;
}) {
  const head = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    head.current?.focus({ preventScroll: true });
  }, [card.id]);
  const quote = card.anchors.find((a) => a.quote);
  return (
    <section
      aria-labelledby="graph-card-title"
      data-graph-detail
      className="absolute inset-x-3 bottom-3 z-20 flex max-h-[50%] flex-col gap-3 overflow-auto rounded-[24px] border border-line bg-sheet p-5 text-ink min-[900px]:inset-x-auto min-[900px]:top-5 min-[900px]:right-5 min-[900px]:bottom-auto min-[900px]:max-h-[calc(100%-2.5rem)] min-[900px]:w-[340px] min-[900px]:p-6"
    >
      <div aria-hidden="true" className="mx-auto -mt-2 h-1.5 w-10 shrink-0 rounded-full bg-line-strong min-[900px]:hidden" />
      <button type="button" aria-label="Đóng" onClick={onClose} className="absolute top-1 right-2 grid size-11 place-items-center rounded-full text-2xl text-ink-soft hover:bg-sunken">
        ×
      </button>
      <p className="m-0 flex items-center gap-2 pr-10 text-meta text-ink-soft">
        <span aria-hidden="true" className="inline-block size-3 shrink-0 rounded-full" style={{ background: color }} />
        Thẻ · {subject}
      </p>
      <h2 id="graph-card-title" ref={head} tabIndex={-1} className="m-0 font-display text-title leading-tight tracking-tight wrap-anywhere outline-none">
        {card.title}
      </h2>
      <p className="m-0 whitespace-pre-wrap text-body wrap-anywhere">{card.body}</p>
      {quote && (
        <div className="flex flex-col gap-1.5 rounded-[14px] bg-bg p-3.5 text-meta leading-relaxed max-[899px]:hidden">
          <small className="text-caption text-ink-soft">{quote.label}</small>
          <q className="wrap-anywhere">
            <mark className="rounded-sm bg-hl px-0.5 text-ink">{quote.quote}</mark>
          </q>
        </div>
      )}
      {related.length > 0 && (
        <>
          <p className="m-0 mt-1 text-meta text-ink-soft">Liên quan</p>
          <ul className="m-0 flex list-none flex-wrap gap-2 p-0">
            {related.map((r) => (
              <li key={r.id}>
                <button type="button" onClick={() => onPick(r.id)} className="min-h-11 rounded-full bg-sunken px-3 text-meta hover:bg-line">
                  {r.title}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
      <Link
        href={`/kho-kien-thuc?subject=${card.subjectId}`}
        data-open-vault
        className="mt-1 inline-flex min-h-12 shrink-0 items-center justify-center rounded-full bg-hong font-semibold text-on-hong no-underline hover:bg-hong-press"
      >
        Mở trong Kho
      </Link>
    </section>
  );
}

/** Empty state: the canvas itself, with a dotted ground and the mascot, one sentence, one action. */
export function GraphEmpty({ href }: { href: string | null }) {
  return (
    <div
      data-empty
      className="relative flex h-full min-h-80 w-full flex-col items-center justify-center gap-4 overflow-hidden rounded-sheet border border-line bg-bg p-6 text-center [background-image:radial-gradient(var(--line)_1.5px,transparent_1.5px)] [background-size:28px_28px]"
    >
      <div className="flex flex-col items-center gap-3 rounded-sheet bg-sheet px-8 py-6">
        <Mascot pose="vui" size="md" />
        <p className="m-0 max-w-sm text-lead">Chưa có thẻ kiến thức nào. Ghi một buổi học, các thẻ sẽ hiện thành đồ thị ở đây.</p>
        {href && (
          <a
            href={href}
            className="inline-flex min-h-11 items-center rounded-full bg-hong px-5 font-semibold text-on-hong no-underline hover:bg-hong-press"
          >
            Ghi buổi học
          </a>
        )}
      </div>
    </div>
  );
}
