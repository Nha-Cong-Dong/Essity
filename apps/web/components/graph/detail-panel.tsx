"use client";

import type { Ref } from "react";

import { Marker } from "@/components/notebook";
import { Button } from "@/components/ui/button";
import { EDGE_KINDS, EDGE_STYLE, neighbourhood, type GraphCard, type GraphEdge, type GraphView } from "@/lib/graph";

// T9.10a (US-19 AC4; DESIGN §6.15 item 5): the tray. An in-flow panel, not a modal and not a
// sheet: under the frame on a phone, a sticky 360 px column from 1024 px. A card shows its text,
// its anchors, the questions that need it and its links with their evidence; an edge shows the
// quote that makes it exist. Copy marked is the Coder's wording (DESIGN has none).

export type Selection = { kind: "card"; id: string } | { kind: "edge"; id: string };

type Props = {
  view: GraphView;
  selection: Selection | null;
  headingRef: Ref<HTMLHeadingElement>;
  /** Wording of the last unlink, if any: "done" or "failed". */
  unlink: "done" | "failed" | null;
  onSelectCard: (id: string) => void;
  onBackToGraph: () => void;
  onClose: () => void;
  onRemoveEdge: (id: string) => void;
};

const QUIET =
  "min-h-11 min-w-0 rounded-control px-2 py-2 text-left underline decoration-line-strong decoration-[1.5px] underline-offset-[5px] wrap-anywhere outline-none hover:decoration-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";

function Quote({ children }: { children: string }) {
  return (
    <q data-user className="text-source wrap-anywhere">
      <Marker>{children}</Marker>
    </q>
  );
}

function SourceButton({ label }: { label: string }) {
  return (
    <Button type="button" variant="quiet" className="self-start" aria-label={`Mở nguồn: ${label}`}>
      Mở nguồn
    </Button>
  );
}

