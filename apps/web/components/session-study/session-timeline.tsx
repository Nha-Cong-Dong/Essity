"use client";

import { Mascot } from "@/components/mascot";
import { hhmm, pieceSources, pieceTitle } from "@/lib/session-study/piece-view";
import type { Piece } from "@/lib/session-study/api";

// SESSION-V4-RESTORE (mockup session.html): "Đã học trong buổi", one row per "Ghi lại", newest first:
// time, short title, the note (clamped), "Nguồn tr.x" chips when the learner named pages. The empty
// state shows from the start so the save-a-part button and its result are obvious.

export function PieceTimeline({ pieces, onDrop, busy }: { pieces: Piece[]; onDrop: (id: string) => void; busy?: boolean }) {
  const rows = [...pieces].reverse();
  return (
    <section aria-labelledby="timeline-h" className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-3">
        <h2 id="timeline-h" className="m-0 font-display text-lead">
          Đã học trong buổi
        </h2>
        {rows.length > 0 && <span className="text-meta text-ink-soft">{rows.length} lần ghi</span>}
      </div>
      {rows.length === 0 ? (
        <div className="flex items-center gap-5 rounded-tile border border-line bg-sheet px-6 py-5">
          <Mascot pose="cho" size="md" className="shrink-0" />
          <div>
            <p className="m-0 font-display text-lead">Chưa có gì được ghi lại</p>
            <p className="m-0 text-body text-ink-soft">Mỗi lần bấm Ghi lại sẽ thành một dòng ở đây.</p>
          </div>
        </div>
      ) : (
        <ol aria-label="Đã học trong buổi" className="m-0 flex list-none flex-col gap-3 p-0">
          {rows.map((p) => {
            const title = pieceTitle(p.text);
            const sources = pieceSources(p.text);
            const rest = p.text.trim().slice(title.length).replace(/^[.!?…\s]+/, "");
            return (
              <li key={p.id} className="grid grid-cols-[44px_minmax(0,1fr)] gap-2.5 min-[641px]:grid-cols-[52px_minmax(0,1fr)] min-[641px]:gap-3.5">
                <time className="pt-4.5 text-right text-meta text-ink-soft tabular-nums">{hhmm(p.createdAt)}</time>
                <div className="flex min-w-0 flex-col gap-1.5 rounded-tile border border-line bg-sheet px-5 py-4 wrap-anywhere">
                  <b className="font-semibold">{title || (p.fileCount > 0 ? `${p.fileCount} file` : "Một phần")}</b>
                  {rest && <span className="line-clamp-3 whitespace-pre-line text-body text-ink-soft">{rest}</span>}
                  <span className="flex flex-wrap items-center gap-3 text-meta text-ink-soft">
                    {sources.map((s) => (
                      <span key={s} className="rounded-full bg-hong-tint px-3 py-0.5 text-ink">
                        Nguồn {s}
                      </span>
                    ))}
                    {p.fileCount > 0 && p.text.trim() && <span>+{p.fileCount} file</span>}
                    <button
                      type="button"
                      aria-label={`Bỏ phần ${p.position + 1}`}
                      aria-disabled={busy || undefined}
                      onClick={() => onDrop(p.id)}
                      className="ml-auto inline-flex min-h-11 items-center rounded-full px-3 text-meta text-ink-soft underline-offset-4 hover:text-ink hover:underline"
                    >
                      Bỏ phần này
                    </button>
                  </span>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
