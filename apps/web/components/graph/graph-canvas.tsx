"use client";

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";

import { neighbourhood, type GraphSection, type GraphView } from "@/lib/graph";
import { createFitLock } from "@/lib/graph-fit-lock";
import { graphStylesheet, type Palette } from "@/lib/graph-style";

// T9.10a (DESIGN §6.15, .work/T9.10a/design-decisions.md): the Cytoscape.js frame. Loaded only by
// the graph screen (next/dynamic), so no other page carries the library. The canvas is for pointing
// and for seeing the shape: every fact in it is in the list and the tray, so it is aria-hidden and
// the three zoom buttons sit outside it, with names.
//
// The stylesheet (lib/graph-style.ts) is a function of zoom and palette; hit boxes stay 44 px.

let registered = false;
// Icon buttons: 44 px, drawn like the secondary button (a ring, no fill of its own).
const ZOOM_BUTTON =
  "inline-flex h-11 items-center justify-center rounded-full bg-sheet text-caption text-ink inset-ring-[1.5px] inset-ring-line-strong outline-none hover:bg-sunken focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus";
function readPalette(): Palette {
  const css = getComputedStyle(document.documentElement);
  const get = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback;
  return {
    ink: get("--ink", "#26141d"),
    line: get("--line-strong", "#8f6676"),
    sheet: get("--sheet", "#ffffff"),
    focus: get("--focus", "#c2185b"),
    soft: get("--ink-soft", "#6a4f5c"),
    hong: get("--hong", "#d1347a"),
    now: get("--now", "#891b4c"),
    bg: get("--hong-tint", "#fde6ed"),
  };
}

function elements(view: GraphView, sections: GraphSection[]): ElementDefinition[] {
  const used = new Set(view.cards.map((c) => c.sectionId));
  const out: ElementDefinition[] = sections
    .filter((s) => used.has(s.id))
    .map((s) => ({ data: { id: `s:${s.id}`, label: s.title, isSection: true }, selectable: false, grabbable: false }));
  for (const c of view.cards) {
    const parent = sections.some((s) => s.id === c.sectionId) ? { parent: `s:${c.sectionId}` } : {};
    out.push({ data: { id: c.id, ...parent, label: c.title, title: c.title }, classes: "card" });
  }
  for (const e of view.edges) {
    out.push({ data: { id: e.id, source: e.from, target: e.to, kind: e.kind }, classes: e.kind });
  }
  return out;
}

export type GraphCanvasProps = {
  view: GraphView;
  sections: GraphSection[];
  selectedId: string | null;
  reducedMotion: boolean;
  onSelectCard: (id: string) => void;
  onSelectEdge: (id: string) => void;
};

/**
 * A phone frame is tall and narrow but fcose lays out roughly square: stretch the cards
 * vertically (up to 3x) so the cluster uses the height and its labels do not share a row.
 */
export function stretchToFrame(cy: Core, padX = 48, padY = 48): void {
  const cards = cy.nodes(".card");
  if (cards.length < 2 || cy.width() >= 480) return;
  const box = cards.boundingBox({ includeLabels: false, includeOverlays: false });
  const w = Math.max(box.w, 1);
  const h = Math.max(box.h, 1);
  const k = Math.min(3, Math.max(1, ((cy.height() - 2 * padY) / (cy.width() - 2 * padX)) * (w / h)));
  if (k <= 1.05) return;
  cards.forEach((n) => {
    const { x, y } = n.position();
    n.position({ x, y: box.y1 + (y - box.y1) * k });
  });
}

/** Moves apart (up and down) every pair of card labels that cover each other; false if none did. */
export function separateLabels(cy: Core): boolean {
  const cards = cy.nodes(".card").toArray();
  const box = (n: (typeof cards)[number]) => n.renderedBoundingBox({ includeNodes: false, includeLabels: true, includeEdges: false, includeOverlays: false });
  const zoom = cy.zoom();
  let moved = false;
  for (let i = 0; i < cards.length; i++) {
    for (let j = i + 1; j < cards.length; j++) {
      const a = box(cards[i]);
      const b = box(cards[j]);
      if (!(a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2)) continue;
      const need = (Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1) + 8) / zoom;
      const [up, down] = a.y1 + a.y2 <= b.y1 + b.y2 ? [cards[i], cards[j]] : [cards[j], cards[i]];
      up.position({ x: up.position("x"), y: up.position("y") - need / 2 });
      down.position({ x: down.position("x"), y: down.position("y") + need / 2 });
      moved = true;
    }
  }
  return moved;
}

/** Zoom and pan so the card centres fill the frame, with `padX`/`padY` px kept clear for labels. */
export function fitView(cy: Core, padX = cy.width() < 480 ? 52 : 84, padY = 48): void {
  const cards = cy.nodes(".card");
  if (cards.empty()) return;
  let x1 = Infinity;
  let y1 = Infinity;
  let x2 = -Infinity;
  let y2 = -Infinity;
  cards.forEach((n) => {
    const { x, y } = n.position();
    x1 = Math.min(x1, x);
    y1 = Math.min(y1, y);
    x2 = Math.max(x2, x);
    y2 = Math.max(y2, y);
  });
  const w = Math.max(x2 - x1, 1);
  const h = Math.max(y2 - y1, 1);
  const zoom = Math.min(1.5, Math.max(cy.minZoom(), Math.min((cy.width() - 2 * padX) / w, (cy.height() - 2 * padY) / h)));
  cy.zoom(zoom);
  cy.pan({ x: cy.width() / 2 - (zoom * (x1 + x2)) / 2, y: cy.height() / 2 - (zoom * (y1 + y2)) / 2 });
}