function CardDetail({ card, view, onSelectCard }: { card: GraphCard; view: GraphView; onSelectCard: (id: string) => void }) {
  const byId = new Map(view.cards.map((c) => [c.id, c] as const));
  const links = view.edges.filter((e) => e.from === card.id || e.to === card.id);
  const two = [...neighbourhood(view.edges, card.id, 2)].filter(([, d]) => d === 2).map(([id]) => byId.get(id)).filter((c): c is GraphCard => c !== undefined);
  return (
    <>
      <p data-user className="m-0 text-read wrap-anywhere">
        {card.body}
      </p>
      {card.anchors.length > 0 && (
        <section aria-labelledby="tray-anchors" className="flex flex-col gap-1">
          <h3 id="tray-anchors" className="m-0 text-caption font-semibold">
            Neo nguồn
          </h3>
          {card.anchors.map((a) => (
            <div key={a.id} className="flex flex-col gap-1">
              <p className="m-0 text-meta text-ink-soft" data-user>
                {a.label}
              </p>
              <Quote>{a.quote}</Quote>
              <SourceButton label={a.label} />
            </div>
          ))}
        </section>
      )}
      {card.neededBy.length > 0 && (
        <section aria-labelledby="tray-needed" className="flex flex-col gap-1">
          <h3 id="tray-needed" className="m-0 text-caption font-semibold">
            Cần để trả lời
          </h3>
          <ul className="m-0 list-disc pl-5 text-caption" data-user>
            {card.neededBy.map((q) => (
              <li key={q} className="wrap-anywhere">
                {q}
              </li>
            ))}
          </ul>
        </section>
      )}
      <section aria-labelledby="tray-links" className="flex flex-col gap-2">
        <h3 id="tray-links" className="m-0 text-caption font-semibold">
          Liên kết
        </h3>
        {links.length === 0 ? (
          <p className="m-0 text-caption text-ink-soft">Thẻ này chưa có liên kết trong khung đang xem.</p>
        ) : (
          EDGE_KINDS.filter((k) => links.some((e) => e.kind === k)).map((kind) => (
            <div key={kind} className="flex flex-col gap-1">
              <p className="m-0 text-meta text-ink-soft">{EDGE_STYLE[kind].label}</p>
              <ul className="m-0 flex list-none flex-col gap-2 p-0">
                {links
                  .filter((e) => e.kind === kind)
                  .map((e) => {
                    const other = byId.get(e.from === card.id ? e.to : e.from);
                    return other ? (
                      <li key={e.id} className="flex flex-col" data-user>
                        <button type="button" data-link-to={other.id} className={QUIET} onClick={() => onSelectCard(other.id)}>
                          {other.title}
                        </button>
                        <Quote>{e.evidence}</Quote>
                      </li>
                    ) : null;
                  })}
              </ul>
            </div>
          ))
        )}
      </section>
      {two.length > 0 && (
        <details>
          <summary className="flex min-h-11 cursor-pointer items-center text-caption font-semibold">
            Xa hơn
          </summary>
          <ul className="m-0 flex list-none flex-col p-0">
            {two.map((c) => (
              <li key={c.id} data-user>
                <button type="button" className={QUIET} onClick={() => onSelectCard(c.id)}>
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}

function EdgeDetail({
  edge,
  view,
  unlink,
  onRemoveEdge,
}: {
  edge: GraphEdge;
  view: GraphView;
  unlink: Props["unlink"];
  onRemoveEdge: (id: string) => void;
}) {
  const from = view.cards.find((c) => c.id === edge.from);
  const to = view.cards.find((c) => c.id === edge.to);
  return (
    <>
      <p data-user className="m-0 text-read wrap-anywhere">
        {from?.title} <span className="font-semibold">{EDGE_STYLE[edge.kind].phrase}</span> {to?.title}
      </p>
      <section aria-labelledby="tray-evidence" className="flex flex-col gap-1">
        <h3 id="tray-evidence" className="m-0 text-caption font-semibold">
          Bằng chứng
        </h3>
        <Quote>{edge.evidence}</Quote>
        <SourceButton label={`${from?.title ?? ""} và ${to?.title ?? ""}`} />
      </section>
      <div className="mt-2 flex flex-col gap-2 border-t border-line pt-3">
        <Button type="button" variant="secondary" className="self-start" onClick={() => onRemoveEdge(edge.id)}>
          Gỡ liên kết này
        </Button>
        {unlink === "failed" && (
          <p role="status" className="m-0 text-caption">
            Chưa có gì thay đổi. Thử lại.
          </p>
        )}
      </div>
    </>
  );
}

export function DetailPanel({ view, selection, headingRef, unlink, onSelectCard, onBackToGraph, onClose, onRemoveEdge }: Props) {
  const card = selection?.kind === "card" ? view.cards.find((c) => c.id === selection.id) : undefined;
  const edge = selection?.kind === "edge" ? view.edges.find((e) => e.id === selection.id) : undefined;
  const heading = card?.title ?? (edge ? `Liên kết: ${EDGE_STYLE[edge.kind].label}` : null);

  return (
    <section
      aria-labelledby="tray-title"
      data-tray
      className="flex min-w-0 flex-col gap-4 rounded-sheet bg-sheet p-4 shadow-sheet lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto"
    >
      {heading === null ? (
        <>
          <h2 id="tray-title" ref={headingRef} tabIndex={-1} className="m-0 text-read font-semibold outline-none">
            Chi tiết
          </h2>
          <p className="m-0 text-caption text-ink-soft">Chọn một thẻ hoặc một đường để xem chi tiết.</p>
        </>
      ) : (
        <>
          <div className="flex items-start justify-between gap-2">
            <h2
              id="tray-title"
              ref={headingRef}
              tabIndex={-1}
              data-user
              className="m-0 min-w-0 text-read font-semibold wrap-anywhere outline-none"
            >
              {heading}
            </h2>
            <Button type="button" variant="quiet" className="shrink-0" onClick={onClose}>
              Đóng
            </Button>
          </div>
          <Button type="button" variant="quiet" className="self-start lg:hidden" onClick={onBackToGraph}>
            Về đồ thị
          </Button>
          {card && <CardDetail card={card} view={view} onSelectCard={onSelectCard} />}
          {edge && <EdgeDetail edge={edge} view={view} unlink={unlink} onRemoveEdge={onRemoveEdge} />}
        </>
      )}
      <div role="status" className="sr-only">
        {heading !== null && `Đã chọn: ${heading}`}
      </div>
    </section>
  );
}
