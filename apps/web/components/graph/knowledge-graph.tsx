"use client";

import cytoscape, { type Core } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { shortLabel } from "@/lib/graph";
import { multiStylesheet } from "@/lib/graph-multi-style";
import { mergeGraphs, type MultiCard, type SubjectGraph } from "@/lib/graph-multi";

// V16/V17: the knowledge graph of one or several subjects. Nodes are cards coloured by subject,
// edges are the links between cards, a tap on a node opens the card in a popup in the middle of the
// screen. A legend names each colour.

let registered = false;
const ZOOM =
  "inline-flex h-11 items-center justify-center rounded-full bg-sheet px-3 text-caption text-ink inset-ring-[1.5px] inset-ring-line-strong hover:bg-sunken";

function CardPopup({ card, subject, color, onClose }: { card: MultiCard; subject: string; color: string; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current;
    if (d && !d.open) d.showModal?.();
  }, []);
  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onClick={(e) => {
        if (e.target === ref.current) onClose();
      }}
      aria-labelledby="graph-card-title"
      className="m-auto max-h-[80vh] w-[min(92vw,34rem)] overflow-auto rounded-sheet border border-line bg-sheet p-6 text-ink backdrop:bg-ink/40"
    >
      <p className="m-0 flex items-center gap-2 text-meta text-ink-soft">
        <span aria-hidden="true" className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
        {subject}
      </p>
      <h2 id="graph-card-title" className="mt-2 mb-3 font-display text-lead wrap-anywhere">
        {card.title}
      </h2>
      <p className="m-0 whitespace-pre-wrap text-read wrap-anywhere">{card.body}</p>
      {card.anchors.length > 0 && (
        <ul className="m-0 mt-4 flex list-none flex-col gap-2 p-0 text-meta text-ink-soft">
          {card.anchors.map((a) => (
            <li key={a.id}>
              <b>{a.label}</b>
              {a.quote ? <q className="ml-1 wrap-anywhere">{a.quote}</q> : null}
            </li>
          ))}
        </ul>
      )}
      <div className="mt-5 flex justify-end">
        <Button type="button" variant="secondary" onClick={onClose}>
          Đóng
        </Button>
      </div>
    </dialog>
  );
}

export function KnowledgeGraph({ graphs, height = "60vh" }: { graphs: SubjectGraph[]; height?: string }) {
  const merged = useMemo(() => mergeGraphs(graphs), [graphs]);
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const bySubject = useMemo(() => new Map(merged.subjects.map((s) => [s.id, s] as const)), [merged]);
  const picked = merged.cards.find((c) => c.id === pickedId) ?? null;

  useEffect(() => {
    if (merged.cards.length === 0 || !host.current) return;
    if (!registered) {
      cytoscape.use(fcose);
      registered = true;
    }
    const css = getComputedStyle(document.documentElement);
    const ink = css.getPropertyValue("--ink").trim() || "#221b1b";
    const line = css.getPropertyValue("--line-strong").trim() || "#8a6b7a";
    const cy = cytoscape({
      container: host.current,
      elements: [
        ...merged.cards.map((c) => ({
          data: { id: c.id, label: shortLabel(c.title), color: bySubject.get(c.subjectId)?.color ?? ink },
        })),
        ...merged.edges.map((e) => ({ data: { id: e.id, source: e.from, target: e.to } })),
      ],
      style: multiStylesheet(ink, line),
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
      autoungrabify: true,
    });
    cyRef.current = cy;
    cy.on("tap", "node", (ev) => setPickedId(ev.target.id()));
    cy.layout({
      name: "fcose",
      animate: false,
      randomize: true,
      fit: true,
      padding: 30,
      nodeDimensionsIncludeLabels: true,
    } as cytoscape.LayoutOptions).run();
    const resize = new ResizeObserver(() => cy.resize());
    resize.observe(host.current);
    return () => {
      resize.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, [merged, bySubject]);

  const zoomBy = (f: number) => {
    const cy = cyRef.current;
    if (cy) cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  if (merged.cards.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-sheet bg-sheet p-6 shadow-sheet" data-empty>
        <p className="m-0 text-read">Chưa có thẻ kiến thức nào. Ghi một buổi học, các thẻ sẽ hiện thành đồ thị ở đây.</p>
        {graphs[0] && (
          <a href={`/subjects/${graphs[0].id}/sessions/new`} className="inline-flex min-h-11 items-center font-semibold underline">
            Ghi buổi học
          </a>
        )}
      </div>
    );
  }
  const subject = picked ? bySubject.get(picked.subjectId) : undefined;
  return (
    <div className="flex flex-col gap-3">
      <ul aria-label="Chú thích màu" className="m-0 flex list-none flex-wrap gap-x-5 gap-y-2 p-0 text-meta">
        {merged.subjects.map((s) => (
          <li key={s.id} className="flex items-center gap-2">
            <span aria-hidden="true" className="inline-block h-3.5 w-3.5 rounded-full" style={{ background: s.color }} />
            <span className="wrap-anywhere">
              {s.name} · {s.cards} thẻ
            </span>
          </li>
        ))}
      </ul>
      <div className="relative">
        <div
          ref={host}
          aria-label="Đồ thị tri thức"
          style={{ height }}
          className="min-h-70 w-full touch-none overflow-hidden rounded-sheet border border-line bg-sheet"
        />
        <div className="absolute right-2 bottom-2 flex gap-2">
          <button type="button" aria-label="Phóng to" className={ZOOM} onClick={() => zoomBy(1.3)}>
            +
          </button>
          <button type="button" aria-label="Thu nhỏ" className={ZOOM} onClick={() => zoomBy(1 / 1.3)}>
            −
          </button>
          <button type="button" className={ZOOM} onClick={() => cyRef.current?.fit(undefined, 30)}>
            Đặt lại
          </button>
        </div>
      </div>
      {picked && subject && <CardPopup card={picked} subject={subject.name} color={subject.color} onClose={() => setPickedId(null)} />}
    </div>
  );
}
