"use client";

import { useSyncExternalStore } from "react";

import { EDGE_STYLE, type GraphCard, type GraphEdge, type GraphView } from "@/lib/graph";

// T9.10a (US-19 AC3; DESIGN §6.15): the list that holds everything the canvas draws, for the
// keyboard and the screen reader. Same view, same filter, same tray. One form is in the DOM at a
// time: a real <table> from 768 px, a <ul> of cards below (a table turned into blocks loses its
// meaning for some readers). Tab walks the buttons: no roving focus.

const WIDE = "(min-width: 768px)";
const hasMedia = () => typeof window.matchMedia === "function";
const subscribe = (cb: () => void) => {
  const mq = hasMedia() ? window.matchMedia(WIDE) : null;
  mq?.addEventListener("change", cb);
  return () => mq?.removeEventListener("change", cb);
};
const snapshot = () => (hasMedia() ? window.matchMedia(WIDE).matches : false);

const LINK =
  "min-h-11 min-w-0 rounded-control px-2 py-2 text-left font-medium underline decoration-line-strong decoration-[1.5px] underline-offset-[5px] wrap-anywhere outline-none hover:decoration-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus aria-pressed:bg-hong-tint";

type Props = {
  view: GraphView;
  selectedId: string | null;
  onSelectCard: (id: string) => void;
};

function CardButton({
  card,
  other,
  edge,
  selected,
  onSelect,
}: {
  card: GraphCard;
  other: GraphCard;
  edge: GraphEdge;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      type="button"
      aria-label={`Chọn thẻ ${card.title}, liên kết ${EDGE_STYLE[edge.kind].label} với thẻ ${other.title}`}
      aria-pressed={selected}
      data-card={card.id}
      onClick={() => onSelect(card.id)}
      className={LINK}
    >
      {card.title}
    </button>
  );
}

export function EdgeList({ view, selectedId, onSelectCard }: Props) {
  const wide = useSyncExternalStore(subscribe, snapshot, () => false);
  const byId = new Map(view.cards.map((c) => [c.id, c] as const));
  const rows = view.edges.flatMap((e) => {
    const from = byId.get(e.from);
    const to = byId.get(e.to);
    return from && to ? [{ e, from, to }] : [];
  });
  const alone = view.cards.filter((c) => view.unlinked.has(c.id));

  return (
    <div data-edge-list className="flex min-w-0 flex-col gap-4">
      <a
        href="#after-list"
        className="w-fit text-caption underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-focus"
      >
        Bỏ qua danh sách
      </a>
      {rows.length > 0 &&
        (wide ? (
          <table className="w-full table-fixed [border-collapse:collapse] text-caption">
            <caption className="pb-2 text-left text-meta text-ink-soft">Liên kết giữa các thẻ</caption>
            <thead>
              <tr className="text-left">
                <th scope="col" className="w-[22%] py-1 pr-2 font-semibold">
                  Thẻ
                </th>
                <th scope="col" className="w-[18%] py-1 pr-2 font-semibold">
                  Loại liên kết
                </th>
                <th scope="col" className="w-[22%] py-1 pr-2 font-semibold">
                  Thẻ kia
                </th>
                <th scope="col" className="py-1 font-semibold">
                  Bằng chứng
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ e, from, to }) => (
                <tr key={e.id} data-edge-row={e.id} className="border-t border-line align-top">
                  <td className="py-1 pr-2" data-user>
                    <CardButton card={from} other={to} edge={e} selected={selectedId === from.id} onSelect={onSelectCard} />
                  </td>
                  <td className="py-3 pr-2">{EDGE_STYLE[e.kind].label}</td>
                  <td className="py-1 pr-2" data-user>
                    <CardButton card={to} other={from} edge={e} selected={selectedId === to.id} onSelect={onSelectCard} />
                  </td>
                  <td className="py-3 wrap-anywhere" data-user>
                    “{e.evidence}”
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <ul className="m-0 flex list-none flex-col gap-3 p-0" aria-label="Liên kết giữa các thẻ">
            {rows.map(({ e, from, to }) => (
              <li key={e.id} data-edge-row={e.id} className="rounded-control border border-line bg-sheet p-3">
                <dl className="m-0 flex min-w-0 flex-col gap-1 text-caption">
                  <dt className="text-ink-soft">Thẻ</dt>
                  <dd className="m-0" data-user>
                    <CardButton card={from} other={to} edge={e} selected={selectedId === from.id} onSelect={onSelectCard} />
                  </dd>
                  <dt className="text-ink-soft">Loại liên kết</dt>
                  <dd className="m-0 px-2 font-medium">{EDGE_STYLE[e.kind].label}</dd>
                  <dt className="text-ink-soft">Thẻ kia</dt>
                  <dd className="m-0" data-user>
                    <CardButton card={to} other={from} edge={e} selected={selectedId === to.id} onSelect={onSelectCard} />
                  </dd>
                  <dt className="text-ink-soft">Bằng chứng</dt>
                  <dd className="m-0 px-2 wrap-anywhere" data-user>
                    “{e.evidence}”
                  </dd>
                </dl>
              </li>
            ))}
          </ul>
        ))}
      {alone.length > 0 && (
        <section aria-labelledby="alone-h">
          <h3 id="alone-h" className="m-0 mb-1 text-caption font-semibold">
            Thẻ chưa có liên kết
          </h3>
          <ul className="m-0 flex list-none flex-col p-0" data-unlinked>
            {alone.map((c) => (
              <li key={c.id} data-user>
                <button
                  type="button"
                  aria-pressed={selectedId === c.id}
                  data-card={c.id}
                  onClick={() => onSelectCard(c.id)}
                  className={LINK}
                >
                  {c.title}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
      <span id="after-list" tabIndex={-1} className="sr-only">
        Hết danh sách
      </span>
    </div>
  );
}
