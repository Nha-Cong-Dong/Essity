"use client";

import cytoscape, { type Core } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { shortLabel } from "@/lib/graph";
import { multiStylesheet } from "@/lib/graph-multi-style";
import { optionsFor, type SimEdge, type SimNode, stepSim } from "@/lib/graph-sim";
import { mergeGraphs, type MultiCard, type SubjectGraph } from "@/lib/graph-multi";

// V16/V17: the knowledge graph of one or several subjects. Nodes are cards coloured by subject,
// edges are the links between cards, a tap on a node opens the card in a popup in the middle of the
// screen. A legend names each colour.

let registered = false;
const MAX_FIT_ZOOM = 1.1;
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

export function KnowledgeGraph({ graphs, height = "max(26rem, calc(100dvh - 15rem))" }: { graphs: SubjectGraph[]; height?: string }) {
  const merged = useMemo(() => mergeGraphs(graphs), [graphs]);
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  const [pickedId, setPickedId] = useState<string | null>(null);
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const bySubject = useMemo(() => new Map(merged.subjects.map((s) => [s.id, s] as const)), [merged]);
  const picked = merged.cards.find((c) => c.id === pickedId) ?? null;

  useEffect(() => {
    if (merged.cards.length === 0 || !host.current) return;
    if (!registered) {
      cytoscape.use(fcose);
      registered = true;
    }
    const degree = new Map<string, number>();
    for (const e of merged.edges) {
      degree.set(e.from, (degree.get(e.from) ?? 0) + 1);
      degree.set(e.to, (degree.get(e.to) ?? 0) + 1);
    }
    const css = getComputedStyle(document.documentElement);
    const ink = css.getPropertyValue("--ink").trim() || "#221b1b";
    const line = css.getPropertyValue("--line-strong").trim() || "#8a6b7a";
    const cy = cytoscape({
      container: host.current,
      elements: [
        ...merged.cards.map((c) => ({
          data: {
            id: c.id,
            label: shortLabel(c.title),
            color: bySubject.get(c.subjectId)?.color ?? ink,
            size: 12 + 3 * Math.min(degree.get(c.id) ?? 0, 5),
          },
        })),
        ...merged.edges.map((e) => ({ data: { id: e.id, source: e.from, target: e.to } })),
      ],
      style: multiStylesheet(ink, line, css.getPropertyValue("--sheet").trim() || "#ffffff"),
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
    });
    cyRef.current = cy;
    // Labels appear once the reader is zoomed in far enough to read them; a hovered node always shows its own.
    const labelByZoom = () => cy.nodes().toggleClass("labelled", cy.zoom() >= 0.9);
    cy.on("zoom", labelByZoom);
    labelByZoom();
    cy.on("tap", "node", (ev) => setPickedId(ev.target.id()));
    // Hover lights a node and its neighbours; the rest dims (Obsidian-style).
    cy.on("mouseover", "node", (ev) => {
      const hood = ev.target.closedNeighborhood();
      cy.elements().not(hood).addClass("dim");
      hood.addClass("hot");
    });
    cy.on("mouseout", "node", () => cy.elements().removeClass("dim hot"));
    // UI-A: fit puts the whole graph in the middle; a graph of a few cards is not blown up, so its
    // labels keep their size and the canvas does not look empty at the edges.
    const layout = cy.layout({
      name: "fcose",
      animate: false,
      randomize: true,
      fit: true,
      padding: 56,
      nodeDimensionsIncludeLabels: false,
      idealEdgeLength: 90,
      nodeRepulsion: 6500,
    } as cytoscape.LayoutOptions);
    layout.one("layoutstop", () => {
      if (cy.zoom() > MAX_FIT_ZOOM) {
        cy.zoom(MAX_FIT_ZOOM);
        cy.center();
      }
    });
    layout.run();
    // Float: after the first layout the nodes keep drifting under a small force simulation (springs on
    // the edges, repulsion, a pull to the middle). A dragged node is pinned under the pointer and the
    // rest follow. Reduced motion: no drift; nodes can still be dragged.
    let frame = 0;
    let fitTimer = 0;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const startSim = () => {
      if (reduced) return;
      const list = cy.nodes().toArray();
      const index = new Map(list.map((n, i) => [n.id(), i] as const));
      const sim: SimNode[] = list.map((n) => ({ id: n.id(), x: n.position("x"), y: n.position("y"), vx: 0, vy: 0, pinned: false }));
      const links: SimEdge[] = cy
        .edges()
        .toArray()
        .flatMap((e) => {
          const a = index.get(e.source().id());
          const b = index.get(e.target().id());
          return a === undefined || b === undefined ? [] : [{ a, b }];
        });
      cy.on("grab", "node", (ev) => {
        const i = index.get(ev.target.id());
        if (i !== undefined) sim[i].pinned = true;
      });
      cy.on("drag", "node", (ev) => {
        const i = index.get(ev.target.id());
        if (i !== undefined) {
          sim[i].x = ev.target.position("x");
          sim[i].y = ev.target.position("y");
        }
      });
      cy.on("free", "node", (ev) => {
        const i = index.get(ev.target.id());
        if (i !== undefined) sim[i].pinned = false;
      });
      const opts = optionsFor(list.length);
      let alpha = 0.5;
      let calm = 0; // frames spent at the floor; the loop stops after ~10 s and wakes on touch or hover
      let running = false;
      const wake = () => {
        calm = 0;
        alpha = Math.max(alpha, 0.3);
        if (!running) {
          running = true;
          frame = requestAnimationFrame(tick);
        }
      };
      const tick = () => {
        alpha = Math.max(0.1, alpha * 0.995);
        if (alpha <= 0.1 && ++calm > 600) {
          running = false;
          return;
        }
        stepSim(sim, links, alpha, Math.random, opts);
        cy.batch(() => {
          list.forEach((n, i) => {
            if (!sim[i].pinned) n.position({ x: sim[i].x, y: sim[i].y });
          });
        });
        frame = requestAnimationFrame(tick);
      };
      running = true;
      frame = requestAnimationFrame(tick);
      cy.on("grab mouseover", "node", wake);
      // Once the cloud has opened up, frame it again, unless the reader already took hold of the view.
      let touched = false;
      const touch = () => {
        touched = true;
      };
      host.current?.addEventListener("pointerdown", touch, { once: true });
      host.current?.addEventListener("wheel", touch, { once: true, passive: true });
      fitTimer = window.setTimeout(() => {
        if (touched) return;
        cy.animate(
          { fit: { eles: cy.nodes(), padding: 48 } },
          {
            duration: 400,
            complete: () => {
              if (cy.zoom() > MAX_FIT_ZOOM) {
                cy.zoom(MAX_FIT_ZOOM);
                cy.center();
              }
            },
          },
        );
      }, 2500);
    };
    startSim(); // the layout is synchronous (animate: false), so the nodes are already placed
    const resize = new ResizeObserver(() => cy.resize());
    resize.observe(host.current);
    return () => {
      cancelAnimationFrame(frame);
      window.clearTimeout(fitTimer);
      resize.disconnect();
      cy.destroy();
      cyRef.current = null;
    };
  }, [merged, bySubject]);

  // The subjects switched off in the chips are not drawn (their edges go with them).
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.batch(() => {
      cy.nodes().forEach((n) => {
        const card = merged.cards.find((c) => c.id === n.id());
        n.style("display", card && hidden.has(card.subjectId) ? "none" : "element");
      });
    });
  }, [hidden, merged]);

  const toggle = (id: string) =>
    setHidden((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });

  const zoomBy = (f: number) => {
    const cy = cyRef.current;
    if (cy) cy.zoom({ level: cy.zoom() * f, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  if (merged.cards.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3 rounded-tile bg-hong-tint p-6" data-empty>
        <p className="m-0 text-read">Chưa có thẻ kiến thức nào. Ghi một buổi học, các thẻ sẽ hiện thành đồ thị ở đây.</p>
        {graphs[0] && (
          <a href={`/subjects/${graphs[0].id}/sessions/new`} className="inline-flex min-h-11 items-center font-semibold rounded-full bg-sheet px-4 font-medium text-ink no-underline inset-ring-1 inset-ring-line hover:bg-sunken">
            Ghi buổi học
          </a>
        )}
      </div>
    );
  }
  const subject = picked ? bySubject.get(picked.subjectId) : undefined;
  return (
    <div className="flex flex-col gap-3">
      {/* One row on top: the card count, then each subject as a colour chip that also hides / shows it. */}
      <div className="flex flex-wrap items-center gap-2">
        <p className="m-0 mr-2 font-display text-lead">{merged.cards.length} thẻ</p>
        {merged.subjects.map((s) => (
          <button
            key={s.id}
            type="button"
            aria-pressed={!hidden.has(s.id)}
            onClick={() => toggle(s.id)}
            className="inline-flex h-11 max-w-full items-center gap-2 rounded-full bg-sheet px-4 text-meta font-medium text-ink inset-ring-1 inset-ring-line hover:bg-sunken aria-pressed:inset-ring-[1.5px] aria-pressed:inset-ring-line-strong aria-[pressed=false]:text-ink-soft aria-[pressed=false]:line-through"
          >
            <span aria-hidden="true" className="inline-block size-3 shrink-0 rounded-full" style={{ background: s.color }} />
            <span className="truncate">{s.name}</span>
            <span className="text-ink-soft">{s.cards}</span>
          </button>
        ))}
      </div>
      <div className="relative">
        <div
          ref={host}
          aria-label="Đồ thị tri thức"
          style={{ height }}
          className="min-h-70 w-full cursor-grab touch-none overflow-hidden rounded-tile bg-sheet inset-ring-1 inset-ring-line active:cursor-grabbing"
        />
        <div className="absolute right-2 bottom-2 flex gap-2">
          <button type="button" aria-label="Phóng to" className={ZOOM} onClick={() => zoomBy(1.3)}>
            +
          </button>
          <button type="button" aria-label="Thu nhỏ" className={ZOOM} onClick={() => zoomBy(1 / 1.3)}>
            −
          </button>
          <button type="button" className={ZOOM} onClick={() => {
              const cy = cyRef.current;
              if (!cy) return;
              cy.fit(undefined, 48);
              if (cy.zoom() > MAX_FIT_ZOOM) {
                cy.zoom(MAX_FIT_ZOOM);
                cy.center();
              }
            }}>
            Đặt lại
          </button>
        </div>
      </div>
      {picked && subject && <CardPopup card={picked} subject={subject.name} color={subject.color} onClose={() => setPickedId(null)} />}
    </div>
  );
}
