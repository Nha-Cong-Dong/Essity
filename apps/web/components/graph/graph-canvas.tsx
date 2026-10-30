"use client";

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import fcose from "cytoscape-fcose";
import { useEffect, useRef } from "react";

import { neighbourhood, shortLabel, type GraphSection, type GraphView } from "@/lib/graph";
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
    ink: get("--ink", "#221b1b"),
    line: get("--line-strong", "#8a6b7a"),
    sheet: get("--sheet", "#ffffff"),
    focus: get("--focus", "#a8255f"),
    soft: get("--ink-soft", "#6b4a59"),
  };
}

function elements(view: GraphView, sections: GraphSection[]): ElementDefinition[] {
  const used = new Set(view.cards.map((c) => c.sectionId));
  const out: ElementDefinition[] = sections
    .filter((s) => used.has(s.id))
    .map((s) => ({ data: { id: `s:${s.id}`, label: s.title, isSection: true }, selectable: false, grabbable: false }));
  for (const c of view.cards) {
    out.push({ data: { id: c.id, parent: `s:${c.sectionId}`, label: shortLabel(c.title), title: c.title }, classes: "card" });
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

export default function GraphCanvas({ view, sections, selectedId, reducedMotion, onSelectCard, onSelectEdge }: GraphCanvasProps) {
  const host = useRef<HTMLDivElement>(null);
  const cyRef = useRef<Core | null>(null);
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
      cy.style(graphStylesheet(readPalette(), cy.zoom()));
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
    cy.layout({
      name: "fcose",
      animate: !reducedMotion,
      animationDuration: 300,
      randomize: true,
      fit: true,
      padding: 24,
      nodeDimensionsIncludeLabels: true,
      quality: "default",
    } as cytoscape.LayoutOptions).run();

    // A theme switch changes custom properties on <html>; redraw with the new ink.
    const theme = new MutationObserver(refresh);
    theme.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    const scheme = window.matchMedia("(prefers-color-scheme: dark)");
    scheme.addEventListener("change", refresh);
    const resize = new ResizeObserver(() => cy.resize());
    if (host.current) resize.observe(host.current);

    return () => {
      theme.disconnect();
      scheme.removeEventListener("change", refresh);
      resize.disconnect();
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
    if (cy) cy.zoom({ level: cy.zoom() * factor, renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 } });
  };

  return (
    <div className="relative" data-graph-frame>
      <div
        ref={host}
        aria-hidden="true"
        data-graph-canvas
        className="h-[50vh] min-h-70 w-full touch-none overflow-hidden rounded-sheet border border-line bg-sheet"
      />
      <div className="absolute right-2 bottom-2 flex gap-2">
        <button type="button" aria-label="Phóng to" className={ZOOM_BUTTON + " w-11"} onClick={() => zoomBy(1.3)}>
          +
        </button>
        <button type="button" aria-label="Thu nhỏ" className={ZOOM_BUTTON + " w-11"} onClick={() => zoomBy(1 / 1.3)}>
          −
        </button>
        <button type="button" aria-label="Đặt lại khung nhìn" className={ZOOM_BUTTON + " px-3"} onClick={() => cyRef.current?.fit(undefined, 24)}>
          Đặt lại
        </button>
      </div>
    </div>
  );
}
