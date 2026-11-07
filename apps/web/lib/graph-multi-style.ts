import type { StylesheetJson } from "cytoscape";

// V16/V17: the Cytoscape stylesheet of the knowledge graph. A node takes its colour from its own
// data (the subject's colour); edges are one ink line.
export function multiStylesheet(ink: string, line: string, surface = "#ffffff", soft = ink, display = "sans-serif"): StylesheetJson {
  return [
    {
      selector: "node",
      style: {
        // GRAPH-LANDING-STYLE: ring nodes like the landing graph: a pale tint of the topic colour inside a ring of the colour.
        "background-color": "data(fill)",
        width: "data(size)",
        height: "data(size)",
        label: "data(label)",
        // Labels show when zoomed in (class .labelled), or on the node under the pointer (.hot).
        "text-opacity": 0,
        color: soft,
        "font-size": 11,
        "text-valign": "bottom",
        "text-margin-y": 3,
        "text-wrap": "ellipsis",
        "text-max-width": "110px",
        // UI-A: a label never sits bare on an edge: a soft plate under the words.
        "text-background-color": surface,
        "text-background-opacity": 0.85,
        "text-background-padding": "2px",
        "text-background-shape": "roundrectangle",
        "border-width": 1.5,
        "border-color": "data(color)",
      },
    },
    // A hub (one per topic): the biggest node, a heavier ring, its name in the display font.
    { selector: "node.hub", style: { "border-width": 2.5, color: ink, "font-family": display, "font-size": 13, "font-weight": 600, "text-wrap": "wrap", "text-max-width": "130px" } },
    { selector: "edge", style: { width: 0.9, "line-color": line, "curve-style": "bezier", opacity: 0.34, "z-index": 0 } },
    { selector: "node", style: { "z-index": 10 } },
    { selector: "node.labelled", style: { "text-opacity": 1 } },
    { selector: "node.hot", style: { "text-opacity": 1 } },
    { selector: ".dim", style: { opacity: 0.18 } },
    { selector: "node.hot", style: { "border-color": ink, "border-width": 3 } },
    { selector: "edge.hot", style: { opacity: 1, "line-color": ink, width: 2 } },
  ];
}
