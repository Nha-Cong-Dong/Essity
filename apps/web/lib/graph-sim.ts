// UI-A: a small force simulation for the knowledge graph (Obsidian-style): nodes repel, edges are
// springs, a weak pull keeps the cloud centred, and a faint drift keeps it alive. Pure maths over
// plain arrays so it is unit-testable; the canvas copies positions in and out each frame.

export type SimNode = { id: string; x: number; y: number; vx: number; vy: number; pinned: boolean };
export type SimEdge = { a: number; b: number };
export type SimOptions = {
  repulsion: number;
  spring: number;
  rest: number;
  gravity: number;
  damping: number;
  drift: number;
};

export const SIM_DEFAULTS: SimOptions = { repulsion: 9000, spring: 0.03, rest: 100, gravity: 0.003, damping: 0.86, drift: 0.05 };

/** A small graph is spread out to fill the canvas; a big one keeps its repulsion down so it stays compact. */
export const optionsFor = (count: number): SimOptions => ({ ...SIM_DEFAULTS, repulsion: SIM_DEFAULTS.repulsion * Math.min(1, 30 / Math.max(count, 1)) });

/** Advance one frame. `alpha` scales the forces (1 = full, ~0.1 = a gentle float). */
export function stepSim(nodes: SimNode[], edges: SimEdge[], alpha: number, noise: () => number, o: SimOptions = SIM_DEFAULTS): void {
  const n = nodes.length;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      let dx = nodes[j].x - nodes[i].x;
      let dy = nodes[j].y - nodes[i].y;
      let d2 = dx * dx + dy * dy;
      if (d2 < 0.01) {
        dx = noise() - 0.5;
        dy = noise() - 0.5;
        d2 = dx * dx + dy * dy + 0.01;
      }
      if (d2 > 640000) continue; // beyond 800 px nodes do not feel each other
      const d = Math.sqrt(d2);
      const f = (o.repulsion * alpha) / d2;
      const fx = (dx / d) * f;
      const fy = (dy / d) * f;
      nodes[i].vx -= fx;
      nodes[i].vy -= fy;
      nodes[j].vx += fx;
      nodes[j].vy += fy;
    }
  }
  for (const e of edges) {
    const p = nodes[e.a];
    const q = nodes[e.b];
    const dx = q.x - p.x;
    const dy = q.y - p.y;
    const d = Math.sqrt(dx * dx + dy * dy) || 0.001;
    const f = (d - o.rest) * o.spring * alpha;
    p.vx += (dx / d) * f;
    p.vy += (dy / d) * f;
    q.vx -= (dx / d) * f;
    q.vy -= (dy / d) * f;
  }
  let cx = 0;
  let cy = 0;
  for (const p of nodes) {
    cx += p.x;
    cy += p.y;
  }
  cx /= n || 1;
  cy /= n || 1;
  for (const p of nodes) {
    if (p.pinned) {
      p.vx = 0;
      p.vy = 0;
      continue;
    }
    p.vx += (cx - p.x) * o.gravity * alpha + (noise() - 0.5) * o.drift;
    p.vy += (cy - p.y) * o.gravity * alpha + (noise() - 0.5) * o.drift;
    p.vx *= o.damping;
    p.vy *= o.damping;
    p.x += p.vx;
    p.y += p.vy;
  }
}
