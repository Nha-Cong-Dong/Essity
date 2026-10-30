import { EDGE_KINDS, EDGE_STYLE, type EdgeKind } from "@/lib/graph";

// T9.10a (DESIGN §6.15 item 4): the legend. Five kinds told apart by stroke, end shape and word,
// in ink only, plus the two links that are not card-to-card.

/** A 56x16 sample of a kind's stroke and end, drawn with the same pattern the canvas uses. */
export function EdgeSample({ kind }: { kind: EdgeKind }) {
  const s = EDGE_STYLE[kind];
  const end = (tip: number, dir: 1 | -1) => {
    const back = tip - dir * 8;
    switch (s.arrow) {
      case "triangle":
        return <polygon points={`${tip},8 ${back},3 ${back},13`} fill="currentColor" />;
      case "diamond":
        return (
          <polygon
            points={`${tip},8 ${tip - dir * 5},4 ${tip - dir * 10},8 ${tip - dir * 5},12`}
            fill="var(--sheet)"
            stroke="currentColor"
            strokeWidth="1.5"
          />
        );
      case "vee":
        return <polyline points={`${back},3 ${tip},8 ${back},13`} fill="none" stroke="currentColor" strokeWidth="2" />;
      case "triangle-tee":
        return (
          <>
            <polygon points={`${tip},8 ${back},3 ${back},13`} fill="currentColor" />
            <line x1={tip} y1="2" x2={tip} y2="14" stroke="currentColor" strokeWidth="2" />
          </>
        );
      default:
        return null;
    }
  };
  return (
    <svg width="56" height="16" viewBox="0 0 56 16" aria-hidden="true" className="shrink-0 text-ink" data-edge-sample={kind}>
      <line
        x1={s.both ? 8 : 2}
        y1="8"
        x2="48"
        y2="8"
        stroke="currentColor"
        strokeWidth={s.width}
        strokeDasharray={s.dash?.join(" ")}
        strokeLinecap={s.dash ? "round" : "butt"}
      />
      {end(54, 1)}
      {s.both && end(2, -1)}
    </svg>
  );
}

export function Legend() {
  return (
    <details className="rounded-control border border-line bg-sheet px-3 py-1" data-legend>
      <summary className="flex h-11 cursor-pointer items-center text-caption font-semibold">Chú giải</summary>
      <ul className="m-0 mb-2 flex list-none flex-col gap-2 p-0 text-caption">
        {EDGE_KINDS.map((kind) => (
          <li key={kind} className="flex items-center gap-3">
            <EdgeSample kind={kind} />
            <span>{EDGE_STYLE[kind].label}</span>
          </li>
        ))}
        <li className="flex items-center gap-3">
          <svg width="56" height="16" viewBox="0 0 56 16" aria-hidden="true" className="shrink-0 text-line-strong">
            <rect x="2" y="2" width="52" height="12" rx="4" fill="none" stroke="currentColor" strokeWidth="1" />
          </svg>
          <span>Thẻ thuộc mục: khung mảnh quanh các thẻ cùng mục</span>
        </li>
        <li className="flex items-center gap-3">
          <span aria-hidden="true" className="w-14 shrink-0 text-center text-ink-soft">
            · · · ·
          </span>
          <span>Câu cần thẻ này: hiện trong khay khi chọn một thẻ, không vẽ trên đồ thị</span>
        </li>
      </ul>
    </details>
  );
}
