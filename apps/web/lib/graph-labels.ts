import type { Core, NodeSingular } from "cytoscape";

// E-10: label collision pass for the knowledge graph. Run once, after the layout has settled, in
// model coordinates (labels scale with zoom, so the overlap is the same at any zoom). Pure order
// (by node index, no randomness) so the same cards always end in the same places.

type Box = { x1: number; x2: number; y1: number; y2: number };

function labelBox(n: NodeSingular): Box {
  const b = n.boundingBox({ includeNodes: true, includeLabels: true, includeEdges: false, includeOverlays: false });
  return { x1: b.x1, x2: b.x2, y1: b.y1, y2: b.y2 };
}

/** Pushes apart (up and down, half each) every pair of nodes whose label boxes overlap; true if any moved. */
export function separateLabelBoxes(cy: Core, gap = 4): boolean {
  const nodes: NodeSingular[] = cy.nodes().filter((n) => n.style("display") !== "none").toArray() as NodeSingular[];
  let moved = false;
  for (let i = 0; i < nodes.length; i++) {
    for (let j = i + 1; j < nodes.length; j++) {
      const a = labelBox(nodes[i]);
      const b = labelBox(nodes[j]);
      if (!(a.x1 < b.x2 && b.x1 < a.x2 && a.y1 < b.y2 && b.y1 < a.y2)) continue;
      const need = Math.min(a.y2, b.y2) - Math.max(a.y1, b.y1) + gap;
      const [up, down] = a.y1 + a.y2 <= b.y1 + b.y2 ? [nodes[i], nodes[j]] : [nodes[j], nodes[i]];
      up.position({ x: up.position("x"), y: up.position("y") - need / 2 });
      down.position({ x: down.position("x"), y: down.position("y") + need / 2 });
      moved = true;
    }
  }
  return moved;
}

/** Repeats the pass a fixed number of times at most, so the cost is bounded and the result stable. */
export function settleLabels(cy: Core, rounds = 20): void {
  for (let i = 0; i < rounds; i++) if (!separateLabelBoxes(cy)) return;
}