export default function GraphCanvas({ view, sections, selectedId, reducedMotion, onSelectCard, onSelectEdge }: GraphCanvasProps) {
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
  // True once the reader has panned or zoomed by hand: a resize of the box then keeps the view.
  const lockRef = useRef(createFitLock());
  const handlers = useRef({ onSelectCard, onSelectEdge });
  const selectedRef = useRef(selectedId);
  useEffect(() => {
    handlers.current = { onSelectCard, onSelectEdge };
    selectedRef.current = selectedId;
  });

  useEffect(() => {
    if (!registered) {
      cytoscape.use(fcose);
      registered = true;
    }
    const cy = cytoscape({
      container: host.current,
      elements: elements(view, sections),
      minZoom: 0.2,
      maxZoom: 3,
      wheelSensitivity: 0.3,
      boxSelectionEnabled: false,
      autoungrabify: true,
    });
    cyRef.current = cy;
    // The design-preview route (it always has ?state=) lets e2e read node positions to tap them.
    if (host.current && new URLSearchParams(window.location.search).has("state")) {
      (host.current as HTMLDivElement & { __cy?: Core }).__cy = cy;
    }

    // Everything that depends on zoom or on the palette lives here, so a resize of the box or a
    // switch of theme restyles without rebuilding the graph.
    const restyle = () => {
      cy.style(graphStylesheet(readPalette(), cy.zoom(), cy.width() < 480));
    };
    const mark = () => {
      cy.elements().removeClass("picked near far");
      const id = selectedRef.current;
      if (id === null || cy.getElementById(id).empty()) return;
      const dist = neighbourhood(view.edges, id, 2);
      cy.getElementById(id).addClass("picked");
      cy.nodes(".card").forEach((n) => {
        const d = dist.get(n.id());
        if (d === undefined) n.addClass("far");
        else if (d <= 1) n.addClass("near");
      });
      cy.edges().forEach((e) => {
        if (!dist.has(e.source().id()) || !dist.has(e.target().id())) e.addClass("far");
      });
    };
    const refresh = () => {
      mark();
      restyle();
    };

    cy.on("tap", "node.card", (ev) => handlers.current.onSelectCard(ev.target.id()));
    cy.on("tap", "edge", (ev) => handlers.current.onSelectEdge(ev.target.id()));
    cy.on("zoom", refresh);
    refresh();
    // Fit-to-view: after the layout settles, and again when the box changes size (the frame can
    // be sized after the first paint), until the reader pans or zooms by hand.
    // Zoom is locked from the input events (wheel, two-finger touch, the +/- buttons) and not from
    // cytoscape's "zoom" event, because fit() itself zooms.
    const fitLock = lockRef.current;
    fitLock.reset();
    const fit = () => {
      if (fitLock.touched || cy.destroyed()) return;
      // cy.fit() would fit the boxes of nodes and labels, but those are pixels / zoom in model
      // units, so fitting them zooms out, which makes them bigger, down to the minimum zoom.
      // Fit the card centres instead and leave room in pixels for a label either side.
      fitView(cy);
    };
    const detach = fitLock.attach(host.current);
    cy.on("dragpan", fitLock.lock);
    cy.on("layoutstop", () => {
      stretchToFrame(cy);
      fit();
      // Still two labels on one another (a narrow frame): push each such pair apart up and down.
      for (let i = 0; i < 12 && cy.width() < 480 && !fitLock.touched && separateLabels(cy); i++) fit();
    });
    cy.layout({
      name: "fcose",
      animate: !reducedMotion,
      animationDuration: 300,
      randomize: true,
      fit: true,
      padding: 24,
      nodeDimensionsIncludeLabels: true,
      nodeRepulsion: 12000,
      idealEdgeLength: 120,
      packComponents: true,
      quality: "default",
    } as cytoscape.LayoutOptions).run();

    // A theme switch changes custom properties on <html>; redraw with the new ink.
    const theme = new MutationObserver(refresh);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", refresh);
    const resize = new ResizeObserver(() => {
      cy.resize();
      fit();
    });
    if (host.current) resize.observe(host.current);

    return () => {
      theme.disconnect();
      scheme.removeEventListener("change", refresh);
      resize.disconnect();
      detach();
      cy.destroy();
      cyRef.current = null;
    };
    // Rebuilt when the data or the motion preference changes; selection is applied below.
  }, [view, sections, reducedMotion]);

  useEffect(() => {
    const cy = cyRef.current;
    if (cy === null) return;
    cy.emit("zoom"); // restyle + mark for the new selection
  }, [selectedId]);

  const zoomBy = (factor: number) => {
    const cy = cyRef.current;
    lockRef.current.lock();
    if (cy) cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  return (
    <div className="relative" data-graph-frame>
      <div
        ref={host}
        aria-hidden="true"
        data-graph-canvas
        data-foreign-dom
        className="h-[clamp(18rem,calc(100dvh-240px),42rem)] w-full touch-none overflow-hidden rounded-tile border border-line bg-hong-tint"
      />
      <div className="absolute right-2 bottom-2 flex gap-2">
        <button type="button" aria-label="Phóng to" className={ZOOM_BUTTON + " w-11"} onClick={() => zoomBy(1.3)}>
          +
        </button>
        <button type="button" aria-label="Thu nhỏ" className={ZOOM_BUTTON + " w-11"} onClick={() => zoomBy(1 / 1.3)}>
          −
        </button>
        <button type="button" aria-label="Đặt lại khung nhìn" className={ZOOM_BUTTON + " px-3"} onClick={() => {
            lockRef.current.reset();
            if (cyRef.current) fitView(cyRef.current);
          }}>
          Đặt lại
        </button>
      </div>
    </div>
  );
}
